/**
 * Medication Extractor
 * 
 * This file contains functions for extracting medication data from discharge letters.
 * It replicates the functionality from the original chartgenerator.html file but
 * makes it available as a standalone module that can be used in the Flask application.
 */

/**
 * Extract medication data from a discharge letter
 * 
 * @param {string} dischargeLetterText - The text of the discharge letter
 * @returns {Array} An array of medication objects
 */
function extractMedicationsFromDischargeLetter(dischargeLetterText) {
    console.log("Starting medication extraction from discharge letter");
    const startTrigger = "Medications Prescribed on Discharge";
    const endTriggers = [
        "Dose Changes:",
        "DOSE CHANGES:",
        "Medications Started in Hospital Comment:",
        "Medications Stopped in Hospital Comment:",
        "Take Home Medications Comment:",
        "Treatment recommendation (For GP):",
        "Information for the Community Pharmacy:",
        "TTO Completed by Ward Pharmacist?:",
        "Medications Authorised by::",
    ];

    // Find the start of the medication section
    const startIndex = dischargeLetterText.indexOf(startTrigger);
    console.log(`Start trigger '${startTrigger}' found at index: ${startIndex}`);
    if (startIndex === -1) {
        console.log("No medications section found in discharge letter");
        return []; // No medications found
    }

    // Find the end of the medication section
    let endIndex = dischargeLetterText.length;
    for (const trigger of endTriggers) {
        const triggerIndex = dischargeLetterText.indexOf(trigger, startIndex);
        if (triggerIndex !== -1 && triggerIndex < endIndex) {
            endIndex = triggerIndex;
        }
    }

    // Extract the medication section
    const medicationSection = dischargeLetterText
        .slice(startIndex + startTrigger.length, endIndex)
        .trim();
    
    console.log("Extracted medication section:", medicationSection);

    // Split the medication section into individual entries
    const medicationLines = medicationSection.split('\n');
    const medicationEntries = [];
    let currentEntry = '';
    let currentIndentedLines = [];
    
    // Process the lines to keep indented lines associated with the medication entry
    for (let i = 0; i < medicationLines.length; i++) {
        const line = medicationLines[i];
        // If the line starts with spaces and is not empty, it's an indented line
        if (line.match(/^\s+\S/) && line.trim() !== '') {
            currentIndentedLines.push(line);
        }
        // If the line doesn't start with spaces or is empty, it's a new entry
        else {
            // If we have a current entry, add it to the entries with its indented lines
            if (currentEntry) {
                medicationEntries.push({
                    entry: currentEntry,
                    indentedLines: currentIndentedLines
                });
                // Reset for the next entry
                currentIndentedLines = [];
            }
            // Start a new entry if the line is not empty
            if (line.trim() !== '') {
                currentEntry = line;
            } else {
                currentEntry = '';
            }
        }
    }
    
    // Add the last entry if there is one
    if (currentEntry) {
        medicationEntries.push({
            entry: currentEntry,
            indentedLines: currentIndentedLines
        });
    }
    
    const medications = [];

    for (const entryObj of medicationEntries) {
        const entry = entryObj.entry;
        const indentedLines = entryObj.indentedLines;
        let name,
            dosage,
            instructions,
            percentage = "";
        const medicationRegex =
            /^([^\[]+)\s*(?:(\d+(?:\.\d+)?%))?\s*\[(.*?)\],\s+(.*)/;
        const match = medicationRegex.exec(entry);

        if (match) {
            // Logic for medications with square brackets
            name = match[1].trim();
            percentage = match[2] || "";
            dosage = match[3];
            instructions = match[4];
            name =
                name + (percentage ? " " + percentage : "") + " [" + dosage + "]";
        } else {
            // Logic for medications without square brackets
            const parts = entry.split(",");
            if (parts.length >= 2) {
                name = parts[0].trim();
                dosage = name; // Use the full name as dosage for now
                instructions = parts.slice(1).join(",").trim();
            } else {
                // If the entry doesn't match either format, skip it
                continue;
            }
        }

        const strengthRegex =
            /(\d+(?:,\d+)?(?:\.\d+)?)\s*(\w+)?(?:\s*\/\s*(\d+(?:,\d+)?(?:\.\d+)?)\s*(\w+)?)?/i;
        const strengthMatch = strengthRegex.exec(dosage);
        let strength,
            strength1,
            strength2,
            strengthUnit,
            strengthVolume,
            strengthVolumeUnit;

        if (strengthMatch) {
            strength1 = parseFloat(strengthMatch[1].replace(/,/g, ""));
            strengthUnit = (strengthMatch[2] || "").toLowerCase();

            if (strengthMatch[3]) {
                strength2 = parseFloat(strengthMatch[3].replace(/,/g, ""));
                strengthVolumeUnit = strengthMatch[4]
                    ? strengthMatch[4].toLowerCase()
                    : null;
                if (strengthVolumeUnit === "ml") {
                    strength = strength1;
                    strengthVolume = strength2;
                } else {
                    strength = strength1 + strength2;
                    strengthVolume = 1;
                }
            } else {
                strength = strength1;
                strengthVolume = 1;
            }
        } else {
            strength = null;
            strengthUnit = null;
            strengthVolume = 1;
            strengthVolumeUnit = null;
        }

        const doseTabletRegex =
            /(\d+(?:\.\d+)?)\s*(half\s+(?:tab|tablet)|quarter\s+(?:tab|tablet)|tab|tablet)/i;
        const doseTabletMatch = doseTabletRegex.exec(instructions);
        let minDose, maxDose, doseUnit;
        if (doseTabletMatch) {
            const quantity = parseFloat(doseTabletMatch[1]);
            const tabletType = doseTabletMatch[2].toLowerCase();

            if (tabletType.includes("half")) {
                minDose = quantity / 2;
                maxDose = quantity / 2;
                doseUnit = "half tablet";
            } else if (tabletType.includes("quarter")) {
                minDose = quantity / 4;
                maxDose = quantity / 4;
                doseUnit = "quarter tablet";
            } else {
                minDose = quantity;
                maxDose = quantity;
                doseUnit = "tablet";
            }
        }

        const formRegex =
            /(?:tablet|sprays|spray|tabs|caplet|oral\s+solution|oral\s+son\.|capsule|tab|caps|cap|inhalator|patch|capsule\/tablet|inhaler|flexpen|cartridge|sach|sachet|cream|crm|ointment|Scalp Application|sudocrem|lotion|gel|liquid gel|nebule|nebules|nebs|amps|solution|syrup|suspension|oral solution|oral soln\.|liquid|elixir|linctus|s\/f oral soln\.|oral powder|drop|drops|lozenge|gum)/i;
        const formMatch = formRegex.exec(dosage);
        let form = formMatch ? formMatch[0].toLowerCase() : null;

        if (
            form === "device" &&
            (/fluticasone/i.test(dosage) ||
                /glycopyrronium\/formoterol\/budes/i.test(dosage))
        ) {
            form = "inhaler";
        }
        if (form === "sach") {
            form = "sachet";
        } else if (form === "tab") {
            form = "tablet";
        } else if (form === "cap") {
            form = "capsule";
        } else if (form === "oral powder") {
            form = "sachet";
        } else if (form === "drops") {
            form = "drop";
        } else if (form === "scalp application") {
            form = "cream";
        }

        const doseRangeRegex =
            /(\d+(?:,\d+)*(?:\.\d+)?)\s*(?:-\s*(\d+(?:,\d+)*(?:\.\d+)?))?\s*(\w+)?/i;
        const doseRangeMatch = doseRangeRegex.exec(instructions);
        minDose = doseRangeMatch
            ? parseFloat(doseRangeMatch[1].replace(/,/g, ""))
            : null;
        maxDose =
            doseRangeMatch && doseRangeMatch[2] !== undefined
                ? parseFloat(doseRangeMatch[2].replace(/,/g, ""))
                : minDose;
        doseUnit = doseRangeMatch
            ? doseRangeMatch[3]
                ? doseRangeMatch[3].toLowerCase()
                : "units"
            : null;

        if (instructions.toLowerCase().includes("see taper")) {
            minDose = null;
            maxDose = null;
            doseUnit = null;
        }

        if (!minDose || !maxDose) {
            const doseRegex = /(\d+(?:,\d+)*(?:\.\d+)?)\s*(\w+)/i;
            const doseMatch = doseRegex.exec(instructions);
            minDose = doseMatch
                ? parseFloat(doseMatch[1].replace(/,/g, ""))
                : null;
            maxDose = minDose;
            doseUnit = doseMatch ? doseMatch[2].toLowerCase() : null;
        }

        const doseQuantityRegex =
            /(\d+(?:\.\d+)?)\s+(tab|tablet|capsule|cap)/i;
        const doseQuantityMatch = doseQuantityRegex.exec(instructions);
        if (doseQuantityMatch) {
            minDose = parseFloat(doseQuantityMatch[1]);
            maxDose = minDose;
            doseUnit = doseQuantityMatch[2].toLowerCase();
            if (minDose === 0.5) {
                doseUnit = "half " + doseUnit;
                minDose = 1;
                maxDose = 1;
            }
        }

        if (
            minDose &&
            strength &&
            (form === "tablet" ||
                form === "capsule" ||
                form === "tab" ||
                form === "cap") &&
            doseUnit !== "tab" &&
            doseUnit !== "tablet" &&
            doseUnit !== "capsule" &&
            doseUnit !== "cap" &&
            doseUnit !== "half tab" &&
            doseUnit !== "half tablet" &&
            doseUnit !== "half capsule" &&
            doseUnit !== "half cap"
        ) {
            minDose = minDose / strength;
            maxDose = maxDose / strength;
        }

        const sprayCountRegex = /(\d+(?:\.\d+)?)\s*(?:spray|sprays)/i;
        const sprayCountMatch = sprayCountRegex.exec(instructions);
        const sprayCount = sprayCountMatch
            ? parseFloat(sprayCountMatch[1])
            : null;

        let isTaper =
            instructions.toLowerCase().includes("taper") ||
            instructions.toLowerCase().includes("see taper") ||
            entry.toLowerCase().includes("prescriber determined");

        let taperInstructions = null;
        if (isTaper) {
            const taperTableRegex =
                /Dose\s+Frequency\s+Days\s+Hours\s+From\s+Through\s*\n((?:.*\n?)*)/;
            const taperTableMatch = taperTableRegex.exec(entry);

            if (taperTableMatch) {
                taperInstructions = taperTableMatch[1].trim();
            }
        }
        if (name.toLowerCase().includes("scopoderm tts")) {
            const doseMatch = /(\d+(?:\.\d+)?)\s*mg/.exec(instructions);
            if (doseMatch) {
                minDose = maxDose = parseFloat(doseMatch[1]);
            } else {
                minDose = maxDose = 1; // Default to 1mg if no dose specified
            }
            strength = 1; // Each patch is 1mg
            strengthUnit = "mg";
            form = "patch";
        }

        // Extract frequency information
        let frequency = "";
        const frequencyRegex = /(once|twice|three times|four times|1 time|2 times|3 times|4 times)(?:\s+a\s+day|\s+daily|\s+every\s+day|\s+per\s+day)?/i;
        const frequencyMatch = frequencyRegex.exec(instructions);
        if (frequencyMatch) {
            frequency = frequencyMatch[0];
        } else if (instructions.toLowerCase().includes("daily")) {
            frequency = "once daily";
        } else if (instructions.toLowerCase().includes("twice a day")) {
            frequency = "twice a day";
        } else if (instructions.toLowerCase().includes("three times a day")) {
            frequency = "three times a day";
        } else if (instructions.toLowerCase().includes("four times a day")) {
            frequency = "four times a day";
        }

        // Extract timing information
        let timing = "";
        if (instructions.toLowerCase().includes("morning")) {
            timing += "morning ";
        }
        if (instructions.toLowerCase().includes("afternoon")) {
            timing += "afternoon ";
        }
        if (instructions.toLowerCase().includes("evening")) {
            timing += "evening ";
        }
        if (instructions.toLowerCase().includes("night") || instructions.toLowerCase().includes("bedtime")) {
            timing += "night ";
        }
        timing = timing.trim();

        // Extract with/without food information
        let withFood = "";
        if (instructions.toLowerCase().includes("with food") || 
            instructions.toLowerCase().includes("after food") || 
            instructions.toLowerCase().includes("after meals")) {
            withFood = "with food";
        } else if (instructions.toLowerCase().includes("without food") || 
                  instructions.toLowerCase().includes("before food") || 
                  instructions.toLowerCase().includes("on empty stomach")) {
            withFood = "without food";
        }

        // Extract purpose/condition information
        let condition = "";
        const conditionRegex = /for\s+([\w\s]+?)(?:\.|\,|$)/i;
        const conditionMatch = conditionRegex.exec(instructions);
        if (conditionMatch) {
            condition = conditionMatch[1].trim();
        }

        // Check if any indented lines match our trigger phrases for preselection
        let shouldPreselect = false;
        const triggerPhrases = ['Existing Med', 'New Med', 'Hospital Supply', 'GP to Review'];
        
        if (indentedLines && indentedLines.length > 0) {
            for (const line of indentedLines) {
                const trimmedLine = line.trim();
                for (const phrase of triggerPhrases) {
                    if (trimmedLine.startsWith(phrase)) {
                        shouldPreselect = true;
                        break;
                    }
                }
                if (shouldPreselect) break;
            }
        }

        const medicationObj = {
            name: name,
            dosage: dosage,
            instructions: instructions,
            strength: strength,
            strengthVolume: strengthVolume,
            strengthVolumeUnit: strengthVolumeUnit,
            strengthUnit: strengthUnit,
            form: form,
            minDose: minDose,
            maxDose: maxDose,
            doseUnit: doseUnit,
            sprayCount: sprayCount,
            frequency: frequency,
            timing: timing,
            withFood: withFood,
            condition: condition,
            shouldPreselect: shouldPreselect, // Add the preselection flag
            isPrn:
                (instructions.toLowerCase().includes("prn") ||
                instructions.toLowerCase().includes("when required") ||
                instructions.toLowerCase().includes("as required")) &&
                !isTaper, // Only mark as PRN if not a taper
            isTaper: isTaper,
            taperInstructions: taperInstructions,
            isOmitMon: instructions.toLowerCase().includes("omit mon"),
            isSomeDays:
                instructions.toLowerCase().includes("once a week") ||
                instructions.toLowerCase().includes("once week") ||
                instructions.toLowerCase().includes("twice a week") ||
                instructions.toLowerCase().includes("3 x week") ||
                instructions.toLowerCase().includes("6 days of week") ||
                instructions.toLowerCase().includes("every 72 hours") ||
                instructions.toLowerCase().includes("alternate") ||
                instructions.toLowerCase().includes("month") ||
                instructions.toLowerCase().includes("every 3 days") ||
                instructions.toLowerCase().includes("once only one"),
            isExcludedFromCharts: name.includes(
                "Stationery [Steroid Emergency Card]"
            ),
        };

        medications.push(medicationObj);
    }

    console.log(`Extracted ${medications.length} medications:`, medications);
    return medications;
}

// Export the function for use in other JavaScript files
if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
        extractMedicationsFromDischargeLetter
    };
}

// Expose medications to parent window for QR code generation
window.medications = [];
