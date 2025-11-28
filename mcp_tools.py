import json
import os
from typing import Optional
from database_setup import create_db_session, Project, ConfigurableAudit, CustomYL2Query, Audit, AuditPrompt
from utils import remove_excluded_fields

# --- Security Configuration ---
# Get the absolute path of the project's root directory
PROJECT_ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__)))

# --- Session State ---
# A simple in-memory dictionary to hold session-specific data.
# This is cleared when the user starts a new session.
SESSION_STATE = {}

def clear_session_state():
    """Clears the current session state."""
    global SESSION_STATE
    SESSION_STATE = {}
    print("--- MCP session state cleared. ---")

def set_session_tenant(tenant_project_id: str) -> str:
    """
    Sets the tenant (project) to be used for all subsequent commands in the
    current session. This avoids having to specify the tenant ID for every action.

    Args:
        tenant_project_id: The project ID of the tenant to set as the default.

    Returns:
        A confirmation message indicating success or an error message if the
        tenant ID is not found.
    """
    db_session = create_db_session()
    try:
        project = db_session.query(Project).filter_by(id=tenant_project_id).first()
        if not project:
            return f"Error: Tenant with project ID '{tenant_project_id}' not found."
        
        SESSION_STATE['tenant_project_id'] = tenant_project_id
        return f"Session tenant set to '{project.display_name} ({tenant_project_id})'. All subsequent commands will use this tenant."
    finally:
        db_session.close()


def list_tenants() -> str:
    """
    Lists all configured tenants (projects) in the database.

    Returns:
        A JSON string representing a list of tenant objects, each containing
        the project_id and project_name.
    """
    db_session = create_db_session()
    try:
        projects = db_session.query(Project).all()
        if not projects:
            return "No tenants found in the database."
        
        tenant_list = [
            {"project_id": p.id, "project_name": p.display_name}
            for p in projects
        ]
        return json.dumps(tenant_list, indent=2)
    finally:
        db_session.close()

def list_audits() -> str:
    """
    Lists all available audits, including standard configurable audits and
    custom YL2 queries.

    Returns:
        A JSON string representing a list of audit objects, each containing
        the audit's name and its category.
    """
    db_session = create_db_session()
    try:
        audits = []
        
        # Fetch configurable audits
        configurable_audits = db_session.query(ConfigurableAudit).all()
        for audit in configurable_audits:
            audits.append({"name": audit.name, "category": audit.category})
            
        # Fetch custom YL2 queries
        custom_queries = db_session.query(CustomYL2Query).all()
        for query in custom_queries:
            audits.append({"name": query.name, "category": query.category})
            
        if not audits:
            return "No audits found."
            
        return json.dumps(audits, indent=2)
    finally:
        db_session.close()

def get_latest_audit_results(audit_name: str, tenant_project_id: Optional[str] = None) -> str:
    """
    Retrieves the results of the last successful run for a specific audit.
    If tenant_project_id is not provided, it uses the tenant set for the current session.
    This tool automatically applies any field exclusions configured in the LLM settings.

    Args:
        audit_name: The name of the audit to retrieve results for.
        tenant_project_id: (Optional) The project ID of the tenant. Defaults to the session tenant.

    Returns:
        The full JSON string of the audit results if found (with exclusions applied),
        otherwise an error message.
    """
    # Determine the tenant ID to use
    project_id_to_use = tenant_project_id or SESSION_STATE.get('tenant_project_id')
    
    if not project_id_to_use:
        return "Error: No tenant specified. Please either provide a 'tenant_project_id' or set a default tenant for the session using the 'set_session_tenant' tool."

    db_session = create_db_session()
    try:
        latest_audit = db_session.query(Audit).filter_by(
            tenant_project_id=project_id_to_use,
            audit_name=audit_name,
            status="Success"
        ).order_by(Audit.run_timestamp.desc()).first()

        if not latest_audit:
            return f"No successful audit run found for audit '{audit_name}' on tenant '{project_id_to_use}'."
        
        # Load the raw results
        results_data = json.loads(latest_audit.results)

        # Fetch exclusion settings for this audit
        prompt_settings = db_session.query(AuditPrompt).filter_by(audit_name=audit_name).first()
        
        if prompt_settings and prompt_settings.excluded_fields:
            excluded_fields = [field.strip() for field in prompt_settings.excluded_fields.split(',') if field.strip()]
            print(f"--- Applying exclusions for '{audit_name}': {excluded_fields} ---")
            # Apply the exclusions
            filtered_data = remove_excluded_fields(results_data, excluded_fields)
            # Return the filtered data as a JSON string
            return json.dumps(filtered_data, indent=2)
        else:
            # If no exclusions, return the original results string
            return latest_audit.results
    finally:
        db_session.close()

def read_local_file(file_path: str) -> str:
    """
    Reads the content of a local file, but only if it's within the project directory.
    This tool is sandboxed and cannot access files outside the application's root folder.

    Args:
        file_path: The relative path to the file within the project directory.

    Returns:
        The content of the file as a string, or an error message if the file
        is not found, is outside the allowed directory, or cannot be read.
    """
    try:
        # --- Security Check ---
        # 1. Construct the full, absolute path for the requested file
        full_path = os.path.realpath(os.path.join(PROJECT_ROOT, file_path))

        # 2. Check if the resolved path is still within the project's root directory
        if not full_path.startswith(PROJECT_ROOT):
            return f"Error: Access denied. Path '{file_path}' is outside the allowed project directory."

        # --- File Reading ---
        if not os.path.exists(full_path):
            return f"Error: File not found at '{file_path}'."
        
        if not os.path.isfile(full_path):
            return f"Error: Path '{file_path}' is a directory, not a file."

        with open(full_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        return content

    except FileNotFoundError:
        return f"Error: File not found at '{file_path}'."
    except Exception as e:
        return f"An unexpected error occurred while reading the file: {e}"


# --- Tool Registry ---
# A dictionary that maps tool names (strings) to the actual function objects.
# This is used by the direct tool execution endpoint.
TOOL_REGISTRY = {
    "list_tenants": list_tenants,
    "list_audits": list_audits,
    "get_latest_audit_results": get_latest_audit_results,
    "set_session_tenant": set_session_tenant,
    "read_local_file": read_local_file,
}
