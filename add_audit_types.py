import json

# This script is a one-time fix to add the 'audit_type_name' to the default audits file.

INPUT_FILE = 'default_audits.json'
OUTPUT_FILE = 'default_audits.json'

# Mapping from the old audit_type_id to the correct name
AUDIT_TYPE_MAP = {
    1: "Chronicle API",
    2: "Custom IAM",
    3: "Custom YL2", # This ID might not be in the current file, but is here for completeness
    4: "SOAR API",
    5: "BindPlane API"
}

try:
    with open(INPUT_FILE, 'r') as f:
        audits = json.load(f)

    print(f"Read {len(audits)} audits from '{INPUT_FILE}'.")

    for audit in audits:
        audit_type_id = audit.get('audit_type_id')
        if audit_type_id in AUDIT_TYPE_MAP:
            audit['audit_type_name'] = AUDIT_TYPE_MAP[audit_type_id]
        else:
            # Default to Chronicle API if the ID is unknown or missing
            audit['audit_type_name'] = "Chronicle API"
            print(f"Warning: Unknown audit_type_id '{audit_type_id}' for audit '{audit['name']}'. Defaulting to 'Chronicle API'.")

    with open(OUTPUT_FILE, 'w') as f:
        json.dump(audits, f, indent=2)

    print(f"Successfully updated '{OUTPUT_FILE}' with 'audit_type_name' fields.")

except FileNotFoundError:
    print(f"Error: Input file '{INPUT_FILE}' not found.")
except json.JSONDecodeError:
    print(f"Error: Could not decode JSON from '{INPUT_FILE}'.")
except Exception as e:
    print(f"An unexpected error occurred: {e}")
