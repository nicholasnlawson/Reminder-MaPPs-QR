// BNF Cautionary and Advisory Labels
let bnfLabelsData = {}; // Will store the label text for each label number
let drugFormulationsData = []; // Will store drug-formulation to label mappings
let drugAliases = {}; // Will store drug name aliases
let formulationAliases = {}; // Will store formulation aliases
let formulationCategories = {}; // Will store formulation categories

// Add error state tracking
let dataLoadingState = {
    bnfLabels: false,
    drugFormulations: false,
    drugAliases: false,
    formulationAliases: false
};

// Load BNF labels data
fetch('/static/bnf_labels.json')
  .then(response => {
    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }
    return response.json();
  })
  .then(data => {
    // Process the data into the expected flat structure
    const labels = {};
    if (data.cautionary_advisory_labels) {
      data.cautionary_advisory_labels.forEach(label => {
        labels[label.label_number] = label.text;
      });
    }
    bnfLabelsData = labels;
    dataLoadingState.bnfLabels = true;
    console.log('BNF labels loaded:', Object.keys(bnfLabelsData).length);
  })
  .catch(error => {
    console.error('Error loading BNF labels:', error);
    dataLoadingState.bnfLabels = false;
  });

// Load drug formulations data
fetch('/static/drug_formulations.json')
  .then(response => {
    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }
    return response.json();
  })
  .then(data => {
    // Transform data to use all drug names and formulations
    drugFormulationsData = [];
    
    data.forEach(item => {
      if (item.name && Array.isArray(item.name) && item.name.length > 0) {
        // Create an entry for each name-formulation combination
        item.name.forEach(drugName => {
          // Handle different formulation formats
          const formulations = Array.isArray(item.formulation) ? item.formulation : [item.formulation];
          
          formulations.forEach(formulation => {
            drugFormulationsData.push({
              drug: drugName.toLowerCase(),
              formulation: formulation ? formulation : '',
              labels: item.label_number || []
            });
          });
        });
      }
    });
    
    dataLoadingState.drugFormulations = true;
    console.log('Drug formulations loaded:', drugFormulationsData.length);
  })
  .catch(error => {
    console.error('Error loading drug formulations:', error);
    dataLoadingState.drugFormulations = false;
  });

// Load drug aliases if available
fetch('/static/drug_aliases.json')
  .then(response => response.json())
  .then(data => {
    drugAliases = data;
    dataLoadingState.drugAliases = true;
    console.log('Drug aliases loaded:', Object.keys(drugAliases).length);
  })
  .catch(error => {
    console.log('Drug aliases file not found or error loading. Continuing without aliases.');
    dataLoadingState.drugAliases = false;
    drugAliases = {};
  });

// Load formulation aliases data and transform it
fetch('/static/formulation_aliases.json')
  .then(response => {
    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }
    return response.json();
  })
  .then(data => {
    // Transform data structure for easier access
    try {
      formulationAliases = {};
      formulationCategories = {};
      
      // Process the hierarchical structure
      for (const [routeKey, route] of Object.entries(data.formulations)) {
        for (const [categoryKey, category] of Object.entries(route)) {
          // For array values (direct list of aliases)
          if (Array.isArray(category)) {
            // Each alias in this category maps to the route/category
            category.forEach(alias => {
              formulationAliases[alias.toLowerCase()] = routeKey;
              
              // Store in categories for type checking
              if (!formulationCategories[routeKey]) {
                formulationCategories[routeKey] = {};
              }
              formulationCategories[routeKey][alias.toLowerCase()] = categoryKey;
            });
          } 
          // For object values (subcategories)
          else {
            for (const [subcategoryKey, aliases] of Object.entries(category)) {
              if (Array.isArray(aliases)) {
                aliases.forEach(alias => {
                  formulationAliases[alias.toLowerCase()] = routeKey;
                  
                  // Store the full category path
                  if (!formulationCategories[routeKey]) {
                    formulationCategories[routeKey] = {};
                  }
                  formulationCategories[routeKey][alias.toLowerCase()] = `${categoryKey}_${subcategoryKey}`;
                });
              }
            }
          }
        }
      }
      
      console.log('Formulation aliases processed successfully');
      dataLoadingState.formulationAliases = true;
    } catch (error) {
      console.error('Error processing formulation aliases:', error);
      dataLoadingState.formulationAliases = false;
    }
  })
  .catch(error => {
    console.error('Error loading formulation aliases:', error);
    dataLoadingState.formulationAliases = false;
    formulationAliases = {};
    formulationCategories = {};
  });

// Function to normalize drug name (remove case sensitivity, handle aliases)
function normalizeDrugName(name) {
  if (!name) return '';
  name = name.toLowerCase().trim();
  
  // Check if this drug has any aliases
  for (const [primaryDrug, aliases] of Object.entries(drugAliases)) {
    if (Array.isArray(aliases) && aliases.some(alias => name.includes(alias.toLowerCase()))) {
      return primaryDrug.toLowerCase();
    }
  }
  
  return name;
}

// Function to normalize formulation name and get its category
function normalizeFormulation(form) {
  if (!form) return { normalized: '', category: '', route: '' };
  form = form.toLowerCase().trim();
  
  // Find the longest matching alias
  let bestMatch = '';
  let bestCategory = '';
  let bestRoute = '';
  
  // First try exact matches
  if (formulationAliases[form]) {
    const route = formulationAliases[form];
    const category = formulationCategories[route][form];
    return { 
      normalized: form, 
      category: category,
      route: route
    };
  }
  
  // Find all words in the formulation
  const words = form.split(/\s+/);
  
  // Try multi-word matches in any order
  for (const [alias, route] of Object.entries(formulationAliases)) {
    const aliasWords = alias.split(/\s+/);
    
    // Check if all alias words are in the formulation
    const allWordsMatch = aliasWords.every(word => words.includes(word));
    
    if (allWordsMatch && alias.length > bestMatch.length) {
      bestMatch = alias;
      bestRoute = route;
      bestCategory = formulationCategories[route][alias];
    }
  }
  
  if (bestMatch) {
    return { 
      normalized: bestMatch, 
      category: bestCategory,
      route: bestRoute
    };
  }
  
  // No match found, return the original
  return { 
    normalized: form, 
    category: '',
    route: ''
  };
}

// Helper function to match formulations
function matchFormulation(medicationForm, entryForm) {
  if (!medicationForm || !entryForm) {
    return { matched: false, score: 0 };
  }
  
  // Normalize both to lowercase
  medicationForm = medicationForm.toLowerCase().trim();
  entryForm = entryForm.toLowerCase().trim();
  
  // Exact match is always best
  if (medicationForm === entryForm) {
    return { matched: true, score: entryForm.length * 2 }; // Double score for exact match
  }
  
  // Get normalized forms and categories
  const medFormInfo = normalizeFormulation(medicationForm);
  const entryFormInfo = normalizeFormulation(entryForm);
  
  console.log(`Matching formulations: "${medicationForm}" (${medFormInfo.category}) vs "${entryForm}" (${entryFormInfo.category})`);
  
  // If both have categories and they're the same category, it's a match
  if (medFormInfo.category && entryFormInfo.category && 
      medFormInfo.category === entryFormInfo.category) {
    return { matched: true, score: Math.max(medFormInfo.normalized.length, entryFormInfo.normalized.length) };
  }
  
  // Special case: "tablet" and "oral tablet" should match
  if ((medicationForm === 'tablet' && entryForm === 'oral tablet') ||
      (medicationForm === 'oral tablet' && entryForm === 'tablet')) {
    return { matched: true, score: 5 };
  }
  
  // If they're in different categories that both contain "tablet", they shouldn't match
  // For example, "tablet" vs "chewable_tablet" shouldn't match
  if (medFormInfo.category && entryFormInfo.category && 
      medFormInfo.category.includes('tablet') && entryFormInfo.category.includes('tablet') &&
      medFormInfo.category !== entryFormInfo.category) {
    return { matched: false, score: 0 };
  }
  
  // For non-tablet formulations, allow partial matches with lower scores
  if (!medicationForm.includes('tablet') && !entryForm.includes('tablet')) {
    if (medicationForm.includes(entryForm)) {
      return { matched: true, score: entryForm.length };
    }
    if (entryForm.includes(medicationForm)) {
      return { matched: true, score: medicationForm.length };
    }
  }
  
  // No match
  return { matched: false, score: 0 };
}

// Helper function to handle combination medications (drug1/drug2 format)
function matchDrugName(medicationName, entryDrug) {
  // Normalize both strings to lowercase
  medicationName = medicationName.toLowerCase();
  entryDrug = entryDrug.toLowerCase();
  
  // Check for exact match first
  if (medicationName === entryDrug) {
    return { matched: true, score: entryDrug.length };
  }
  
  // Check if this is a combination medication with slash
  const hasMedicationSlash = medicationName.includes('/');
  const hasEntrySlash = entryDrug.includes('/');
  
  // If both have slashes, check if they match in either order
  if (hasMedicationSlash && hasEntrySlash) {
    const medParts = medicationName.split('/').map(p => p.trim());
    const entryParts = entryDrug.split('/').map(p => p.trim());
    
    // Check if all parts match in any order
    const allPartsMatch = medParts.every(mp => 
      entryParts.some(ep => ep === mp || ep.includes(mp) || mp.includes(ep))
    );
    
    if (allPartsMatch) {
      return { matched: true, score: entryDrug.length };
    }
  }
  
  // Handle case where medication name has slash but entry doesn't
  if (hasMedicationSlash) {
    const medParts = medicationName.split('/').map(p => p.trim());
    // If any individual part matches the entry
    if (medParts.some(mp => mp === entryDrug || mp.includes(entryDrug) || entryDrug.includes(mp))) {
      return { matched: true, score: entryDrug.length };
    }
  }
  
  // Handle case where entry has slash but medication doesn't
  if (hasEntrySlash) {
    const entryParts = entryDrug.split('/').map(p => p.trim());
    // If entry matches any individual part
    if (entryParts.some(ep => ep === medicationName || ep.includes(medicationName) || medicationName.includes(ep))) {
      return { matched: true, score: Math.max(...entryParts.map(p => p.length)) };
    }
  }
  
  // Check if one contains the other (with word boundaries)
  if (medicationName.includes(` ${entryDrug} `) || 
      medicationName.startsWith(`${entryDrug} `) || 
      medicationName.endsWith(` ${entryDrug}`) ||
      entryDrug.includes(` ${medicationName} `) || 
      entryDrug.startsWith(`${medicationName} `) || 
      entryDrug.endsWith(` ${medicationName}`)) {
    return { matched: true, score: entryDrug.length };
  }
  
  // Check for partial inclusion
  if (medicationName.includes(entryDrug) || entryDrug.includes(medicationName)) {
    return { matched: true, score: entryDrug.length };
  }
  
  // No match
  return { matched: false, score: 0 };
}

// BNF label integration temporarily disabled by user request
function getBNFLabels(medication) {
  return [];
}

function addBNFWarnings(medication) {
  return '';
}

// Function to format BNF labels HTML
function formatBNFLabelsHTML(labelNumbers) {
  try {
    if (!labelNumbers || labelNumbers.length === 0) return '';
    if (!bnfLabelsData || Object.keys(bnfLabelsData).length === 0) return '';
    let html = "<br><strong>Cautionary and Advisory Labels:</strong><ul>";
    labelNumbers.forEach(labelNum => {
      const labelText = bnfLabelsData[labelNum];
      if (labelText) {
        html += `<li>${labelText}</li>`;
      } else {
        html += `<li>Label ${labelNum} not found</li>`;
      }
    });
    html += "</ul>";
    return html;
  } catch (err) {
    console.error("Error in formatBNFLabelsHTML for:", labelNumbers, err);
    return '';
  }
}

// Add validation function
function isDataLoaded() {
  return dataLoadingState.bnfLabels && dataLoadingState.drugFormulations;
}

// Initialize data loading when page loads
document.addEventListener('DOMContentLoaded', function() {
  console.log('BNF labels module loaded');
  
  // Function was referenced but not defined, adding it here
  function loadBNFData() {
    // All data loading is already handled by the fetch calls at the top of the file
    console.log('BNF data loading status check initiated');
    
    // Check if data is already loaded
    setTimeout(function checkDataLoaded() {
      if (isDataLoaded()) {
        console.log('All required BNF data is loaded');
      } else {
        console.log('Waiting for BNF data to load...');
        setTimeout(checkDataLoaded, 500); // Check again in 500ms
      }
    }, 500);
  }
  
  loadBNFData();
  
  // Store the original function if it exists
  if (typeof window.addTriggerPhrases === 'function') {
    const originalAddTriggerPhrases = window.addTriggerPhrases;
    
    // Override the function
    window.addTriggerPhrases = function(medication, isMAR = false) {
      // Call the original function first
      let additionalInfo = originalAddTriggerPhrases(medication);
      
      // Only add BNF cautionary and advisory labels for MAR charts
      if (isMAR) {
        try {
          const bnfLabels = getBNFLabels(medication);
          if (bnfLabels && bnfLabels.length > 0) {
            additionalInfo += formatBNFLabelsHTML(bnfLabels);
          }
        } catch (error) {
          console.error('Error adding BNF labels:', error);
        }
      }
      
      return additionalInfo;
    };
    
    console.log('Enhanced addTriggerPhrases function with BNF labels');
  } else {
    console.error('addTriggerPhrases function not found');
  }
});
