import json
import requests
from typing import Optional
from google.auth.transport.requests import AuthorizedSession
from database_setup import create_db_session, SecopsTenantConfig
from utils import retry_with_backoff, get_gcp_credentials

@retry_with_backoff(retries=3, backoff_in_seconds=2)
def make_api_request(project_id: str, audit_details: dict, base_url: str, parent_path: Optional[str] = None, max_pages: Optional[int] = None) -> dict:
    """
    Makes a generic, authenticated API request, handling pagination if configured.
    """
    db_session = create_db_session()
    try:
        print(f"--- ULTIMATE DEBUG: Received audit_details: {json.dumps(audit_details, indent=2)} ---")
        config = db_session.query(SecopsTenantConfig).filter_by(project_id=project_id).first()
        if not config:
            return {"error": "Configuration not found for this project."}

        auth_method = audit_details.get("auth_method", "GCP")
        method = audit_details.get("method", "GET")
        api_path = audit_details.get("api_path", "")
        json_data = audit_details.get("json_data")
        
        # Pagination settings from the audit configuration
        page_token_key = audit_details.get("pagination_token_key")
        results_key = audit_details.get("pagination_results_key")
        request_token_key = audit_details.get("pagination_request_token_key") or page_token_key
        page_size = audit_details.get("default_page_size")

        # Conditionally format the api_path only if the placeholder exists
        if "{parent}" in api_path:
            api_path = api_path.format(parent=parent_path)
        
        headers = {}
        session = requests.Session()

        # --- Authentication Logic ---
        if auth_method == "GCP":
            credentials = get_gcp_credentials()
            authed_session = AuthorizedSession(credentials)
        elif auth_method == "SOAR_API_KEY":
            if not config.soar_api_key:
                return {"error": "SOAR API Key is not configured."}
            headers['AppKey'] = config.soar_api_key
            authed_session = session
        elif auth_method == "BINDPLANE_API_KEY":
            if not config.bindplane_api_key:
                 return {"error": "BindPlane API Key is not configured."}
            headers['X-Bindplane-Api-Key'] = config.bindplane_api_key
            authed_session = session
        else:
            return {"error": f"Unknown auth method: {auth_method}"}

        # --- Request Execution with Pagination ---
        url = f"{base_url.rstrip('/')}/{api_path.lstrip('/')}"
        all_results = []
        next_page_token = None
        page_count = 0

        print(f"--- DEBUG: Starting API request for '{audit_details.get('name', 'N/A')}'. Pagination is {'ENABLED' if page_token_key else 'DISABLED'}. ---")

        while True:
            page_count += 1
            if max_pages and page_count > max_pages:
                print(f"--- DEBUG: Reached max_pages limit of {max_pages}. Stopping pagination. ---")
                break

            params = {}
            # Add page size to every request if it's specified
            if page_size:
                params['pageSize'] = page_size
            
            if next_page_token and request_token_key:
                print(f"--- DEBUG: Fetching page {page_count} with token '{next_page_token[:10]}...'. ---")
                params[request_token_key] = next_page_token
            else:
                print(f"--- DEBUG: Fetching page 1 (no token). ---")

            # Construct the full URL with parameters for logging purposes only
            query_string = '&'.join([f'{k}={v}' for k, v in params.items()])
            log_url = f"{url}?{query_string}" if query_string else url
            
            print(f"--- DEBUG: Requesting URL: {log_url} ---")
            # Make the request using the base URL and the params dictionary
            response = authed_session.request(method, url, params=params, json=json_data, headers=headers)
            response.raise_for_status()

            if response.status_code == 204 or not response.content:
                print("--- DEBUG: Received empty response. Stopping pagination. ---")
                break

            try:
                data = response.json()
            except json.JSONDecodeError:
                print("--- DEBUG: Response was not JSON. Stopping pagination. ---")
                if not all_results:
                    return {"result": response.text}
                break

            # --- Data Aggregation ---
            if results_key and results_key in data:
                results_on_page = data.get(results_key, [])
                if isinstance(results_on_page, list):
                    all_results.extend(results_on_page)
                    print(f"--- DEBUG: Aggregated {len(results_on_page)} results from page {page_count}. Total results: {len(all_results)}. ---")
                else:
                    print(f"--- DEBUG: Results key '{results_key}' did not point to a list. Returning single response. ---")
                    return data
            elif not page_token_key:
                print("--- DEBUG: No pagination key. Returning single response. ---")
                return data

            # --- Token Handling ---
            if page_token_key:
                next_page_token = data.get(page_token_key)
                if not next_page_token:
                    print("--- DEBUG: No next page token found. Pagination complete. ---")
                    break
                else:
                    print(f"--- DEBUG: Found next page token: '{next_page_token[:10]}...'. ---")
            else:
                break

        # After the loop, return the aggregated results
        if results_key:
            print(f"--- DEBUG: Returning final aggregated results with key '{results_key}'. ---")
            return {results_key: all_results}
        else:
            print("--- DEBUG: Returning fallback result. ---")
            return all_results[0] if len(all_results) == 1 else {"results": all_results}

    except requests.exceptions.HTTPError as e:
        try:
            error_details = e.response.json()
            error_message = error_details.get("error", {}).get("message", str(e))
        except (ValueError, AttributeError):
            error_message = str(e)
        return {"error": f"HTTP Error: {e.response.status_code}", "details": error_message}
    except Exception as e:
        return {"error": "An unexpected error occurred", "details": str(e)}
    finally:
        db_session.close()