import json

# This script is a one-time upgrade to add default prompt and exclusion fields
# to the default_audits.json file.

INPUT_FILE = 'default_audits.json'
OUTPUT_FILE = 'default_audits.json'

def get_default_prompt(audit_name):
    """Generates a generic, high-quality default prompt for a given audit."""
    return (
        f"Act as a security analyst. Provide a concise summary of the key findings from the audit data for '{audit_name}'. "
        "Use Markdown for formatting, including headers (e.g., '## Key Findings') and bullet points (e.g., '* Finding 1'). "
        "Focus on the most important insights, anomalies, or configuration details. "
        "Your response should be only the raw Markdown content. Do not use HTML tags and do not wrap the response in code fences (e.g., ```markdown)."
    )

try:
    with open(INPUT_FILE, 'r') as f:
        audits = json.load(f)

    print(f"Read {len(audits)} audits from '{INPUT_FILE}'.")

    for audit in audits:
        # Add the new fields if they don't already exist
        if 'prompt_text' not in audit:
            audit['prompt_text'] = get_default_prompt(audit['name'])
        if 'excluded_fields' not in audit:
            audit['excluded_fields'] = ""

    with open(OUTPUT_FILE, 'w') as f:
        json.dump(audits, f, indent=2)

    print(f"Successfully updated '{OUTPUT_FILE}' with default prompt and exclusion fields.")

except FileNotFoundError:
    print(f"Error: Input file '{INPUT_FILE}' not found.")
except json.JSONDecodeError:
    print(f"Error: Could not decode JSON from '{INPUT_FILE}'.")
except Exception as e:
    print(f"An unexpected error occurred: {e}")
