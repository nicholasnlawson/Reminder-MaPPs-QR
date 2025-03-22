# Medication Chart Generator Flask Application

This Flask application serves as an interface for the Medication Chart Generator HTML program. It preserves the original HTML file exactly as it is while providing a Flask UI wrapper around it.

## Setup and Installation

1. Create a virtual environment (optional but recommended):
   ```
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

2. Install the required dependencies:
   ```
   pip install -r requirements.txt
   ```

3. Run the application:
   ```
   python app.py
   ```

4. Open your web browser and navigate to:
   ```
   http://127.0.0.1:5004
   ```

## Features

- **Flask UI**: The original HTML embedded within a Flask UI wrapper
- **Single Warning Banner**: Only displays the warning message once
- **Clean Interface**: Provides a clean and professional interface for the Medication Chart Generator
- **Patient Information Leaflets**: Generate customized information leaflets for patients about their medications
- **Easy Read Pictorials**: Create visual guides for medication administration using simple pictograms

## Original Functionality (Preserved)

- Generate prescriptions from discharge letters
- Create reminder charts for medication schedules
- Generate MAR (Medication Administration Record) charts
- Adjust font sizes
- Delete and manage rows in the generated charts
- Print functionality for all generated documents

## New Functionality

### Patient Information Leaflets
Generate patient-friendly information leaflets:
- provided by MaPPS

### Easy Read Pictorials
Create visual guides for medications:
- provided by MaPPs


