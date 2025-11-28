import datetime
import json

from database_setup import create_db_session, Audit, AuditType, ConfigurableAudit, SecopsTenantConfig, CustomYL2Query
from chronicle_api import make_api_request
from custom_audits import run_custom_iam_audit
from utils import get_response_details

# This function is extracted from main.py to break a circular dependency
# and to decouple the core logic from the FastAPI web framework.

def list_available_audits_from_db():
    """
    Helper to fetch all available audits directly from the database.
    """
    db_session = create_db_session()
    try:
        all_audits = {}
        # Fetch standard audits
        configurable_audits = db_session.query(ConfigurableAudit).all()
        for audit in configurable_audits:
            all_audits[audit.name] = {
                "category": audit.category,
                "api_path": audit.api_path,
                "method": audit.method,
                "response_key": audit.response_key,
                "default_page_size": audit.default_page_size,
                "audit_type_name": audit.audit_type.name,
                "audit_type_icon": audit.audit_type.icon,
                "auth_method": audit.audit_type.auth_method,
                "response_format": audit.response_format,
                "pagination_token_key": audit.pagination_token_key,
                "pagination_results_key": audit.pagination_results_key,
                "pagination_request_token_key": audit.pagination_request_token_key,
                "max_pages": audit.max_pages
            }
        # Fetch custom YL2 queries
        custom_queries = db_session.query(CustomYL2Query).all()
        yl2_audit_type = db_session.query(AuditType).filter_by(name="Custom YL2").one_or_none()
        for q in custom_queries:
            all_audits[q.name] = {
                "category": q.category,
                "audit_type_name": yl2_audit_type.name if yl2_audit_type else "Custom YL2",
                "audit_type_icon": yl2_audit_type.icon if yl2_audit_type else "code",
                "yl2_query": q.yl2_query,
                "time_unit": q.time_unit,
                "time_value": q.time_value,
                "api_path": "v1alpha/{parent}/dashboardQueries:execute",
                "method": "POST",
                "response_key": "queryResults"
            }
        return all_audits
    finally:
        db_session.close()


def run_audit_logic(project_id: str, request: dict):
    """
    Synchronous core logic for running an audit.
    Raises ValueError on failure.
    """
    audit_name = request.get("audit_name")
    audit_details_override = request.get("audit_details")

    db_session = create_db_session()
    try:
        if audit_details_override:
            audit_details = audit_details_override
            audit_type_obj = db_session.query(AuditType).filter_by(id=audit_details['audit_type_id']).one()
            audit_details['auth_method'] = audit_type_obj.auth_method
        elif audit_name:
            all_audits = list_available_audits_from_db()
            audit_details = all_audits.get(audit_name)
        else:
            raise ValueError("Request must include either 'audit_name' or 'audit_details'.")

        if not audit_details:
            raise ValueError(f"Audit '{audit_name}' not found")

        audit_type = audit_details.get("audit_type_name") or audit_details.get("audit_type")

        if audit_type == "Custom IAM":
            final_response = run_custom_iam_audit(project_id)
        else:
            config = db_session.query(SecopsTenantConfig).filter_by(project_id=project_id).first()
            if not config:
                raise ValueError("Tenant is not configured.")

            if audit_type == "Custom YL2":
                json_payload = {
                    "query": {
                        "query": audit_details.get("yl2_query", "").strip(),
                        "input": {"relativeTime": {"timeUnit": audit_details.get("time_unit"), "startTimeVal": str(audit_details.get("time_value"))}}
                    }
                }
                audit_details["json_data"] = json_payload
            
            auth_method = audit_details.get("auth_method", "GCP")
            parent_path = None
            base_url = None

            if auth_method == "GCP":
                parent_path = f'projects/{project_id}/locations/{config.secops_region}/instances/{config.secops_customer_id}'
                base_url = f"https://{config.secops_region}-chronicle.googleapis.com"
            elif auth_method == "SOAR_API_KEY":
                base_url = config.soar_url
            elif auth_method == "BINDPLANE_API_KEY":
                base_url = config.bindplane_url
            
            final_response = make_api_request(project_id=project_id, audit_details=audit_details, base_url=base_url, parent_path=parent_path, max_pages=audit_details.get("max_pages"))

        if "error" in final_response:
            error_detail = final_response.get("details", final_response.get("error", "Unknown error"))
            raise ValueError(error_detail)

        current_audit_name = audit_details.get("name") or audit_name
        new_audit = Audit(
            tenant_project_id=project_id,
            audit_category=audit_details.get("category", "Unknown"),
            audit_name=current_audit_name,
            run_timestamp=datetime.datetime.utcnow().isoformat(),
            status="Success",
            results=json.dumps(final_response, indent=2)
        )
        db_session.add(new_audit)
        db_session.commit()

        size_bytes, item_count = get_response_details(final_response)
        size_kb = round(size_bytes / 1024, 2)

        return {"message": f"Audit '{current_audit_name}' completed successfully. Results: {item_count} items ({size_kb} KB)."}

    except (ValueError, KeyError) as e:
        current_audit_name = audit_details.get("name") or audit_name if audit_details else "Unknown"
        new_audit = Audit(
            tenant_project_id=project_id,
            audit_category=audit_details.get("category", "Unknown") if audit_details else "Unknown",
            audit_name=current_audit_name,
            run_timestamp=datetime.datetime.utcnow().isoformat(),
            status="Failed",
            results=json.dumps({"error": str(e)}, indent=2)
        )
        db_session.add(new_audit)
        db_session.commit()
        raise e
    finally:
        db_session.close()
