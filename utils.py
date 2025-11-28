
import time
import random
import functools
import difflib
import datetime
import io
import csv
from google.api_core import exceptions as google_exceptions
import requests
import os
import json
from typing import Any
import google.generativeai as genai
from google.auth import default as google_auth_default
from google.generativeai.types import HarmCategory, HarmBlockThreshold
import configparser
from google.oauth2 import service_account
from google.auth import default as google_auth_default

def get_gcp_credentials():
    """
    Reads the config.ini file and returns the appropriate GCP credentials.
    """
    config = configparser.ConfigParser()
    # Ensure the path is correct, assuming config.ini is in the root of the project
    config_path = os.path.join(os.path.dirname(__file__), 'config.ini')
    
    if not os.path.exists(config_path):
        print("--- config.ini not found, falling back to Application Default Credentials (ADC). ---")
        credentials, project = google_auth_default()
        return credentials

    config.read(config_path)
    
    auth_method = config.get('auth', 'method', fallback='ADC')

    if auth_method == 'SERVICE_ACCOUNT':
        key_path = config.get('auth', 'service_account_path', fallback=None)
        if not key_path or not os.path.exists(key_path):
            raise FileNotFoundError(
                "Authentication method is SERVICE_ACCOUNT, but 'service_account_path' is missing, invalid, or the file does not exist in config.ini."
            )
        print(f"--- Using Service Account credentials from: {key_path} ---")
        credentials = service_account.Credentials.from_service_account_file(key_path)
    else: # Default to ADC
        print("--- Using Application Default Credentials (ADC). ---")
        credentials, project = google_auth_default()

    return credentials

def retry_with_backoff(retries=5, backoff_in_seconds=1):
    """
    A decorator for retrying a function with exponential backoff.
    Handles Google API exceptions and requests HTTP errors.
    """
    def rwb(f):
        @functools.wraps(f)
        def wrapper(*args, **kwargs):
            x = 0
            while True:
                try:
                    result = f(*args, **kwargs)
                    
                    # For requests-based functions that return a dict
                    if isinstance(result, dict) and "error" in result:
                        # Check for 429 status in the details
                        details = result.get("details", "")
                        if "429" in str(result.get("error", "")):
                            raise requests.exceptions.HTTPError(f"Status 429: {details}")

                    return result

                except (google_exceptions.ResourceExhausted, google_exceptions.ServiceUnavailable) as e:
                    if x == retries:
                        raise e

                    sleep_time = (backoff_in_seconds * 2**x) + random.uniform(0, 1)
                    print(f"!!! RETRYING: Rate limit exceeded for function '{f.__name__}'. Retrying in {sleep_time:.2f} seconds...")
                    time.sleep(sleep_time)
                    x += 1
                
                except requests.exceptions.HTTPError as e:
                    if "429" not in str(e):
                        raise e # Re-raise if not a 429 error
                    
                    if x == retries:
                        raise e

                    sleep_time = (backoff_in_seconds * 2**x) + random.uniform(0, 1)
                    print(f"!!! RETRYING: Rate limit exceeded for function '{f.__name__}'. Retrying in {sleep_time:.2f} seconds...")
                    time.sleep(sleep_time)
                    x += 1

                except Exception as e:
                    # For other exceptions, fail immediately
                    raise e
        return wrapper
    return rwb

def remove_excluded_fields(data: Any, excluded_fields: list[str]) -> Any:
    """
    Recursively removes specified fields from a dictionary or a list of dictionaries.
    """
    if isinstance(data, dict):
        return {
            key: remove_excluded_fields(value, excluded_fields)
            for key, value in data.items()
            if key not in excluded_fields
        }
    elif isinstance(data, list):
        return [remove_excluded_fields(item, excluded_fields) for item in data]
    else:
        return data

def chunk_data_by_tokens(data_string: str, model: genai.GenerativeModel, max_tokens_per_chunk: int) -> list[str]:
    """
    Splits a string into chunks based on the number of tokens, as counted by the provided model.
    This is a simplified implementation that splits by lines, which is safer for JSON.
    """
    chunks = []
    current_chunk_lines = []
    current_token_count = 0
    
    lines = data_string.splitlines(keepends=True)

    for line in lines:
        try:
            line_token_count = model.count_tokens(line).total_tokens
        except Exception:
            # Fallback for lines that might cause counting errors (e.g., empty or unusual content)
            line_token_count = len(line) // 4

        if current_token_count + line_token_count > max_tokens_per_chunk:
            # Finalize the current chunk if it's not empty
            if current_chunk_lines:
                chunks.append("".join(current_chunk_lines))
            # Start a new chunk with the current line
            current_chunk_lines = [line]
            current_token_count = line_token_count
        else:
            current_chunk_lines.append(line)
            current_token_count += line_token_count

    # Add the last remaining chunk
    if current_chunk_lines:
        chunks.append("".join(current_chunk_lines))

    return chunks

@retry_with_backoff(retries=5, backoff_in_seconds=2)
def _call_gemini_with_retry(model, full_prompt, safety_settings, generation_config=None):
    """A decorated wrapper to handle retries for the Gemini API call."""
    print(f"--- DEBUG: Calling Gemini with generation_config: {generation_config} ---") # Explicit logging
    return model.generate_content(full_prompt, safety_settings=safety_settings, generation_config=generation_config)

def generate_gemini_summary(celery_task, prompt, data, audit_name):
    """
    Sends data and a prompt to the Gemini API for summarization.
    It checks the token count of the data and decides whether to use a single API call
    or a map-reduce approach for very large datasets.
    """
    if not data or (isinstance(data, (list, dict)) and not any(data)):
        print(f"--- Skipping Gemini for '{audit_name}' because there is no data to process. ---")
        return "No data available for this audit. The API returned an empty result."

    try:
        # --- Read configuration ---
        config = configparser.ConfigParser()
        config_path = os.path.join(os.path.dirname(__file__), 'config.ini')
        config.read(config_path)

        model_name = config.get('gemini', 'model_name', fallback='gemini-1.5-flash')
        max_tokens_per_chunk = config.getint('gemini', 'max_tokens_per_chunk', fallback=900000)
        final_max_output_tokens = config.getint('gemini', 'final_max_output_tokens', fallback=8192)
        map_max_output_tokens = config.getint('gemini', 'map_max_output_tokens', fallback=2048)
        block_safety_filters = config.getboolean('gemini', 'block_safety_filters', fallback=True)

        model = genai.GenerativeModel(model_name)
        
        safety_settings = {}
        if block_safety_filters:
            print("--- DEBUG: Safety filters are being disabled based on config.ini. ---")
            safety_settings = {
                HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
            }

        # --- Logic to handle data type and count tokens ---
        try:
            deserialized_data = json.loads(data)
            data_string = json.dumps(deserialized_data, indent=2)
        except (json.JSONDecodeError, TypeError):
            data_string = data

        try:
            data_tokens = model.count_tokens(data_string).total_tokens
        except Exception as token_error:
            print(f"--- Warning: Could not count tokens for '{audit_name}'. Falling back to character length. Error: {token_error} ---")
            data_tokens = len(data_string) // 4

        template_prompt = _build_full_prompt(prompt, "[DATA_PLACEHOLDER]", audit_name)
        prompt_tokens = model.count_tokens(template_prompt).total_tokens - model.count_tokens("[DATA_PLACEHOLDER]").total_tokens
        total_input_tokens = data_tokens + prompt_tokens

        # --- Decide on single call vs. map-reduce ---
        final_gen_config = genai.GenerationConfig(max_output_tokens=final_max_output_tokens)

        if total_input_tokens < max_tokens_per_chunk:
            print(f"--- Processing '{audit_name}' in a single call ({total_input_tokens} tokens). ---")
            if celery_task:
                celery_task.update_state(state='PROGRESS', meta={'status': f"Sending data for '{audit_name}' to the LLM..."})
            
            full_prompt = _build_full_prompt(prompt, data_string, audit_name)
            response = _call_gemini_with_retry(model, full_prompt, safety_settings, generation_config=final_gen_config)
            return _handle_gemini_response(response, audit_name)
        
        else:
            print(f"--- Data for '{audit_name}' is large ({total_input_tokens} tokens). Starting map-reduce. ---")
            
            chunks = chunk_data_by_tokens(data_string, model, max_tokens_per_chunk - prompt_tokens) # Reserve space for prompt
            print(f"--- Split data into {len(chunks)} token-based chunks. ---")
            
            partial_summaries = []
            map_gen_config = genai.GenerationConfig(max_output_tokens=map_max_output_tokens)

            for i, chunk in enumerate(chunks):
                if celery_task:
                    celery_task.update_state(state='PROGRESS', meta={'status': f"Summarizing chunk {i+1}/{len(chunks)} for '{audit_name}'..."})
                
                chunk_prompt = "This is one part of a larger dataset. Please summarize the key findings from this specific chunk of data. Do not draw final conclusions, as you only have a partial view."
                full_prompt = _build_full_prompt(chunk_prompt, chunk, f"{audit_name} (Part {i+1})")
                response = _call_gemini_with_retry(model, full_prompt, safety_settings, generation_config=map_gen_config)
                partial_summaries.append(_handle_gemini_response(response, f"{audit_name} (Part {i+1})"))

            if celery_task:
                celery_task.update_state(state='PROGRESS', meta={'status': f"Creating final summary for '{audit_name}'..."})

            combined_summary_text = "\n\n---\n\n".join(partial_summaries)
            reduce_prompt = f"{prompt}\n\nThe following are several partial summaries... Your task is to synthesize them..."
            
            final_prompt = _build_full_prompt(reduce_prompt, combined_summary_text, audit_name)
            final_response = _call_gemini_with_retry(model, final_prompt, safety_settings, generation_config=final_gen_config)
            return _handle_gemini_response(final_response, audit_name)

    except Exception as e:
        import traceback
        error_message = f"An error occurred while generating the summary for '{audit_name}': {e}"
        print(f"--- {error_message}\n{traceback.format_exc()} ---")
        if celery_task:
            celery_task.update_state(state='FAILURE', meta={'status': error_message})
        return {"error": error_message}

def _build_full_prompt(prompt, data_string, audit_name):
    """Helper to construct the final prompt string."""
    current_time_utc = datetime.datetime.utcnow().isoformat()
    
    # Heuristically determine the data format for correct code fencing
    trimmed_data = data_string.strip()
    if trimmed_data.startswith(('{', '[')):
        data_section = f"```json\n{data_string}\n```"
    elif ',' in trimmed_data.splitlines()[0]: # Simple check for CSV header
        data_section = f"```csv\n{data_string}\n```"
    else:
        data_section = data_string # For plain text like diffs

    return (
        f"The current date and time is {current_time_utc} UTC.\n\n"
        f"{prompt}\n\n"
        f"Analyze the following data for the '{audit_name}' audit:\n\n"
        f"{data_section}"
    )

def _handle_gemini_response(response, audit_name):
    """Helper to robustly extract text from a Gemini response or handle errors."""
    try:
        # First, check if there are parts to access.
        if response.parts:
            return response.text
        else:
            # If there are no parts, it means the model was blocked or stopped early.
            finish_reason = response.candidates[0].finish_reason.name if response.candidates else 'UNKNOWN'
            safety_ratings = response.prompt_feedback.safety_ratings if response.prompt_feedback else 'N/A'
            error_details = (
                f"The response from the AI was blocked or incomplete. "
                f"Finish Reason: {finish_reason}. Safety Ratings: {safety_ratings}"
            )
            print(f"--- Gemini response for '{audit_name}' was empty. Details: {error_details} ---")
            return {"error": error_details}
    except ValueError as e:
        # This will catch the error from response.text if it still occurs,
        # or the one we just raised.
        finish_reason = response.candidates[0].finish_reason.name if response.candidates else 'UNKNOWN'
        safety_ratings = response.prompt_feedback.safety_ratings if response.prompt_feedback else 'N/A'
        error_details = (
            f"The response from the AI was blocked. "
            f"Finish Reason: {finish_reason}. Safety Ratings: {safety_ratings}"
        )
        print(f"--- Gemini response for '{audit_name}' was blocked. Details: {error_details} ---")
        return {"error": error_details}




def get_response_details(response_data):

    """Calculates the size and item count of a JSON response."""

    if not response_data:

        return 0, 0



    # Pretty-print the JSON to get a more realistic size, then encode to bytes

    size_bytes = len(json.dumps(response_data, indent=2).encode('utf-8'))

    item_count = 0



    if isinstance(response_data, dict):

        # Find the first key that holds a list of dictionaries (items)

        for key, value in response_data.items():

            if isinstance(value, list):

                item_count = len(value)

                break

        # If no list is found but the dict is not empty, consider it a single item

        if item_count == 0 and response_data:

            item_count = 1

    elif isinstance(response_data, list):

        item_count = len(response_data)



    return size_bytes, item_count


def generate_json_diff(json_str1: str, json_str2: str, fromfile='previous_run', tofile='latest_run') -> str:
    """
    Compares two JSON strings and returns a human-readable unified diff.
    """
    try:
        # Load JSON strings into Python objects to normalize them
        data1 = json.loads(json_str1)
        data2 = json.loads(json_str2)

        # Pretty-print the objects to create a consistent, comparable format
        # Sorting keys ensures that the order of keys doesn't create false differences
        formatted_str1 = json.dumps(data1, indent=2, sort_keys=True).splitlines()
        formatted_str2 = json.dumps(data2, indent=2, sort_keys=True).splitlines()

        # Generate the diff
        diff = difflib.unified_diff(
            formatted_str1,
            formatted_str2,
            fromfile=fromfile,
            tofile=tofile,
            lineterm='' # Avoid extra newlines in the output
        )

        # Join the diff lines into a single string
        diff_output = '\n'.join(diff)

        # If there's no difference, return a specific message
        if not diff_output:
            return "No differences found between the two audit runs."

        return diff_output

    except json.JSONDecodeError as e:
        return f"Error decoding JSON: {e}"
    except Exception as e:
        return f"An unexpected error occurred during diff generation: {e}"

def _extract_value_from_union(value_union: dict):
    """
    Helper function to extract the actual data from the SecOps "union field" object
    based on the documented possible value types.
    """
    
    # Priority list of simple, primitive-like types
    VALUE_KEYS = [
        'stringVal',
        'int64Val',
        'uint64Val',
        'doubleVal',
        'boolVal',
        'timestampVal',
        'bytesVal'
    ]

    # Check for simple types first
    for key in VALUE_KEYS:
        if key in value_union:
            return value_union[key]

    # --- Handle special and complex types ---
    
    # Handle null values
    if 'nullVal' in value_union and value_union['nullVal']:
        return None  # csv.writer correctly handles None as an empty field

    # Handle Date objects
    if 'dateVal' in value_union:
        date_obj = value_union.get('dateVal', {})
        # Format as YYYY-MM-DD for a standard CSV representation
        return f"{date_obj.get('year', 'YYYY')}-{date_obj.get('month', 'MM')}-{date_obj.get('day', 'DD')}"

    # Handle generic Proto objects
    if 'protoVal' in value_union:
        # Serialize the complex object to a JSON string.
        # The csv.writer will automatically quote this string if it
        # contains commas or other special characters.
        return json.dumps(value_union.get('protoVal'))
        
    # Fallback if no known value key is found
    return None

def convert_secops_json_to_csv(api_response: dict) -> str:
    """
    Converts a verbose, columnar Google SecOps API JSON response
    into a compact, row-oriented CSV string.
    
    Args:
        api_response (dict): The parsed JSON response from the API.
            
    Returns:
        str: A string containing the data in CSV format.
    """
    
    # Check for an empty or invalid response
    if 'results' not in api_response or not api_response['results']:
        return "" # Return an empty string if there are no results

    try:
        # 1. Extract Headers (Column Names)
        # e.g., ['product_event_type', 'email_address', 'total']
        headers = [item['column'] for item in api_response['results']]
        
        # 2. Extract Data (Column-wise)
        # This builds a list of lists, where each inner list is a full column.
        # e.g., [ 
        #         ['event_val_1', 'event_val_2'],  <-- Column 1
        #         ['email_val_1', 'email_val_2']   <-- Column 2
        #       ]
        columnar_data = []
        for item in api_response['results']:
            column_values = []
            # Use .get('values', []) to safely handle columns with no values
            for value_obj in item.get('values', []):
                value_union = value_obj.get('value', {})
                extracted_val = _extract_value_from_union(value_union)
                column_values.append(extracted_val)
            columnar_data.append(column_values)

        # 3. Transpose Columnar Data to Row Data
        # This is the key step to pivot the data.
        # zip(*columnar_data) turns:
        # [ ['a', 'b'], ['c', 'd'] ]
        # into:
        # [ ('a', 'c'), ('b', 'd') ]
        # Each tuple is now a complete row.
        rows = list(zip(*columnar_data))

        # 4. Write to an in-memory CSV file
        # io.StringIO creates a text buffer that acts like a file
        output = io.StringIO()
        
        # Pass the buffer to the csv.writer
        writer = csv.writer(output)
        
        # Write the header row
        writer.writerow(headers)
        
        # Write all the data rows
        if rows:
            writer.writerows(rows)
            
        # Get the final CSV string from the buffer
        return output.getvalue()

    except Exception as e:
        # Handle potential errors, e.g., malformed JSON
        print(f"Error converting JSON to CSV: {e}")
        return "" # Return empty string on failure


