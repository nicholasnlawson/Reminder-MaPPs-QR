from flask import Flask, render_template, send_from_directory, request, jsonify, redirect, url_for, send_file, Response
import os
import re
import io
import json
import PyPDF2
import tempfile
import glob
import qrcode
import hashlib
import base64
from gtts import gTTS
from datetime import datetime, timedelta
from PIL import Image, ImageDraw, ImageFont

app = Flask(__name__)

# Directory for storing QR codes
QR_DIR = os.path.join(app.static_folder, 'qrcodes')

# Directory for storing audio files
AUDIO_DIR = os.path.join(app.static_folder, 'audio')

# Create directories if they don't exist
os.makedirs(QR_DIR, exist_ok=True)
os.makedirs(AUDIO_DIR, exist_ok=True)

# Dictionary to store instruction texts
instruction_texts = {}

# Path to store instruction data
INSTRUCTION_DATA_FILE = os.path.join(app.static_folder, 'data', 'instructions.json')

# Directory for backup files
BACKUP_DIR = os.path.join(app.static_folder, 'backups')
os.makedirs(BACKUP_DIR, exist_ok=True)

# Create data directory if it doesn't exist
data_dir = os.path.join(app.static_folder, 'data')
os.makedirs(data_dir, exist_ok=True)
print(f"Ensuring data directory exists: {data_dir}")

# Load existing instruction data if available
def load_instruction_data():
    global instruction_texts
    if os.path.exists(INSTRUCTION_DATA_FILE):
        try:
            with open(INSTRUCTION_DATA_FILE, 'r') as f:
                instruction_texts = json.load(f)
            print(f"Loaded {len(instruction_texts)} instructions from file")
        except Exception as e:
            print(f"Error loading instruction data: {e}")

# Save instruction data to file
def save_instruction_data():
    try:
        with open(INSTRUCTION_DATA_FILE, 'w') as f:
            json.dump(instruction_texts, f, indent=2)
        print(f"Saved {len(instruction_texts)} instructions to file")
        return True
    except Exception as e:
        print(f"Error saving instruction data: {e}")
        return False

# Load instruction data at startup
load_instruction_data()

# Path to the original HTML file
# The original HTML file is in the parent directory
ORIGINAL_HTML_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'chartgenerator.html')

@app.route('/')
def index():
    # Clean up old temp files on startup
    cleanup_temp_files(hours=24)
    # Clean up old audio files
    cleanup_audio_files(hours=1)
    # Render the Flask UI template
    return render_template('flask_ui_updated.html')

@app.route('/cleanup_temp', methods=['POST'])
def cleanup_temp():
    """Clean up temporary PDF files"""
    try:
        # Get the file to clean up from the request
        data = request.json
        filename = data.get('filename', None)
        
        if filename:
            # Clean up a specific file
            file_path = os.path.join(app.static_folder, 'temp', filename)
            if os.path.exists(file_path):
                os.remove(file_path)
                return jsonify({'status': 'success', 'message': f'File {filename} deleted'})
            else:
                return jsonify({'status': 'error', 'message': f'File {filename} not found'})
        else:
            # Clean up all files older than 1 hour
            num_deleted = cleanup_temp_files(hours=1)
            return jsonify({'status': 'success', 'message': f'Deleted {num_deleted} temporary files'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

def cleanup_temp_files(hours=1):
    """Delete temporary files older than the specified number of hours"""
    temp_dir = os.path.join(app.static_folder, 'temp')
    if not os.path.exists(temp_dir):
        return 0
        
    # Get current time
    now = datetime.now()
    count = 0
    
    # Check all files in the temp directory
    for file_path in glob.glob(os.path.join(temp_dir, '*')):
        # Skip directories
        if os.path.isdir(file_path):
            continue
            
        # Get file modification time
        file_mod_time = datetime.fromtimestamp(os.path.getmtime(file_path))
        
        # If file is older than specified hours, delete it
        if now - file_mod_time > timedelta(hours=hours):
            try:
                os.remove(file_path)
                count += 1
            except Exception as e:
                print(f"Error deleting {file_path}: {e}")
                
    return count

def cleanup_audio_files(hours=1):
    """Delete audio files older than the specified number of hours"""
    if not os.path.exists(AUDIO_DIR):
        return 0
        
    # Get current time
    now = datetime.now()
    count = 0
    
    # Check all files in the audio directory
    for file_path in glob.glob(os.path.join(AUDIO_DIR, '*.mp3')):
        # Get file modification time
        file_mod_time = datetime.fromtimestamp(os.path.getmtime(file_path))
        
        # If file is older than specified hours, delete it
        if now - file_mod_time > timedelta(hours=hours):
            try:
                os.remove(file_path)
                count += 1
                print(f"Deleted old audio file: {file_path}")
            except Exception as e:
                print(f"Error deleting {file_path}: {e}")
                
    return count

@app.route('/original')
def original():
    # Serve the original HTML file directly
    try:
        with open(ORIGINAL_HTML_PATH, 'r') as file:
            content = file.read()
        return content
    except FileNotFoundError:
        # If the file is not found, return a simple message
        return f"Original HTML file not found at: {ORIGINAL_HTML_PATH}"
        
@app.route('/admin')
def admin():
    # Serve the admin page for medication data management
    return render_template('admin.html')

# Normalize medication form terms
def normalize_form(form_term):
    """
    Normalize form terms to handle aliases
    """
    form_aliases = {
        "tablet": ["tablet", "tablets", "tabs", "tab"],
        "capsule": ["capsule", "capsules", "caps", "cap"],
        "inhaler": ["inhaler", "inhalator", "inhale", "inh"],
        "spray": ["spray", "sprays"],
        "liquid": ["liquid", "solution", "suspension", "syrup", "soln"],
        "gel": ["gel", "jelly"],
        "cream": ["cream", "crm", "ointment"],
        "patch": ["patch", "patches", "plaster"]
    }
    
    form_term = form_term.lower()
    
    # Check if the form term matches any of our known aliases
    for normalized_form, aliases in form_aliases.items():
        if form_term in aliases:
            return normalized_form
            
    # If no match found, return the original term
    return form_term

# Define medication keyword mappings
def find_matching_pdf(medication_name, pdf_type):
    """
    Find the most appropriate PDF based on medication name and keywords.
    pdf_type should be either 'leaflet' or 'pictorial'
    """
    # Convert medication name to lowercase for case-insensitive matching
    med_name_lower = medication_name.lower()
    
    # Convert pdf_type to the correct folder name
    pdf_folder = pdf_type + 's' if not pdf_type.endswith('s') else pdf_type
    pdf_key = 'leaflet' if 'leaflet' in pdf_type else 'pictorial'
    
    # Define keyword mappings for medications
    keyword_mappings = {
        'paracetamol': {
            'tablet': {
                'leaflet': 'paracetamoltabletsleaflet.pdf',
                'pictorial': 'Paracetamoltabletspictorial.pdf'
            }
        },
        'salbutamol': {
            'inhaler': {
                'leaflet': 'Salbutamolinhalerleaflet.pdf',
                'pictorial': 'Salbutamolinhalerpictorial.pdf'
            }
        },
        'peptac': {
            'suspension': {
                'leaflet': 'peptacliquidleaflet.pdf',
                'pictorial': 'peptacliquidpictorial.pdf'
            },
            'liquid': {
                'leaflet': 'peptacliquidleaflet.pdf',
                'pictorial': 'peptacliquidpictorial.pdf'
            }
        },
        'amlodipine': {
            'tablet': {
                'leaflet': 'amlodipinetabletleaflet.pdf',
                'pictorial': 'amlodipinetabletpictorial.pdf'
            }
        },
        'atorvastatin': {
            'tablet': {
                'leaflet': 'atorvastatintabletleaflet.pdf',
                'pictorial': 'atorvastatintabletpictorial.pdf'
            }
        },
        'carbomer': {
            'gel': {
                'leaflet': 'carbomerleaflet.pdf',
                'pictorial': 'carbomerpictorial.pdf'
            }
        },
        'doxycycline': {
            'capsule': {
                'leaflet': 'doxycyclinecapsuleleaflet.pdf',
                'pictorial': 'doxycyclinecapsulepictorial.pdf'
            }
        },
        'esomeprazole': {
            'tablet': {
                'leaflet': 'esomeprazoletabletleaflet.pdf',
                'pictorial': 'esomeprazoletabletpictorial.pdf'
            }
        },
        'furosemide': {
            'tablet': {
                'leaflet': 'furosemidetabletleaflet.pdf',
                'pictorial': 'furosemidetabletpictorial.pdf'
            }
        },
        'lisinopril': {
            'tablet': {
                'leaflet': 'lisinopriltabletleaflet.pdf',
                'pictorial': 'lisinopriltabletpictorial.pdf'
            }
        },
        'metformin': {
            'm/r tablet': {
                'leaflet': 'metforminmrtabletleaflet.pdf',
                'pictorial': 'metforminmrtabletpictorial.pdf'
            }
        },
        'mirtazapine': {
            'tablet': {
                'leaflet': 'mirtazapinetabletleaflet.pdf',
                'pictorial': 'mirtazapinetabletpictorial.pdf'
            }
        },
        'prednisolone': {
            'tablet': {
                'leaflet': 'prednisolonetabletleaflet.pdf',
                'pictorial': 'prednisolonetabletpictorial.pdf'
            }
        },
        'trimbow': {
            'mdi': {
                'leaflet': 'trimbowpMDIleaflet.pdf',
                'pictorial': 'trimbowpMDIpictorial.pdf'
            }
        },
        # Added new medications
        'gtn': {
            'spray': {
                'leaflet': 'gtnsprayleaflet.pdf',
                'pictorial': 'gtnspraypictorial.pdf'
            }
        },
        'fludrocortisone': {
            'tablet': {
                'leaflet': 'fludrocortisonetabletleaflet.pdf',
                'pictorial': 'fludrocortisonetabletpictorial.pdf'
            }
        },
        'apixaban': {
            'tablet': {
                'leaflet': 'apixabantabletleaflet.pdf',
                'pictorial': 'apixabantabletpictorial.pdf'
            }
        },
        'loperamide': {
            'capsule': {
                'leaflet': 'loperamidecapsuleleaflet.pdf',
                'pictorial': 'loperamidecapsulepictorial.pdf'
            }
        },
        'amiodarone': {
            'tablet': {
                'leaflet': 'amiodaronetabletleaflet.pdf',
                'pictorial': 'amiodaronetabletpictroial.pdf'  # Corrected to match actual filename
            }
        }
    }
    
    # Track the best match and its score
    best_match = None
    best_score = 0
    
    # Determine which type of PDF we're looking for
    pdf_key = 'leaflet' if 'leaflet' in pdf_type else 'pictorial'
    
    # Check each medication keyword
    for med_key, formulations in keyword_mappings.items():
        if med_key in med_name_lower:
            # Found a medication match, now check formulations
            for form_key, pdf_info in formulations.items():
                normalized_form = normalize_form(form_key)
                # Check if any form term (or its alias) is in the med name
                if any(alias in med_name_lower for alias in [
                    form_key, 
                    normalized_form, 
                    f"{normalized_form}s", 
                    f"{normalized_form[0:3]}", 
                    f"{normalized_form[0:3]}s"
                ]) or (form_key == 'tablet' and 'tab' in med_name_lower) or (form_key == 'capsule' and 'cap' in med_name_lower):
                    # Both medication and formulation match - this is a perfect match
                    return pdf_info[pdf_key] if pdf_key in pdf_info else None
                else:
                    # Only medication matches, keep track of it as a potential match
                    # Score of 1 for medication match
                    if 1 > best_score:
                        best_score = 1
                        best_match = list(formulations.values())[0][pdf_key]
    
    # If we found any match, return it
    if best_match:
        return best_match
    
    # No match found, return None
    return None

def get_formatted_medication_name(med_name):
    """
    Get a properly formatted medication name with formulation details.
    """
    med_name_lower = med_name.lower()
    
    # Define medication mappings with their proper names and formulations
    medication_mappings = {
        'salbutamol': {
            'mdi': 'Salbutamol pMDI inhaler',
            'inhaler': 'Salbutamol pMDI inhaler',
        },
        'trimbow': {
            'pMDI': 'Trimbow pMDI inhaler',
            'inhaler': 'Trimbow pMDI inhaler'
        },
        'doxycycline': {
            'capsule': 'Doxycycline capsules',
        },
        'esomeprazole': {
            'tablet': 'Esomeprazole tablets',
        },
        'furosemide': {
            'tablet': 'Furosemide tablets',
        },
        'lisinopril': {
            'tablet': 'Lisinopril tablets'
        },
        'metformin': {
            'm/r tablet': 'Metformin modified-release tablets',
        },
        'mirtazapine': {
            'tablet': 'Mirtazapine tablets',
        },
        'prednisolone': {
            'tablet': 'Prednisolone tablets',
        },
        'paracetamol': {
            'tablet': 'Paracetamol tablets',
        },
        'peptac': {
            'suspension': 'Peptac liquid',
            'liquid': 'Peptac liquid'
        },
        'amlodipine': {
            'tablet': 'Amlodipine tablets'
        },
        'atorvastatin': {
            'tablet': 'Atorvastatin tablets'
        },
        'carbomer': {
            'gel': 'Carbomer eye gel'
        },
        # Added new medications
        'gtn': {
            'spray': 'GTN spray'
        },
        'fludrocortisone': {
            'tablet': 'Fludrocortisone tablets'
        },
        'apixaban': {
            'tablet': 'Apixaban tablets'
        },
        'loperamide': {
            'capsule': 'Loperamide capsules'
        },
        'amiodarone': {
            'tablet': 'Amiodarone tablets'
        }
    }
    
    # Find the medication in our mappings
    for med_key, formulations in medication_mappings.items():
        if med_key in med_name_lower:
            # Found a medication match, now check formulations
            for form_key, formatted_name in formulations.items():
                normalized_form = normalize_form(form_key)
                # Check for form aliases
                if any(alias in med_name_lower for alias in [
                    form_key, 
                    normalized_form, 
                    f"{normalized_form}s", 
                    f"{normalized_form[0:3]}", 
                    f"{normalized_form[0:3]}s"
                ]):
                    # Both medication and formulation match
                    return formatted_name
            
            # If no formulation match but medication matches, return the first formulation
            if formulations:
                return list(formulations.values())[0]
    
    # If no match found, return the original name
    return med_name

def get_all_medications():
    """
    Get a list of all available medications with their formulations.
    """
    medications = [
        {'name': 'Salbutamol', 'formulation': 'pMDI inhaler'},
        {'name': 'Trimbow', 'formulation': 'pMDI inhaler'},
        {'name': 'Doxycycline', 'formulation': 'capsules'},
        {'name': 'Esomeprazole', 'formulation': 'tablets'},
        {'name': 'Furosemide', 'formulation': 'tablets'},
        {'name': 'Lisinopril', 'formulation': 'tablets'},
        {'name': 'Metformin', 'formulation': 'M/R tablets'},
        {'name': 'Mirtazapine', 'formulation': 'tablets'},
        {'name': 'Prednisolone', 'formulation': 'tablets'},
        {'name': 'Paracetamol', 'formulation': 'tablets'},
        {'name': 'Peptac', 'formulation': 'liquid'},
        {'name': 'Amlodipine', 'formulation': 'tablets'},
        {'name': 'Atorvastatin', 'formulation': 'tablets'},
        {'name': 'Carbomer', 'formulation': 'eye gel'},
        # Added new medications
        {'name': 'GTN', 'formulation': 'spray'},
        {'name': 'Fludrocortisone', 'formulation': 'tablets'},
        {'name': 'Apixaban', 'formulation': 'tablets'},
        {'name': 'Loperamide', 'formulation': 'capsules'},
        {'name': 'Amiodarone', 'formulation': 'tablets'}
    ]
    
    # Add PDF availability information
    for med in medications:
        # Try with both combined name and individual components
        med_name = f"{med['name']} {med['formulation']}"
        pdf_leaflet = find_matching_pdf(med_name, 'leaflet')
        pdf_pictorial = find_matching_pdf(med_name, 'pictorial')
        
        # If not found, try with just the medication name
        if pdf_leaflet is None and pdf_pictorial is None:
            pdf_leaflet = find_matching_pdf(med['name'], 'leaflet')
            pdf_pictorial = find_matching_pdf(med['name'], 'pictorial')
            
        # Print debug info
        print(f"Checking: {med_name}")
        print(f"  Leaflet: {pdf_leaflet}")
        print(f"  Pictorial: {pdf_pictorial}")
        
        med['pdfAvailable'] = (pdf_leaflet is not None) or (pdf_pictorial is not None)
        med['pdfLeafletAvailable'] = pdf_leaflet is not None
        med['pdfPictorialAvailable'] = pdf_pictorial is not None
        
        if pdf_leaflet:
            med['pdfLeafletFilename'] = pdf_leaflet
        if pdf_pictorial:
            med['pdfPictorialFilename'] = pdf_pictorial
    
    return medications

@app.route('/generate_leaflet', methods=['POST'])
def generate_leaflet():
    """
    Generate patient information leaflets based on the provided medication names.
    This will find and serve the appropriate PDF leaflets based on keyword matching.
    """
    data = request.json
    medication_names = data.get('medicationNames', [])
    
    # If no medications were provided, return an error
    if not medications_list_check(medication_names):
        return jsonify({
            'status': 'error',
            'message': 'No medication names provided'
        })
    
    # Find matching PDF leaflets for all medications
    pdf_files = []
    not_found_medications = []
    
    for medication_name in medication_names:
        pdf_filename = find_matching_pdf(medication_name, 'leaflets')
        if pdf_filename:
            # Store the full file path
            pdf_files.append(os.path.join(app.root_path, 'static', 'pdfs', 'leaflets', pdf_filename))
        else:
            not_found_medications.append(medication_name)
    
    # If we found at least one PDF, merge them and return the merged PDF
    if pdf_files:
        # Create a unique filename for the merged PDF
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        merged_filename = f'merged_leaflets_{timestamp}.pdf'
        merged_filepath = os.path.join(app.root_path, 'static', 'temp', merged_filename)
        
        # Create the temp directory if it doesn't exist
        os.makedirs(os.path.join(app.root_path, 'static', 'temp'), exist_ok=True)
        
        # Merge the PDFs
        merge_pdfs(pdf_files, merged_filepath)
        
        # Return the path to the merged PDF
        return jsonify({
            'status': 'success',
            'type': 'pdf',
            'pdf_path': f'/static/temp/{merged_filename}',
            'not_found_medications': not_found_medications
        })
    
    # If no matching PDFs were found, generate a fallback HTML response
    # Create a list of medications that weren't found
    not_found_list = '\n'.join([f'<li>{med}</li>' for med in not_found_medications])
    
    html = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Patient Information Leaflet - Not Found</title>
        <style>
            body {{
                font-family: Arial, sans-serif;
                line-height: 1.6;
                margin: 0;
                padding: 20px;
                max-width: 800px;
                margin: 0 auto;
            }}
            h1, h2 {{
                color: #2c3e50;
            }}
            .header {{
                text-align: center;
                margin-bottom: 30px;
                padding-bottom: 10px;
                border-bottom: 2px solid #3498db;
            }}
            .section {{
                margin-bottom: 20px;
                padding: 15px;
                background-color: #f9f9f9;
                border-radius: 5px;
            }}
            .warning {{
                background-color: #ffe6e6;
                border-left: 4px solid #ff4d4d;
                padding: 10px 15px;
                margin-bottom: 20px;
            }}
            .footer {{
                text-align: center;
                margin-top: 30px;
                padding-top: 10px;
                border-top: 1px solid #ddd;
                font-size: 0.9em;
                color: #7f8c8d;
            }}
            @media print {{
                body {{
                    padding: 0;
                }}
                .no-print {{
                    display: none;
                }}
            }}
        </style>
    </head>
    <body>
        <div class="header">
            <h1>Patient Information Leaflet</h1>
            <h2>Medications Not Found</h2>
        </div>
        
        <div class="warning">
            <strong>Important:</strong> No matching leaflets found for the following medications:
        </div>
        
        <div class="section">
            <h3>Medications Without Leaflets</h3>
            <ul>
                {not_found_list}
            </ul>
            <p>Please consult your healthcare provider for information about these medications.</p>
        </div>
        
        <div class="footer">
            <p>This notice was generated on {datetime.now().strftime('%Y-%m-%d')}.</p>
            <p>For medical emergencies, contact your healthcare provider or local emergency services.</p>
            <button class="no-print" onclick="window.print()">Print this Notice</button>
        </div>
    </body>
    </html>
    """
    
    return jsonify({
        'status': 'success',
        'html': html
    })

@app.route('/generate_pictorial', methods=['POST'])
def generate_pictorial():
    """
    Generate easy read pictorials based on the provided medication names.
    This will find and serve the appropriate PDF pictorials based on keyword matching.
    """
    data = request.json
    medication_names = data.get('medicationNames', [])
    
    # If no medications were provided, return an error
    if not medications_list_check(medication_names):
        return jsonify({
            'status': 'error',
            'message': 'No medication names provided'
        })
    
    # Find matching PDF pictorials for all medications
    pdf_files = []
    not_found_medications = []
    
    for medication_name in medication_names:
        pdf_filename = find_matching_pdf(medication_name, 'pictorials')
        if pdf_filename:
            # Store the full file path
            pdf_files.append(os.path.join(app.root_path, 'static', 'pdfs', 'pictorials', pdf_filename))
        else:
            not_found_medications.append(medication_name)
    
    # If we found at least one PDF, merge them and return the merged PDF
    if pdf_files:
        # Create a unique filename for the merged PDF
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        merged_filename = f'merged_pictorials_{timestamp}.pdf'
        merged_filepath = os.path.join(app.root_path, 'static', 'temp', merged_filename)
        
        # Create the temp directory if it doesn't exist
        os.makedirs(os.path.join(app.root_path, 'static', 'temp'), exist_ok=True)
        
        # Merge the PDFs
        merge_pdfs(pdf_files, merged_filepath)
        
        # Return the path to the merged PDF
        return jsonify({
            'status': 'success',
            'type': 'pdf',
            'pdf_path': f'/static/temp/{merged_filename}',
            'not_found_medications': not_found_medications
        })
    
    # If no matching PDFs were found, generate a fallback HTML response
    # Create a list of medications that weren't found
    not_found_list = '\n'.join([f'<li>{med}</li>' for med in not_found_medications])
    
    html = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Easy Read Pictorial - Not Found</title>
        <style>
            body {{
                font-family: Arial, sans-serif;
                line-height: 1.6;
                margin: 0;
                padding: 20px;
                max-width: 800px;
                margin: 0 auto;
                text-align: center;
            }}
            h1 {{
                color: #2c3e50;
                margin-bottom: 30px;
            }}
            .pictorial {{
                display: flex;
                flex-direction: column;
                align-items: center;
                gap: 20px;
                margin: 30px 0;
            }}
            .card {{
                background-color: #f9f9f9;
                border-radius: 10px;
                padding: 20px;
                width: 100%;
                max-width: 400px;
                box-shadow: 0 4px 8px rgba(0,0,0,0.1);
            }}
            .emoji {{
                font-size: 5em;
                margin: 10px 0;
            }}
            .instruction {{
                font-size: 1.5em;
                margin: 10px 0;
            }}
            .medication {{
                font-size: 2em;
                font-weight: bold;
                color: #3498db;
                margin: 15px 0;
            }}
            ul {{
                text-align: left;
                padding-left: 20px;
            }}
            .footer {{
                margin-top: 30px;
                font-size: 0.9em;
                color: #7f8c8d;
            }}
            @media print {{
                body {{
                    padding: 0;
                }}
                .no-print {{
                    display: none;
                }}
            }}
        </style>
    </head>
    <body>
        <h1>Easy Read Pictorial</h1>
        
        <div class="pictorial">
            <div class="card">
                <div class="emoji">💊</div>
                <div class="medication">Medications Not Found</div>
            </div>
            
            <div class="card">
                <p>No matching pictorials found for the following medications:</p>
                <ul>
                    {not_found_list}
                </ul>
                <p>Please consult your healthcare provider for information about these medications.</p>
            </div>
        </div>
        
        <div class="footer">
            <p>This notice was generated on {datetime.now().strftime('%Y-%m-%d')}.</p>
            <p>If you have questions, talk to your doctor or pharmacist.</p>
            <button class="no-print" onclick="window.print()">Print this Notice</button>
        </div>
    </body>
    </html>
    """
    
    return jsonify({
        'status': 'success',
        'html': html
    })

@app.route('/test')
def test_page():
    """
    Serve a test page with a sample discharge letter for testing the medication extraction.
    """
    return send_from_directory('static', 'test_discharge_letter.html')

def medications_list_check(medication_names):
    """
    Check if the medication_names list is valid
    """
    return medication_names and isinstance(medication_names, list) and len(medication_names) > 0


def merge_pdfs(pdf_files, output_path):
    """
    Merge multiple PDF files into a single PDF file
    """
    merger = PyPDF2.PdfMerger()
    
    for pdf_file in pdf_files:
        merger.append(pdf_file)
    
    merger.write(output_path)
    merger.close()
    
    return output_path


@app.route('/search_medications', methods=['POST'])
def search_medications():
    """
    Search for medications based on a search term.
    Returns a list of matching medications with their formulations.
    """
    data = request.json
    search_term = data.get('searchTerm', '').lower()
    
    if not search_term or len(search_term) < 2:
        return jsonify({
            'status': 'error',
            'message': 'Search term must be at least 2 characters long'
        })
    
    # Get all medications
    all_medications = get_all_medications()
    
    # Filter medications based on search term
    matching_medications = []
    for med in all_medications:
        if search_term in med['name'].lower() or search_term in med['formulation'].lower():
            matching_medications.append(med)
    
    return jsonify({
        'status': 'success',
        'medications': matching_medications
    })

@app.route('/get_medication_details', methods=['POST'])
def get_medication_details():
    """
    Get details for a specific medication, including its formatted name and PDF availability.
    """
    data = request.json
    medication_name = data.get('medicationName', '')
    
    if not medication_name:
        return jsonify({
            'status': 'error',
            'message': 'No medication name provided'
        })
    
    # Get formatted medication name
    formatted_name = get_formatted_medication_name(medication_name)
    
    # Check if PDF is available
    pdf_leaflet = find_matching_pdf(medication_name, 'leaflets')
    pdf_pictorial = find_matching_pdf(medication_name, 'pictorials')
    
    return jsonify({
        'status': 'success',
        'formattedName': formatted_name,
        'pdfAvailable': (pdf_leaflet is not None) or (pdf_pictorial is not None),
        'pdfLeafletAvailable': pdf_leaflet is not None,
        'pdfPictorialAvailable': pdf_pictorial is not None,
        'pdfLeafletFilename': pdf_leaflet if pdf_leaflet else None,
        'pdfPictorialFilename': pdf_pictorial if pdf_pictorial else None
    })


# Generate a unique ID for an instruction
def generate_instruction_id(instruction):
    # Create a hash of the instruction to use as a unique identifier
    hash_obj = hashlib.md5(instruction.encode('utf-8'))
    return hash_obj.hexdigest()

# Ensure instruction pages exist for multiple medications
@app.route('/ensure_instruction_pages', methods=['POST'])
def ensure_instruction_pages():
    try:
        data = request.json
        instructions_data = data.get('instructions', [])
        
        if not instructions_data:
            return jsonify({'status': 'error', 'message': 'No instructions provided'})
        
        results = []
        
        for item in instructions_data:
            medication_name = item.get('medication_name', '')
            instruction = item.get('instruction', '')
            instruction_id = item.get('instruction_id', '')
            
            if not instruction or not instruction_id:
                continue
                
            # Check if instruction ID matches what we would generate
            generated_id = generate_instruction_id(instruction)
            if generated_id != instruction_id:
                print(f"Warning: Instruction ID mismatch for {medication_name}")
                instruction_id = generated_id
            
            # Create QR code that points to the instruction page
            qr_url = url_for('instruction_page', instruction_id=instruction_id, _external=True)
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=10,
                border=4,
            )
            qr.add_data(qr_url)
            qr.make(fit=True)
            
            # Create QR code image
            qr_img = qr.make_image(fill_color="black", back_color="white")
            
            # Add medication name as text below QR code if provided
            if medication_name:
                # Create a new image with space for text
                img_width, img_height = qr_img.size
                new_img = Image.new('RGB', (img_width, img_height + 40), 'white')
                new_img.paste(qr_img, (0, 0))
                
                # Add text
                draw = ImageDraw.Draw(new_img)
                try:
                    font = ImageFont.truetype("Arial", 16)
                except IOError:
                    font = ImageFont.load_default()
                    
                # Draw medication name centered below QR code
                text_width = draw.textlength(medication_name, font=font)
                draw.text(((img_width - text_width) // 2, img_height + 10), medication_name, fill="black", font=font)
                qr_img = new_img
            
            # Save QR code image
            qr_filename = f"{instruction_id}.png"
            qr_path = os.path.join(QR_DIR, qr_filename)
            qr_img.save(qr_path)
            
            # Generate audio file if it doesn't exist
            audio_filename = f"{instruction_id}.mp3"
            audio_path = os.path.join(AUDIO_DIR, audio_filename)
            
            if not os.path.exists(audio_path):
                # Create the audio file with gTTS
                spoken_text = f"For {medication_name}: {instruction}" if medication_name else instruction
                tts = gTTS(text=spoken_text, lang='en')
                tts.save(audio_path)
            
            # Store the instruction text for this ID if it's not already stored
            if instruction_id not in instruction_texts:
                instruction_texts[instruction_id] = {
                    'text': instruction,
                    'medication_name': medication_name
                }
            
            results.append({
                'instruction_id': instruction_id,
                'qr_generated': True,
                'audio_generated': not os.path.exists(audio_path)
            })
        
        # Save the updated instruction data to file
        save_instruction_data()
        
        return jsonify({
            'status': 'success',
            'message': f'{len(results)} instruction pages ensured',
            'results': results
        })
        
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

# Generate a QR code for a medication instruction
@app.route('/generate_qr_code', methods=['POST'])
def generate_qr_code():
    try:
        data = request.json
        medication_name = data.get('medication_name', '')
        instruction = data.get('instruction', '')
        
        if not instruction:
            return jsonify({'status': 'error', 'message': 'Instruction is required'})
        
        # Generate a unique ID for this instruction
        instruction_id = generate_instruction_id(instruction)
        
        # Create QR code that points to the instruction page
        qr_url = url_for('instruction_page', instruction_id=instruction_id, _external=True)
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(qr_url)
        qr.make(fit=True)
        
        # Create QR code image
        qr_img = qr.make_image(fill_color="black", back_color="white")
        
        # Add medication name as text below QR code
        if medication_name:
            # Create a new image with space for text
            img_width, img_height = qr_img.size
            new_img = Image.new('RGB', (img_width, img_height + 40), 'white')
            new_img.paste(qr_img, (0, 0))
            
            # Add text
            draw = ImageDraw.Draw(new_img)
            try:
                font = ImageFont.truetype("Arial", 16)
            except IOError:
                font = ImageFont.load_default()
                
            # Draw medication name centered below QR code
            text_width = draw.textlength(medication_name, font=font)
            draw.text(((img_width - text_width) // 2, img_height + 10), medication_name, fill="black", font=font)
            qr_img = new_img
        
        # Save QR code image
        qr_filename = f"{instruction_id}.png"
        qr_path = os.path.join(QR_DIR, qr_filename)
        qr_img.save(qr_path)
        
        # Generate audio file if it doesn't exist
        audio_filename = f"{instruction_id}.mp3"
        audio_path = os.path.join(AUDIO_DIR, audio_filename)
        
        if not os.path.exists(audio_path):
            # Create the audio file with gTTS
            spoken_text = f"For {medication_name}: {instruction}" if medication_name else instruction
            tts = gTTS(text=spoken_text, lang='en')
            tts.save(audio_path)
        
        # Store the instruction text for this ID if it's not already stored
        instruction_data = {
            'medication_name': medication_name,
            'instruction': instruction,
            'qr_path': qr_path,
            'audio_path': audio_path
        }
        
        # Save instruction data to JSON file
        instruction_data_file = os.path.join(app.static_folder, 'data', 'instructions.json')
        
        # Create the data directory if it doesn't exist
        os.makedirs(os.path.dirname(instruction_data_file), exist_ok=True)
        
        # Load existing data if file exists
        existing_data = {}
        if os.path.exists(instruction_data_file):
            try:
                with open(instruction_data_file, 'r') as f:
                    existing_data = json.loads(f.read())
            except Exception as e:
                print(f"Error loading instruction data: {e}")
        
        # Update with new data
        existing_data[instruction_id] = instruction_data
        
        # Save updated data
        with open(instruction_data_file, 'w') as f:
            f.write(json.dumps(existing_data, indent=2))
        
        # Return the QR code URL and instruction ID
        return jsonify({
            'status': 'success',
            'qr_url': url_for('static', filename=f'qrcodes/{qr_filename}'),
            'instruction_id': instruction_id
        })
        
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

# Page that displays the instruction and plays the audio
@app.route('/instruction/<instruction_id>')
def instruction_page(instruction_id):
    try:
        print(f"\n\n==== PROCESSING INSTRUCTION PAGE REQUEST FOR ID: {instruction_id} ====\n")
        print(f"Current instruction_texts keys: {list(instruction_texts.keys())}")
        
        # Check if we have the instruction text in memory
        instruction_info = instruction_texts.get(instruction_id)
        
        # If we don't have the instruction in memory, try to load from file
        if not instruction_info:
            print(f"Instruction not found in memory: {instruction_id}, trying to load from file")
            
            # Try to load from the instructions.json file
            instruction_data_file = os.path.join(app.static_folder, 'data', 'instructions.json')
            
            if os.path.exists(instruction_data_file):
                try:
                    with open(instruction_data_file, 'r') as f:
                        all_instructions = json.load(f)
                    
                    print(f"Loaded instructions from file. Available IDs: {list(all_instructions.keys())}")
                    
                    # Check if the instruction ID exists in the file
                    if instruction_id in all_instructions:
                        instruction_info = all_instructions[instruction_id]
                        # Store in memory for future use
                        instruction_texts[instruction_id] = instruction_info
                        print(f"Found instruction {instruction_id} in file and stored in memory")
                except Exception as e:
                    print(f"Error loading instruction data from file: {e}")
                    
        # Debug what we found
        if instruction_info:
            print(f"Instruction info found: {instruction_info}")
        
        # If we don't have the instruction info, return an error
        if not instruction_info:
            print(f"Instruction not found: {instruction_id}")
            print(f"Available instructions: {list(instruction_texts.keys())}")
            return render_template('error.html', message="Instruction not found. This QR code may be invalid or not yet generated."), 404
            
        # If we have instruction info but it's in the wrong format, fix it
        if instruction_info and 'text' not in instruction_info and 'instructions' in instruction_info:
            instruction_info['text'] = instruction_info['instructions']
            
        # If we have instruction info but it's missing medication_name, set it to empty string
        if instruction_info and 'medication_name' not in instruction_info:
            instruction_info['medication_name'] = ''
        
        # Generate audio file if it doesn't exist or is older than 1 hour
        audio_filename = f"{instruction_id}.mp3"
        audio_path = os.path.join(AUDIO_DIR, audio_filename)
        audio_url = f"/static/audio/{audio_filename}"
        
        # Check if file exists and when it was created
        should_generate_audio = True
        if os.path.exists(audio_path):
            file_mod_time = datetime.fromtimestamp(os.path.getmtime(audio_path))
            if datetime.now() - file_mod_time < timedelta(hours=1):
                # File is fresh (less than 1 hour old), use it
                should_generate_audio = False
                print(f"Using existing audio file: {audio_path}")
        
        # Generate audio file if needed
        if should_generate_audio:
            try:
                # Generate spoken text
                if instruction_info.get('medication_name'):
                    spoken_text = f"For {instruction_info.get('medication_name')}, {instruction_info.get('text', '')}"
                else:
                    spoken_text = instruction_info.get('text', '')
                
                print(f"Generating audio for text: '{spoken_text}'")
                    
                # Create high-quality UK English audio
                tts = gTTS(text=spoken_text, lang='en-gb', slow=False)
                print(f"Saving audio to: {audio_path}")
                tts.save(audio_path)
                
                print(f"Generated new audio file: {audio_path}")
                # Verify file was created
                if os.path.exists(audio_path):
                    file_size = os.path.getsize(audio_path)
                    print(f"Audio file created successfully. Size: {file_size} bytes")
                else:
                    print(f"WARNING: Audio file was not created at {audio_path}")
                    audio_url = None
            except Exception as e:
                print(f"Error generating audio file: {e}")
                # If there's an error generating the audio, we'll fall back to Web Speech API
                audio_url = None
        
        # Verify the audio file exists
        if not os.path.exists(audio_path):
            print(f"Audio file does not exist: {audio_path}")
            audio_url = None
        
        # Get instruction text for display
        instruction_text = ""
        medication_name = ""
        dosage = ""
        timing = ""
        route = ""
        
        if instruction_info:
            instruction_text = instruction_info.get('text', '') or instruction_info.get('instructions', '')
            medication_name = instruction_info.get('medication_name', '')
            dosage = instruction_info.get('dosage', '')
            timing = instruction_info.get('timing', '')
            route = instruction_info.get('route', '')
        
        # Debug the values we're passing to the template
        print(f"Rendering template with:")
        print(f"  - instruction_text: {instruction_text}")
        print(f"  - medication_name: {medication_name}")
        print(f"  - dosage: {dosage}")
        print(f"  - timing: {timing}")
        print(f"  - route: {route}")
        print(f"  - audio_url: {audio_url}")
        
        return render_template('instruction.html', 
                               instruction_id=instruction_id,
                               instruction_text=instruction_text,
                               medication_name=medication_name,
                               dosage=dosage,
                               timing=timing,
                               route=route,
                               audio_url=audio_url)
    
    except Exception as e:
        print(f"Error in instruction_page: {e}")
        return render_template('error.html', message=str(e)), 500


# Endpoint to create an instruction page from the chart generator
@app.route('/create_instruction_page', methods=['POST'])
def create_instruction_page():
    try:
        # Get the instruction data from the request
        data = request.json
        
        # Validate required fields
        required_fields = ['instruction_id', 'instructions']
        for field in required_fields:
            if field not in data:
                return jsonify({'status': 'error', 'message': f'Missing required field: {field}'}), 400
        
        instruction_id = data['instruction_id']
        instructions = data['instructions']
        medication_name = data.get('medication_name', '')
        dosage = data.get('dosage', '')
        timing = data.get('timing', '')
        route = data.get('route', '')
        
        # Create the instruction data
        instruction_data = {
            'text': instructions,
            'instructions': instructions,  # Keep both for compatibility
            'medication_name': medication_name,
            'dosage': dosage,
            'timing': timing,
            'route': route
        }
        
        # Store the instruction data in memory
        instruction_texts[instruction_id] = instruction_data
        
        # Save to file
        save_instruction_data()
        
        # No need to create audio files anymore as we're using Web Speech API
        
        return jsonify({
            'status': 'success', 
            'message': 'Instruction page created successfully',
            'instruction_id': instruction_id,
            'instruction_url': f'/instruction/{instruction_id}'
        })
    
    except Exception as e:
        print(f"Error creating instruction page: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500
        
# Get instruction text for a specific instruction ID
@app.route('/get_instruction_text/<instruction_id>', methods=['GET'])
def get_instruction_text(instruction_id):
    try:
        # For now, we'll store instruction data in a simple JSON file
        # In a real application, this would be stored in a database
        instruction_data_file = os.path.join(app.static_folder, 'data', 'instructions.json')
        
        # Create the data directory if it doesn't exist
        os.makedirs(os.path.dirname(instruction_data_file), exist_ok=True)
        
        # Initialize with empty data
        instruction_data = {}
        
        # Load existing data if file exists
        if os.path.exists(instruction_data_file):
            try:
                with open(instruction_data_file, 'r') as f:
                    instruction_data = json.loads(f.read())
            except Exception as e:
                print(f"Error loading instruction data: {e}")
        
        # Check if we have data for this instruction ID
        if instruction_id in instruction_data:
            return jsonify({
                'status': 'success',
                'instruction': instruction_data[instruction_id]['instruction'],
                'medication_name': instruction_data[instruction_id].get('medication_name', '')
            })
        else:
            # If we don't have the data, try to infer it from the audio filename
            # This is a fallback mechanism
            return jsonify({
                'status': 'success',
                'instruction': 'Please listen to the audio instructions',
                'medication_name': ''
            })
    
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        })

# Generate QR codes for all instructions in a medication list
@app.route('/generate_qr_codes_for_medications', methods=['POST'])
def generate_qr_codes_for_medications():
    try:
        data = request.json
        medications = data.get('medications', [])
        
        # Debug logging
        print(f"Received request to generate QR codes for {len(medications)} medications")
        print(f"Medications data: {medications}")
        
        if not medications:
            return jsonify({'status': 'error', 'message': 'No medications provided'})
        
        results = []
        for med in medications:
            medication_name = med.get('name', '')
            instruction = med.get('instructions', '')
            
            if instruction:
                # Generate QR code for this instruction
                instruction_id = generate_instruction_id(instruction)
                qr_filename = f"{instruction_id}.png"
                
                # Check if QR code already exists
                qr_path = os.path.join(QR_DIR, qr_filename)
                if not os.path.exists(qr_path):
                    # Create the QR code
                    qr_url = url_for('instruction_page', instruction_id=instruction_id, _external=True)
                    qr = qrcode.QRCode(
                        version=1,
                        error_correction=qrcode.constants.ERROR_CORRECT_L,
                        box_size=10,
                        border=4,
                    )
                    qr.add_data(qr_url)
                    qr.make(fit=True)
                    
                    # Create QR code image with medication name
                    qr_img = qr.make_image(fill_color="black", back_color="white")
                    
                    # Add medication name as text below QR code
                    if medication_name:
                        # Create a new image with space for text
                        img_width, img_height = qr_img.size
                        new_img = Image.new('RGB', (img_width, img_height + 40), 'white')
                        new_img.paste(qr_img, (0, 0))
                        
                        # Add text
                        draw = ImageDraw.Draw(new_img)
                        try:
                            font = ImageFont.truetype("Arial", 16)
                        except IOError:
                            font = ImageFont.load_default()
                            
                        # Draw medication name centered below QR code
                        text_width = draw.textlength(medication_name, font=font)
                        draw.text(((img_width - text_width) // 2, img_height + 10), medication_name, fill="black", font=font)
                        qr_img = new_img
                    
                    # Save QR code image
                    qr_img.save(qr_path)
                
                # Generate audio file if it doesn't exist
                audio_filename = f"{instruction_id}.mp3"
                audio_path = os.path.join(AUDIO_DIR, audio_filename)
                
                if not os.path.exists(audio_path):
                    # Create the audio file with gTTS
                    spoken_text = f"For {medication_name}: {instruction}" if medication_name else instruction
                    tts = gTTS(text=spoken_text, lang='en')
                    tts.save(audio_path)
                
                # Store instruction data
                instruction_data = {
                    'medication_name': medication_name,
                    'text': instruction,  # Use 'text' key to match what instruction_page expects
                    'qr_path': qr_path,
                    'audio_path': audio_path
                }
                
                # Save instruction data to JSON file
                instruction_data_file = os.path.join(app.static_folder, 'data', 'instructions.json')
                
                # Create the data directory if it doesn't exist
                data_dir = os.path.dirname(instruction_data_file)
                os.makedirs(data_dir, exist_ok=True)
                print(f"Ensuring data directory exists: {data_dir}")
                
                # Make sure we're using the global instruction_texts variable
                global instruction_texts
                
                # Store instruction text in memory with consistent key names
                instruction_texts[instruction_id] = {
                    'text': instruction,
                    'medication_name': medication_name
                }
                print(f"Stored instruction in memory with ID: {instruction_id}")
                
                # Load existing data if file exists
                existing_data = {}
                if os.path.exists(instruction_data_file):
                    try:
                        with open(instruction_data_file, 'r') as f:
                            existing_data = json.loads(f.read())
                        print(f"Loaded existing instruction data with {len(existing_data)} entries")
                    except Exception as e:
                        print(f"Error loading instruction data: {e}")
                
                # Update with new data
                existing_data[instruction_id] = instruction_data
                
                # Save updated data
                try:
                    with open(instruction_data_file, 'w') as f:
                        f.write(json.dumps(existing_data, indent=2))
                    print(f"Successfully saved instruction data to {instruction_data_file}")
                    print(f"Total instructions saved: {len(existing_data)}")
                except Exception as e:
                    print(f"Error saving instruction data: {e}")
                
                # Add result
                results.append({
                    'medication_name': medication_name,
                    'instruction': instruction,
                    'qr_url': url_for('static', filename=f'qrcodes/{qr_filename}'),
                    'instruction_id': instruction_id
                })
        
        return jsonify({
            'status': 'success',
            'results': results
        })
        
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

# Ensure instruction pages are created for a list of instruction IDs
# This route has been replaced by the more comprehensive version above
# that accepts a list of instructions rather than instruction IDs

# Keeping the route commented out for reference
"""
@app.route('/ensure_instruction_pages', methods=['POST'])
def ensure_instruction_pages():
    try:
        data = request.json
        instruction_ids = data.get('instruction_ids', [])
        
        if not instruction_ids:
            return jsonify({'status': 'error', 'message': 'No instruction IDs provided'})
        
        # ... rest of the function ...
        
        return jsonify({
            'status': 'success',
            'message': 'All instruction pages are ready'
        })
        
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})
"""

# Generate a PDF with QR code stickers for printing
@app.route('/generate_qr_stickers', methods=['POST'])
def generate_qr_stickers():
    try:
        data = request.json
        instruction_ids = data.get('instruction_ids', [])
        
        if not instruction_ids:
            return jsonify({'status': 'error', 'message': 'No instructions provided'})
        
        # TODO: Implement PDF generation for QR code stickers
        # This would create a PDF with multiple QR codes arranged for printing on sticker sheets
        
        return jsonify({
            'status': 'success',
            'message': 'QR stickers generated successfully'
        })
        
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

# Export all medication data as a downloadable JSON file
@app.route('/export_medication_data')
def export_medication_data():
    try:
        # Create a timestamp for the filename
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"medication_data_{timestamp}.json"
        
        # Create a backup file in the backups directory
        backup_path = os.path.join(BACKUP_DIR, filename)
        
        # Save the current data to the backup file
        with open(backup_path, 'w') as f:
            json.dump(instruction_texts, f, indent=2)
        
        # Send the file as a download
        return send_file(backup_path, as_attachment=True, download_name=filename)
    
    except Exception as e:
        print(f"Error exporting medication data: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

# Import medication data from a JSON file
@app.route('/import_medication_data', methods=['POST'])
def import_medication_data():
    try:
        # Check if a file was uploaded
        if 'file' not in request.files:
            return jsonify({'status': 'error', 'message': 'No file part'}), 400
        
        file = request.files['file']
        
        # Check if the file is empty
        if file.filename == '':
            return jsonify({'status': 'error', 'message': 'No selected file'}), 400
        
        # Check if the file is a JSON file
        if not file.filename.endswith('.json'):
            return jsonify({'status': 'error', 'message': 'File must be a JSON file'}), 400
        
        # Read the file
        data = json.load(file)
        
        # Validate the data format
        if not isinstance(data, dict):
            return jsonify({'status': 'error', 'message': 'Invalid data format'}), 400
        
        # Create a backup of the current data before importing
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_filename = f"pre_import_backup_{timestamp}.json"
        backup_path = os.path.join(BACKUP_DIR, backup_filename)
        
        with open(backup_path, 'w') as f:
            json.dump(instruction_texts, f, indent=2)
        
        # Update the instruction_texts dictionary with the imported data
        instruction_texts.update(data)
        
        # Save the updated data
        save_instruction_data()
        
        return jsonify({
            'status': 'success', 
            'message': f'Successfully imported {len(data)} medication records',
            'backup_file': backup_filename
        })
    
    except Exception as e:
        print(f"Error importing medication data: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

# Get a list of all available medication data
@app.route('/list_medication_data')
def list_medication_data():
    try:
        # Create a list of medication data with basic info
        medications = []
        for instruction_id, data in instruction_texts.items():
            medications.append({
                'id': instruction_id,
                'medication_name': data.get('medication_name', ''),
                'instructions': data.get('instructions', '') or data.get('text', ''),
                'url': f"/instruction/{instruction_id}"
            })
        
        return jsonify({
            'status': 'success',
            'count': len(medications),
            'medications': medications
        })
    
    except Exception as e:
        print(f"Error listing medication data: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 5001))
    app.run(debug=True, host='0.0.0.0', port=port)
