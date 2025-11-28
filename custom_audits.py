
import google.auth
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# A list of the full IAM role names you want to find.
TARGET_ROLES = [
    "roles/chronicle.viewer",
    "roles/chronicle.editor",
    "roles/chronicle.admin",
    "roles/chronicle.federationAdmin",
    "roles/chronicle.federationViewer",
    "roles/chronicle.globalDataAccess",
    "roles/chronicle.limitedViewer",
    "roles/chronicle.restrictedDataAccess",
    "roles/chronicle.restrictedDataAccessViewer",
    "roles/chronicle.serviceAgent",
    "roles/chronicle.soarAdmin",
    "roles/chronicle.soarAnalyst",
    "roles/chronicle.soarEngineer",
    "roles/chronicle.soarServiceAgent",
    "roles/chronicle.soarThreatManager",
    "roles/chronicle.soarViewer",
    "roles/chronicle.soarVulnerabilityManager"
]

def run_custom_iam_audit(project_id: str) -> dict:
    """
    Queries the IAM policy for a given GCP project, finds principals with
    specific Chronicle-related roles, and returns the results as a dictionary.
    """
    try:
        credentials, project = google.auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        service = build('cloudresourcemanager', 'v1', credentials=credentials)

        request = service.projects().getIamPolicy(resource=project_id, body={})
        policy = request.execute()

        bindings = policy.get('bindings', [])
        
        # Initialize results with all target roles to ensure they are all present in the output
        results = {role: [] for role in TARGET_ROLES}

        if not bindings:
            return {"message": f"No IAM bindings found for project {project_id}.", "roles": results}

        for binding in bindings:
            role = binding.get('role')
            if role in TARGET_ROLES:
                members = binding.get('members', [])
                results[role].extend(members)
        
        return {"roles": results}

    except HttpError as error:
        error_details = f"An API error occurred: {error}. Please ensure the project ID '{project_id}' is correct and that the authenticated principal has the 'resourcemanager.projects.getIamPolicy' permission."
        return {"error": "HttpError", "details": error_details}
    except google.auth.exceptions.DefaultCredentialsError:
        error_details = "Authentication failed. Please configure Application Default Credentials (ADC). See https://cloud.google.com/docs/authentication/provide-credentials-adc for more information."
        return {"error": "AuthError", "details": error_details}
    except Exception as e:
        return {"error": "UnexpectedError", "details": str(e)}
