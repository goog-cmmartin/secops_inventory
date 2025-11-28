# gcp_asset_inventory.py
#
# This script inventories resources in a Google Cloud environment using the
# Cloud Asset Inventory API. It can be configured to scan an entire
# organization, a specific folder, or a single project.
#
# Prerequisites:
# 1. A GCP Organization, Folder, or Project to scan.
# 2. Authentication configured. This can be either:
#    a) A Service Account with "Cloud Asset Viewer" and "Browser" roles granted
#       AT THE TARGET SCOPE (Organization, Folder, or Project). The Browser
#       role helps ensure lookup permissions for project/folder names.
#    b) Google Cloud SDK initialized with Application Default Credentials
#       (run `gcloud auth application-default login`).
# 3. The following Python libraries installed:
#    - google-cloud-asset
#    - google-api-python-client
# 4. The "Cloud Resource Manager API" must be enabled in a project in your org.

import os
import time
import re
import fnmatch
from google.cloud import asset_v1
from google.api_core import exceptions as google_exceptions
from googleapiclient import discovery
from database_setup import create_db_session, Organization, Folder, Project, init_db
from utils import get_gcp_credentials

def _get_project_display_name(project_id, crm_service, cache):
    """Looks up a project's display name using the v3 API, using a cache."""
    if project_id in cache:
        return cache[project_id]
    try:
        project = crm_service.projects().get(name=f"projects/{project_id}").execute()
        display_name = project.get("displayName", project_id)
        cache[project_id] = display_name
        return display_name
    except Exception as e:
        print(f"  [Warning] Could not look up project name for ID {project_id}: {e}")
        cache[project_id] = project_id
        return project_id

def _get_folder_display_name(folder_id, crm_service, cache):
    """Looks up a folder's display name using the v3 API, using a cache."""
    if folder_id in cache:
        return cache[folder_id]
    try:
        folder = crm_service.folders().get(name=f"folders/{folder_id}").execute()
        display_name = folder.get("displayName", folder_id)
        cache[folder_id] = display_name
        return display_name
    except Exception as e:
        print(f"  [Warning] Could not look up folder name for ID {folder_id}: {e}")
        cache[folder_id] = folder_id
        return folder_id

def populate_database(assets, service_filter, credentials):
    """
    Processes assets and populates the SQLite database.
    """
    init_db() # Ensure tables are created
    db_session = create_db_session()
    crm_service = discovery.build('cloudresourcemanager', 'v3', credentials=credentials, cache_discovery=False)
    
    # Caches for display names to reduce API calls
    project_name_cache = {}
    folder_name_cache = {}

    # Cache for DB objects within this session to prevent duplicates
    session_object_cache = {}

    assets_by_name = {asset.name: asset for asset in assets}
    
    projects_with_service = set()
    for asset in assets:
        if asset.asset_type == "serviceusage.googleapis.com/Service":
            service_name = asset.name.split('/')[-1]
            if fnmatch.fnmatch(service_name, service_filter):
                parent_project_resource = getattr(asset.resource, 'parent', None)
                if parent_project_resource:
                    projects_with_service.add(parent_project_resource)

    if not projects_with_service:
        print(f"No projects found with services matching filter: {service_filter}")
        db_session.close()
        return

    print("\n--- Populating Database ---")
    for project_resource in projects_with_service:
        project_match = re.search(r'projects/(\d+)', project_resource)
        if not project_match:
            continue
        
        project_id = project_match.group(1)
        
        # Get or create the Project object
        project_key = f"project-{project_id}"
        if project_key not in session_object_cache:
            project_obj = db_session.query(Project).filter_by(id=project_id).first()
            if not project_obj:
                project_name = _get_project_display_name(project_id, crm_service, project_name_cache)
                project_obj = Project(id=project_id, display_name=project_name)
                db_session.add(project_obj)
            session_object_cache[project_key] = project_obj
        project_obj = session_object_cache[project_key]

        parent_resource = getattr(assets_by_name.get(project_resource, {}).resource, 'parent', None)
        
        child_obj = project_obj
        while parent_resource:
            folder_match = re.search(r'folders/(\d+)', parent_resource)
            org_match = re.search(r'organizations/(\d+)', parent_resource)

            if folder_match:
                folder_id = folder_match.group(1)
                folder_key = f"folder-{folder_id}"

                if folder_key not in session_object_cache:
                    folder_obj = db_session.query(Folder).filter_by(id=folder_id).first()
                    if not folder_obj:
                        folder_name = _get_folder_display_name(folder_id, crm_service, folder_name_cache)
                        folder_obj = Folder(id=folder_id, display_name=folder_name)
                        db_session.add(folder_obj)
                    session_object_cache[folder_key] = folder_obj
                folder_obj = session_object_cache[folder_key]
                
                if isinstance(child_obj, Project):
                    child_obj.folder = folder_obj
                elif isinstance(child_obj, Folder):
                    child_obj.parent_folder = folder_obj

                child_obj = folder_obj
                parent_resource = getattr(assets_by_name.get(parent_resource, {}).resource, 'parent', None)

            elif org_match:
                org_id = org_match.group(1)
                org_key = f"org-{org_id}"

                if org_key not in session_object_cache:
                    org_obj = db_session.query(Organization).filter_by(id=org_id).first()
                    if not org_obj:
                        org_obj = Organization(id=org_id, display_name=f"Organization {org_id}")
                        db_session.add(org_obj)
                    session_object_cache[org_key] = org_obj
                org_obj = session_object_cache[org_key]
                
                if isinstance(child_obj, Folder):
                    child_obj.organization = org_obj
                break
            else:
                break
    
    db_session.commit()
    print("Database population complete.")
    db_session.close()

def print_hierarchical_report_from_db():
    """
    Queries the database and prints a hierarchical report.
    """
    db_session = create_db_session()
    print("\n--- Hierarchical Report from Database ---")
    
    for project in db_session.query(Project).all():
        print(f"\nProject: {project.display_name} (ID: {project.id})")
        
        parent_folder = project.folder
        indent = "  "
        while parent_folder:
            print(f"{indent}Parent Folder: {parent_folder.display_name} (ID: {parent_folder.id})")
            parent_folder = parent_folder.parent_folder
            indent += "  "
            if parent_folder and not parent_folder.parent_folder and parent_folder.organization:
                 print(f"{indent}Parent Organization: {parent_folder.organization.id}")


    db_session.close()

def get_gcp_assets(parent_scope, asset_types_filter=None):
    """
    Fetches GCP assets using the centrally configured credentials.
    """
    try:
        credentials = get_gcp_credentials()
        asset_client = asset_v1.AssetServiceClient(credentials=credentials)
    except Exception as e:
        print(f"Error initializing Google Cloud clients: {e}")
        return None, None

    request = {"parent": parent_scope, "content_type": asset_v1.ContentType.RESOURCE}
    if asset_types_filter:
        request["asset_types"] = asset_types_filter

    print(f"\nAttempting to list assets for scope: {parent_scope}\n")

    all_assets = []
    try:
        response = asset_client.list_assets(request=request)
        for asset in response:
            all_assets.append(asset)
        print(f"Successfully fetched {len(all_assets)} assets.")
        return all_assets, credentials
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return None, None

def main(organization_id: str):
    """
    Main function to run the asset discovery and database population.
    """
    ASSET_TYPE_FILTER = [
        "serviceusage.googleapis.com/Service",
        "cloudresourcemanager.googleapis.com/Folder",
        "cloudresourcemanager.googleapis.com/Project"
    ]
    SERVICE_FILTER = "chronicle.googleapis.com"

    parent = f"organizations/{organization_id}"
    
    assets, credentials = get_gcp_assets(parent, ASSET_TYPE_FILTER)
    if assets and credentials:
        populate_database(assets, SERVICE_FILTER, credentials)
        print_hierarchical_report_from_db()

if __name__ == "__main__":
    # This part is for running the script directly for testing
    GCP_ORGANIZATION_ID = "814270943322" 
    main(GCP_ORGANIZATION_ID)
