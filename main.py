import os
import os
import datetime
import json
from typing import Optional, Any
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader
from pydantic import BaseModel
import google.generativeai as genai

import redis
from celery.result import AsyncResult
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload
from celery_worker import celery_app, generate_report_task, generate_insight_report_task, discover_tenants_task, run_scheduled_job, generate_diff_report_task, purge_audits_task
from utils import retry_with_backoff, remove_excluded_fields, generate_gemini_summary, get_response_details
from database_setup import create_db_session, init_db, Project, SecopsTenantConfig, Audit, AuditPrompt, Report, Insight, CustomYL2Query, AuditType, ConfigurableAudit, Schedule
from chronicle_api import make_api_request
from custom_audits import run_custom_iam_audit
from audit_logic import run_audit_logic
import mcp_agent # Import the new agent logic
from mcp_tools import clear_session_state, TOOL_REGISTRY

# --- Redis Client for direct access ---
redis_client = redis.Redis(decode_responses=True)

# --- Gemini Configuration ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    print("Warning: GEMINI_API_KEY environment variable not set. Report generation will fail.")
else:
    genai.configure(api_key=GEMINI_API_KEY)

# --- MCP Agent Session ---
# We'll store one chat session in memory for simplicity.
# A more robust solution might use user-specific sessions.
mcp_chat_session = None

# --- Database setup ---
# This will create the database and tables if they don't exist
init_db()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Seeds the database and initializes the MCP agent session on startup.
    """
    global mcp_chat_session
    seed_audit_types()
    seed_default_audits()
    print("--- Initializing MCP Agent Chat Session... ---")
    mcp_chat_session = mcp_agent.start_chat_session()
    clear_session_state() # Clear any lingering state
    print("--- MCP Agent Ready. ---")
    yield
    # Cleanup logic can be added here if needed in the future

app = FastAPI(lifespan=lifespan)

def seed_audit_types():
    """
    Populates the AuditType table with the predefined types and handles legacy name changes.
    """
    db_session = create_db_session()
    try:
        # --- Migration: Rename "Standard API" to "Chronicle API" if it exists ---
        legacy_type = db_session.query(AuditType).filter_by(name="Standard API").first()
        if legacy_type:
            print("--- Found legacy 'Standard API' type. Renaming to 'Chronicle API'... ---")
            legacy_type.name = "Chronicle API"
            db_session.commit()
            print("--- Rename successful. ---")

        # --- Migration: Update Chronicle API icon ---
        chronicle_api_type = db_session.query(AuditType).filter_by(name="Chronicle API").first()
        if chronicle_api_type and chronicle_api_type.icon != "chronicle":
            print("--- Updating icon for 'Chronicle API' type... ---")
            chronicle_api_type.icon = "chronicle"
            db_session.commit()
            print("--- Icon updated successfully. ---")

        # --- Migration: Update SOAR API icon ---
        soar_api_type = db_session.query(AuditType).filter_by(name="SOAR API").first()
        if soar_api_type and soar_api_type.icon != "chronicle":
            print("--- Updating icon for 'SOAR API' type... ---")
            soar_api_type.icon = "chronicle"
            db_session.commit()
            print("--- Icon updated successfully. ---")

        # --- Migration: Update BindPlane API icon ---
        bindplane_api_type = db_session.query(AuditType).filter_by(name="BindPlane API").first()
        if bindplane_api_type and bindplane_api_type.icon != "bindplane":
            print("--- Updating icon for 'BindPlane API' type... ---")
            bindplane_api_type.icon = "bindplane"
            db_session.commit()
            print("--- Icon updated successfully. ---")

        # --- Migration: Update Custom YL2 icon ---
        yl2_api_type = db_session.query(AuditType).filter_by(name="Custom YL2").first()
        if yl2_api_type and yl2_api_type.icon != "chronicle":
            print("--- Updating icon for 'Custom YL2' type... ---")
            yl2_api_type.icon = "chronicle"
            db_session.commit()
            print("--- Icon updated successfully. ---")

        # Check if the table is already seeded
        if db_session.query(AuditType).count() > 0:
            print("--- AuditTypes already seeded. Skipping initial seed. ---")
            return

        print("--- Seeding initial AuditTypes... ---")
        
        types_to_seed = [
            AuditType(
                name="Chronicle API",
                description="A standard audit that calls a GET endpoint on the Chronicle API.",
                icon="chronicle",
                auth_method="GCP"
            ),
            AuditType(
                name="Custom IAM",
                description="A special audit type for querying GCP IAM policies related to SecOps.",
                icon="security",
                auth_method="GCP"
            ),
            AuditType(
                name="Custom YL2",
                description="An audit based on a user-defined YARA-L 2.0 query.",
                icon="chronicle",
                auth_method="GCP"
            ),
            AuditType(
                name="SOAR API",
                description="An audit that calls an endpoint on the SecOps SOAR API.",
                icon="soar",
                auth_method="SOAR_API_KEY"
            ),
            AuditType(
                name="BindPlane API",
                description="An audit that calls an endpoint on the BindPlane API.",
                icon="bindplane",
                auth_method="BINDPLANE_API_KEY"
            )
        ]
        
        db_session.add_all(types_to_seed)
        db_session.commit()
        print("--- AuditTypes seeded successfully. ---")

    except Exception as e:
        print(f"--- Error seeding AuditTypes: {e} ---")
        db_session.rollback()
    finally:
        db_session.close()


def seed_default_audits():
    """
    Seeds the database with a default set of audits from a JSON file.
    This function is idempotent and safe to run on every startup.
    It handles both standard ConfigurableAudits and CustomYL2Query audits.
    """
    db_session = create_db_session()
    try:
        default_audits_file = os.path.join(os.path.dirname(__file__), 'default_audits.json')
        if not os.path.exists(default_audits_file):
            print("--- 'default_audits.json' not found. Skipping default audit seeding. ---")
            return

        with open(default_audits_file, 'r') as f:
            default_audits = json.load(f)

        # Get existing names to prevent duplicates
        existing_configurable_audits = {audit.name for audit in db_session.query(ConfigurableAudit).all()}
        existing_yl2_queries = {query.name for query in db_session.query(CustomYL2Query).all()}
        existing_prompts = {prompt.audit_name for prompt in db_session.query(AuditPrompt).all()}
        
        audit_types = {type.name: type.id for type in db_session.query(AuditType).all()}
        
        audits_to_add = []
        yl2_queries_to_add = []
        prompts_to_add = []

        for audit_data in default_audits:
            audit_name = audit_data['name']
            audit_type_name = audit_data.get('audit_type_name')

            # --- Handle Audit Seeding ---
            if audit_type_name == "Custom YL2":
                if audit_name not in existing_yl2_queries:
                    new_yl2_query = CustomYL2Query(
                        name=audit_name,
                        category=audit_data.get('category', 'General'),
                        yl2_query=audit_data.get('yl2_query', ''),
                        time_unit=audit_data.get('time_unit', 'DAY'),
                        time_value=audit_data.get('time_value', 30)
                    )
                    yl2_queries_to_add.append(new_yl2_query)
            else: # Handle standard ConfigurableAudits
                if audit_name not in existing_configurable_audits:
                    audit_type_id = audit_types.get(audit_type_name)
                    if not audit_type_id:
                        print(f"--- Warning: Audit type '{audit_type_name}' for audit '{audit_name}' not found. Skipping. ---")
                        continue
                    
                    new_audit = ConfigurableAudit(
                        name=audit_name,
                        category=audit_data.get('category', 'General'),
                        api_path=audit_data.get('api_path'),
                        method=audit_data.get('method'),
                        response_key=audit_data.get('response_key'),
                        default_page_size=audit_data.get('default_page_size'),
                        max_pages=audit_data.get('max_pages'),
                        audit_type_id=audit_type_id,
                        response_format=audit_data.get('response_format', 'JSON'),
                        pagination_token_key=audit_data.get('pagination_token_key'),
                        pagination_results_key=audit_data.get('pagination_results_key'),
                        pagination_request_token_key=audit_data.get('pagination_request_token_key')
                    )
                    audits_to_add.append(new_audit)

            # --- Handle Prompt Seeding (for all types) ---
            if audit_name not in existing_prompts and ('prompt_text' in audit_data or 'excluded_fields' in audit_data):
                new_prompt = AuditPrompt(
                    audit_name=audit_name,
                    prompt_text=audit_data.get('prompt_text', ''),
                    excluded_fields=audit_data.get('excluded_fields', '')
                )
                prompts_to_add.append(new_prompt)

        # --- Commit changes to the database ---
        if audits_to_add:
            print(f"--- Seeding {len(audits_to_add)} new configurable audits... ---")
            db_session.add_all(audits_to_add)
        if yl2_queries_to_add:
            print(f"--- Seeding {len(yl2_queries_to_add)} new Custom YL2 Queries... ---")
            db_session.add_all(yl2_queries_to_add)
        if prompts_to_add:
            print(f"--- Seeding {len(prompts_to_add)} new prompts... ---")
            db_session.add_all(prompts_to_add)

        if any([audits_to_add, yl2_queries_to_add, prompts_to_add]):
            db_session.commit()
            print("--- Default audit seeding complete. ---")
        else:
            print("--- All default audits, queries, and prompts are already in the database. ---")

    except Exception as e:
        print(f"--- Error seeding default audits: {e} ---")
        db_session.rollback()
    finally:
        db_session.close()


# --- Static files and templates ---
script_dir = os.path.dirname(__file__)
static_dir = os.path.join(script_dir, "static")
templates_dir = os.path.join(script_dir, "templates")
app.mount("/static", StaticFiles(directory=static_dir), name="static")
templates = Environment(loader=FileSystemLoader(templates_dir))

# --- Pydantic Models ---
class TenantConfig(BaseModel):
    name: str
    secops_customer_id: str
    secops_region: str
    soar_url: str
    soar_api_key: str
    bindplane_url: Optional[str] = None
    bindplane_api_key: Optional[str] = None

class ChronicleApiRequest(BaseModel):
    method: str
    api_path: str
    json_data: Optional[dict] = None

class AuditRunRequest(BaseModel):
    audit_name: str
    max_records: Optional[int] = None

class PromptUpdateRequest(BaseModel):
    prompts: dict[str, str]
    excluded_fields: dict[str, str]

class GenerateReportRequest(BaseModel):
    audit_names: list[str]

class GenerateDiffRequest(BaseModel):
    audit_id_1: int
    audit_id_2: int

class PurgeAuditsRequest(BaseModel):
    older_than_days: int
    audit_name: Optional[str] = None

class DeleteReportsRequest(BaseModel):
    report_ids: list[int]

class ReportRenameRequest(BaseModel):
    new_name: str

class ReportStatusResponse(BaseModel):
    state: str
    status: str
    report_id: Optional[int] = None

class InsightCreate(BaseModel):
    title: str
    prompt: str
    audit_sources: list[str]
    excluded_fields: Optional[str] = None

class CustomYL2QueryRequest(BaseModel):
    name: str
    category: Optional[str] = None
    yl2_query: str
    time_unit: Optional[str] = None
    time_value: Optional[int] = None



class ExclusionsPreviewRequest(BaseModel):

    excluded_fields: list[str]



class ManualTenantRequest(BaseModel):
    project_id: str
    display_name: str

class ConfigurableAuditRequest(BaseModel):
    name: str
    category: str
    api_path: Optional[str] = None
    method: Optional[str] = None
    response_key: Optional[str] = None
    default_page_size: Optional[int] = None
    audit_type_id: int
    response_format: Optional[str] = 'JSON'
    pagination_token_key: Optional[str] = None
    pagination_results_key: Optional[str] = None
    pagination_request_token_key: Optional[str] = None
    max_pages: Optional[int] = None

class ChatRequest(BaseModel):
    message: str

class ToolRunRequest(BaseModel):
    command: str

class ScheduleCreate(BaseModel):
    name: str
    project_id: str
    cron_schedule: str
    is_enabled: bool
    audit_names: list[str]
    schedule_type: str
    report_name_format: Optional[str] = None

# --- Hardcoded list of available audits for seeding ---
AVAILABLE_AUDITS = {
    "Instance Details": {
        "category": "General", "api_path": "v1alpha/{parent}", "method": "GET", "response_key": None, "default_page_size": None
    },
    "Feeds": {
        "category": "Ingestion", "api_path": "v1alpha/{parent}/feeds", "method": "GET", "response_key": "feeds", "default_page_size": None
    },
    "Forwarders": {
        "category": "Ingestion", "api_path": "v1alpha/{parent}/forwarders", "method": "GET", "response_key": "forwarders", "default_page_size": None
    },
    "Parser Extensions": {
        "category": "Parsing", "api_path": "v1alpha/{parent}/logTypes/-/parserExtensions", "method": "GET", "response_key": "parserExtensions", "default_page_size": 1000
    },
    "Parsers": {
        "category": "Parsing", "api_path": "v1alpha/{parent}/logTypes/-/parsers", "method": "GET", "response_key": "parsers", "default_page_size": None
    },
    "Rules": {
        "category": "Detection", "api_path": "v1alpha/{parent}/rules", "method": "GET", "response_key": "rules", "default_page_size": None
    },
    "Rule Deployment": {
        "category": "Detection", "api_path": "v1alpha/{parent}/rules/-/deployments", "method": "GET", "response_key": "ruleDeployments", "default_page_size": None
    },
    "Rule Execution Errors": {
        "category": "Detection", "api_path": "v1alpha/{parent}/ruleExecutionErrors", "method": "GET", "response_key": "ruleExecutionErrors", "default_page_size": 1000
    },
    "Retro Hunts": {
        "category": "Detection", "api_path": "v1alpha/{parent}/rules/-/retrohunts", "method": "GET", "response_key": "retrohunts", "default_page_size": 100
    },
    "Curated RuleSet Deployment": {
        "category": "Detection", "api_path": "v1alpha/{parent}/curatedRuleSetCategories/-/curatedRuleSets/-/curatedRuleSetDeployments", "method": "GET", "response_key": "curatedRuleSetDeployments", "default_page_size": 2000
    },
    "Curated Rules": {
        "category": "Detection", "api_path": "v1alpha/{parent}/curatedRules", "method": "GET", "response_key": "curatedRules", "default_page_size": 1000
    },
    "Curated Rule Exclusions": {
        "category": "Detection", "api_path": "v1alpha/{parent}/findingsRefinements", "method": "GET", "response_key": "findingsRefinements", "default_page_size": 1000
    },
    "Data Tables": {
        "category": "Data Enrichment", "api_path": "v1alpha/{parent}/dataTables", "method": "GET", "response_key": "dataTables", "default_page_size": 1000
    },
    "Reference Lists": {
        "category": "Data Enrichment", "api_path": "v1alpha/{parent}/referenceLists?view=REFERENCE_LIST_VIEW_BASIC", "method": "GET", "response_key": "referenceLists", "default_page_size": 1000
    },
    "SecOps Access": {
        "category": "Authorization", "audit_type": "custom_iam", "api_path": None, "method": None, "response_key": None, "default_page_size": 1000
    },
    "Native Dashboards": {
        "category": "Dashboards", "api_path": "v1alpha/{parent}/nativeDashboards", "method": "GET", "response_key": "nativeDashboards", "default_page_size": 100
    },
    "Risk Configuration": {
        "category": "Risk Analytics", "api_path": "v1alpha/{parent}/riskConfig", "method": "GET", "response_key": None, "default_page_size": None
    },
    "Linked Instances": {
        "category": "Federation", "api_path": "v1alpha/{parent}:fetchFederationAccess", "method": "GET", "response_key": None, "default_page_size": None
    },
    "Big Query Export": {
        "category": "Data Export", "api_path": "v1alpha/{parent}/bigQueryExport", "method": "GET", "response_key": None, "default_page_size": None
    }
}


# --- Schedule Endpoints ---
@app.get("/api/schedules")
def get_schedules():
    db_session = create_db_session()
    try:
        schedules = db_session.query(Schedule).options(
            joinedload(Schedule.audits_to_run),
            joinedload(Schedule.audits_for_report),
            joinedload(Schedule.audits_for_diff)
        ).all()
        result = []
        for s in schedules:
            # Determine which audit list to use
            audit_names = []
            if s.schedule_type == 'audit':
                audit_names = [a.name for a in s.audits_to_run]
            elif s.schedule_type == 'report':
                audit_names = [a.name for a in s.audits_for_report]
            elif s.schedule_type == 'diff':
                audit_names = [a.name for a in s.audits_for_diff]

            result.append({
                "id": s.id,
                "name": s.name,
                "project_id": s.tenant_project_id,
                "cron_schedule": s.cron_schedule,
                "is_enabled": s.is_enabled,
                "schedule_type": s.schedule_type,
                "report_name_format": s.report_name_format,
                "audits": audit_names
            })
        return result
    finally:
        db_session.close()

@app.post("/api/schedules")
def create_schedule(request: ScheduleCreate):
    db_session = create_db_session()
    try:
        audits = db_session.query(ConfigurableAudit).filter(ConfigurableAudit.name.in_(request.audit_names)).all()
        
        new_schedule = Schedule(
            name=request.name,
            tenant_project_id=request.project_id,
            cron_schedule=request.cron_schedule,
            is_enabled=request.is_enabled,
            schedule_type=request.schedule_type,
            report_name_format=request.report_name_format
        )

        if request.schedule_type == 'audit':
            new_schedule.audits_to_run = audits
        elif request.schedule_type == 'report':
            new_schedule.audits_for_report = audits
        elif request.schedule_type == 'diff':
            new_schedule.audits_for_diff = audits

        db_session.add(new_schedule)
        db_session.commit()
        return {"message": "Schedule created successfully", "id": new_schedule.id}
    except Exception as e:
        db_session.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        db_session.close()

@app.put("/api/schedules/{schedule_id}")
def update_schedule(schedule_id: int, request: ScheduleCreate):
    db_session = create_db_session()
    try:
        schedule = db_session.query(Schedule).get(schedule_id)
        if not schedule:
            raise HTTPException(status_code=404, detail="Schedule not found")

        audits = db_session.query(ConfigurableAudit).filter(ConfigurableAudit.name.in_(request.audit_names)).all()
        
        schedule.name = request.name
        schedule.tenant_project_id = request.project_id
        schedule.cron_schedule = request.cron_schedule
        schedule.is_enabled = request.is_enabled
        schedule.schedule_type = request.schedule_type
        schedule.report_name_format = request.report_name_format

        # Clear existing audit associations and add the new ones
        schedule.audits_to_run.clear()
        schedule.audits_for_report.clear()
        schedule.audits_for_diff.clear()

        if request.schedule_type == 'audit':
            schedule.audits_to_run = audits
        elif request.schedule_type == 'report':
            schedule.audits_for_report = audits
        elif request.schedule_type == 'diff':
            schedule.audits_for_diff = audits
        
        db_session.commit()
        return {"message": "Schedule updated successfully"}
    except Exception as e:
        db_session.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        db_session.close()

@app.delete("/api/schedules/{schedule_id}")
def delete_schedule(schedule_id: int):
    db_session = create_db_session()
    try:
        schedule = db_session.query(Schedule).get(schedule_id)
        if not schedule:
            raise HTTPException(status_code=404, detail="Schedule not found")
        
        db_session.delete(schedule)
        db_session.commit()
        return {"message": "Schedule deleted successfully"}
    finally:
        db_session.close()

@app.post("/api/schedules/{schedule_id}/run")
def run_schedule_now(schedule_id: int):
    """
    Manually triggers a scheduled report to run immediately.
    """
    db_session = create_db_session()
    try:
        schedule = db_session.query(Schedule).get(schedule_id)
        if not schedule:
            raise HTTPException(status_code=404, detail="Schedule not found")
        
        task = run_scheduled_job.delay(schedule.id)
        
        # Update last_run_at to reflect this manual execution
        schedule.last_run_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
        db_session.commit()

        print(f"--- Manually triggered schedule '{schedule.name}' (ID: {schedule.id}) with task ID: {task.id} ---")
        return {"message": f"Schedule '{schedule.name}' has been triggered successfully."}
    finally:
        db_session.close()

# --- API Endpoints ---

@app.get("/", response_class=HTMLResponse)
async def read_root():
    template = templates.get_template("index.html")
    return HTMLResponse(content=template.render())

@app.get("/api/prompts")
async def get_prompts():
    db_session = create_db_session()
    try:
        prompts = db_session.query(AuditPrompt).all()
        return {
            p.audit_name: {
                "prompt_text": p.prompt_text,
                "excluded_fields": p.excluded_fields
            } for p in prompts
        }
    finally:
        db_session.close()

@app.post("/api/prompts")
async def update_prompts(request: PromptUpdateRequest):
    print("Received request to update prompts:", request.model_dump_json(indent=2)) # Troubleshooting log
    db_session = create_db_session()
    try:
        all_audit_names = set(request.prompts.keys()) | set(request.excluded_fields.keys())
        for audit_name in all_audit_names:
            prompt_text = request.prompts.get(audit_name)
            excluded_fields = request.excluded_fields.get(audit_name, "")

            prompt = db_session.query(AuditPrompt).filter_by(audit_name=audit_name).first()
            if prompt:
                if prompt_text is not None:
                    prompt.prompt_text = prompt_text
                prompt.excluded_fields = excluded_fields
            else:
                # If no prompt text is provided, create a default one.
                if prompt_text is None:
                    # Use a specific prompt for YL2 queries, assuming they will be CSV.
                    if "yl2" in audit_name.lower():
                         prompt_text = (
                            "Act as a security analyst. The following data is in CSV format. "
                            "Provide a concise summary of the key findings. Use Markdown for formatting, "
                            "including headers and bullet points. Focus on the most important insights, anomalies, "
                            "or patterns in the data."
                        )
                    else:
                        # Generic default prompt for other audit types.
                        prompt_text = (
                            f"Act as a security analyst. Provide a concise summary of the key findings from the audit data for '{audit_name}'. "
                            "Use Markdown for formatting, including headers (e.g., '## Key Findings') and bullet points (e.g., '* Finding 1'). "
                            "Focus on the most important insights, anomalies, or configuration details."
                        )

                new_prompt = AuditPrompt(
                    audit_name=audit_name,
                    prompt_text=prompt_text,
                    excluded_fields=excluded_fields
                )
                db_session.add(new_prompt)
        db_session.commit()
        return {"message": "Prompts updated successfully"}
    finally:
        db_session.close()

@app.get("/api/audits")
def list_available_audits():
    """
    Returns a combined list of database-driven configurable audits and custom YL2 query audits.
    """
    db_session = create_db_session()
    try:
        all_audits = {}

        # Fetch standard audits from the new ConfigurableAudit table
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
                "auth_method": audit.audit_type.auth_method, # Add the auth method
                "response_format": audit.response_format
            }

        # Fetch custom YL2 queries from their table
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

@app.get("/api/tenants/{project_id}/audits/status")
def get_audits_status(project_id: str):
    db_session = create_db_session()
    try:
        # Get all available audits, including custom ones
        all_audits = list_available_audits()

        # Subquery to find the ID of the latest successful run for each audit
        subq = db_session.query(
            Audit.audit_name,
            func.max(Audit.id).label('latest_id')
        ).filter(
            Audit.tenant_project_id == project_id,
            Audit.status == "Success"
        ).group_by(Audit.audit_name).subquery()

        # Join the Audit table with the subquery to get the full record
        latest_runs_q = db_session.query(Audit).join(
            subq,
            (Audit.id == subq.c.latest_id)
        )
        
        latest_runs = latest_runs_q.all()
        latest_runs_map = {audit.audit_name: audit for audit in latest_runs}

        # --- New: Fetch prompts to merge exclusion data ---
        prompts = db_session.query(AuditPrompt).all()
        prompts_map = {p.audit_name: p for p in prompts}

        # Combine statuses with the full list of available audits
        audits_with_status = {}
        for audit_name, details in all_audits.items():
            # Create a copy to avoid modifying the global dict
            audit_info = details.copy()
            latest_run_obj = latest_runs_map.get(audit_name)
            prompt_obj = prompts_map.get(audit_name)

            audit_info['last_successful_run'] = latest_run_obj.run_timestamp if latest_run_obj else None
            audit_info['latest_run_id'] = latest_run_obj.id if latest_run_obj else None
            
            if latest_run_obj:
                results_data = json.loads(latest_run_obj.results)
                size_bytes, item_count = get_response_details(results_data)
                audit_info['item_count'] = item_count
                audit_info['size_bytes'] = size_bytes
                print(f"--- DEBUG: Audit '{audit_name}' - Items: {item_count}, Size: {size_bytes} ---") # Explicit logging
            else:
                audit_info['item_count'] = None
                audit_info['size_bytes'] = None
                print(f"--- DEBUG: Audit '{audit_name}' - No successful run found. ---") # Explicit logging

            # --- New: Count total successful runs ---
            successful_run_count = db_session.query(Audit).filter_by(
                tenant_project_id=project_id,
                audit_name=audit_name,
                status="Success"
            ).count()
            audit_info['successful_run_count'] = successful_run_count
            print(f"--- DEBUG: Audit '{audit_name}' has {successful_run_count} successful runs. ---")

            # --- New: Add prompt and exclusion info ---
            audit_info['prompt'] = prompt_obj.prompt_text if prompt_obj else f"Summarize the findings for {audit_name}"
            audit_info['excluded_fields'] = prompt_obj.excluded_fields if prompt_obj else ""

            audits_with_status[audit_name] = audit_info
            
        return audits_with_status
    finally:
        db_session.close()

@app.get("/api/tenants")
async def get_tenants():
    db_session = create_db_session()
    try:
        projects = db_session.query(Project).all()
        if not projects:
            raise HTTPException(status_code=412, detail="Initial asset inventory has not been run.")

        tenants = []
        for p in projects:
            config = p.secops_config
            api_status = {
                "chronicle": "Not Configured",
                "soar": "Not Configured",
                "bindplane": "Not Configured"
            }

            if config:
                # Test Chronicle
                parent = f'projects/{p.id}/locations/{config.secops_region}/instances/{config.secops_customer_id}'
                chronicle_details = {"auth_method": "GCP", "method": "GET", "api_path": "v1alpha/{parent}/feeds"}
                chronicle_res = make_api_request(project_id=p.id, audit_details=chronicle_details, base_url=f"https://{config.secops_region}-chronicle.googleapis.com", parent_path=parent)
                api_status["chronicle"] = "Success" if "error" not in chronicle_res else "Failed"

                # Test SOAR
                if config.soar_url and config.soar_api_key:
                    soar_details = {"auth_method": "SOAR_API_KEY", "method": "GET", "api_path": "api/external/v1/settings/GetSystemVersion", "soar_api_key": config.soar_api_key, "response_format": "TEXT"}
                    soar_res = make_api_request(project_id=p.id, audit_details=soar_details, base_url=config.soar_url)
                    api_status["soar"] = "Success" if "error" not in soar_res else "Failed"

                # Test BindPlane
                if config.bindplane_url and config.bindplane_api_key:
                    bindplane_details = {"auth_method": "BINDPLANE_API_KEY", "method": "GET", "api_path": "v1/agent-versions", "bindplane_api_key": config.bindplane_api_key}
                    bindplane_res = make_api_request(project_id=p.id, audit_details=bindplane_details, base_url=config.bindplane_url)
                    api_status["bindplane"] = "Success" if "error" not in bindplane_res else "Failed"

            tenants.append({
                "project_id": p.id,
                "project_name": p.display_name,
                "is_configured": config is not None,
                "api_status": api_status
            })
        return tenants
    finally:
        db_session.close()

@app.get("/api/tenants/{project_id}")
async def get_tenant_config(project_id: str):
    db_session = create_db_session()
    try:
        # Correctly join and filter by the Project's external ID
        config = db_session.query(SecopsTenantConfig).join(Project).filter(Project.id == project_id).first()
        if not config:
            # If no config, find the project to pre-populate the form
            project = db_session.query(Project).filter_by(id=project_id).first()
            if not project:
                raise HTTPException(status_code=404, detail="Project not found")
            # Return a default/empty config structure
            return {
                "name": project.display_name, # Default name to project name
                "secops_customer_id": "",
                "secops_region": "",
                "soar_url": "",
                "soar_api_key": ""
            }

        return {
            "name": config.name,
            "secops_customer_id": config.secops_customer_id,
            "secops_region": config.secops_region,
            "soar_url": config.soar_url,
            "soar_api_key": config.soar_api_key,
            "bindplane_url": config.bindplane_url,
            "bindplane_api_key": config.bindplane_api_key
        }
    finally:
        db_session.close()

@app.post("/api/tenants/{project_id}")
async def update_tenant_config(project_id: str, config: TenantConfig):
    db_session = create_db_session()
    try:
        project = db_session.query(Project).filter_by(id=project_id).first()
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        tenant_config = project.secops_config
        if not tenant_config:
            tenant_config = SecopsTenantConfig(project_id=project_id)
            db_session.add(tenant_config)
        
        tenant_config.name = config.name
        tenant_config.secops_customer_id = config.secops_customer_id
        tenant_config.secops_region = config.secops_region
        
        # Ensure the SOAR URL always ends with a trailing slash for consistency
        soar_url = config.soar_url
        if soar_url and not soar_url.endswith('/'):
            soar_url += '/'
        tenant_config.soar_url = soar_url
        
        tenant_config.soar_api_key = config.soar_api_key
        tenant_config.bindplane_url = config.bindplane_url
        tenant_config.bindplane_api_key = config.bindplane_api_key
        
        db_session.commit()
        return {"message": "Configuration updated successfully"}
    finally:
        db_session.close()

@app.post("/api/tenants/{project_id}/test")
async def test_tenant_connection(project_id: str):
    """
    Uses a standard, hardcoded audit (Feeds) to test the GCP connection.
    """
    db_session = create_db_session()
    try:
        config = db_session.query(SecopsTenantConfig).filter_by(project_id=project_id).first()
        if not config:
            raise HTTPException(status_code=404, detail="Configuration not found for this project.")

        # Construct the full parent path, which was missing
        parent = f'projects/{project_id}/locations/{config.secops_region}/instances/{config.secops_customer_id}'

        audit_details = {
            "auth_method": "GCP",
            "method": "GET",
            "api_path": "v1alpha/{parent}/feeds"
        }
        
        response = make_api_request(
            project_id=project_id,
            audit_details=audit_details,
            base_url=f"https://{config.secops_region}-chronicle.googleapis.com",
            parent_path=parent
        )
        
        if "error" in response:
            error_details = response.get("details", str(response))
            raise HTTPException(status_code=400, detail=f"Connection failed: {error_details}")
            
        return {"message": "Connection successful"}
    finally:
        db_session.close()


class SoarTestRequest(BaseModel):
    soar_url: str
    soar_api_key: str

class BindPlaneTestRequest(BaseModel):
    bindplane_url: str
    bindplane_api_key: str

@app.post("/api/tenants/{project_id}/test_soar")
async def test_soar_connection(project_id: str, request: SoarTestRequest):
    """
    Tests the SOAR API connection using provided credentials.
    """
    audit_details = {
        "auth_method": "SOAR_API_KEY",
        "method": "GET",
        "api_path": "api/external/v1/settings/GetSystemVersion",
        "soar_api_key": request.soar_api_key,
        "response_format": "TEXT"
    }
    
    response = make_api_request(
        project_id=project_id, # Still needed for context, though not used in URL
        audit_details=audit_details,
        base_url=request.soar_url
    )
    
    if "error" in response:
        error_details = response.get("details", str(response))
        raise HTTPException(status_code=400, detail=f"SOAR connection failed: {error_details}")
        
    return {"message": "SOAR connection successful"}

@app.post("/api/tenants/{project_id}/test_bindplane")
async def test_bindplane_connection(project_id: str, request: BindPlaneTestRequest):
    """
    Tests the BindPlane API connection using provided credentials.
    """
    audit_details = {
        "auth_method": "BINDPLANE_API_KEY",
        "method": "GET",
        "api_path": "v1/agent-versions", # A simple, stable endpoint
        "bindplane_api_key": request.bindplane_api_key
    }
    
    response = make_api_request(
        project_id=project_id,
        audit_details=audit_details,
        base_url=request.bindplane_url
    )
    
    if "error" in response:
        error_details = response.get("details", str(response))
        raise HTTPException(status_code=400, detail=f"BindPlane connection failed: {error_details}")
        
    return {"message": "BindPlane connection successful"}


@app.post("/api/tenants/{project_id}/chronicle_api")
async def handle_chronicle_api_request(project_id: str, request: ChronicleApiRequest):
    """
    Handles ad-hoc API requests from the UI, assuming GCP auth.
    """
    db_session = create_db_session()
    try:
        config = db_session.query(SecopsTenantConfig).filter_by(project_id=project_id).first()
        if not config:
            raise HTTPException(status_code=400, detail="Tenant is not configured.")

        audit_details = {
            "auth_method": "GCP",
            "method": request.method,
            "api_path": request.api_path,
            "json_data": request.json_data
        }
        parent = f'projects/{project_id}/locations/{config.secops_region}/instances/{config.secops_customer_id}'
        base_url = f"https://{config.secops_region}-chronicle.googleapis.com"

        response = make_api_request(
            project_id=project_id,
            audit_details=audit_details,
            base_url=base_url,
            parent_path=parent
        )
    finally:
        db_session.close()

    if "error" in response:
        error_detail = response.get("details", response["error"])
        raise HTTPException(status_code=400, detail=error_detail)
    return response

@app.post("/api/tenants/{project_id}/audits/run")
def run_audit(project_id: str, request: dict):
    """
    Runs an audit. Can be triggered by name (from DB) or by providing a full
    audit configuration for testing purposes.
    """
    try:
        return run_audit_logic(project_id, request)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/tenants/{project_id}/audits/{audit_name}/view")
async def view_audit_result(project_id: str, audit_name: str):
    db_session = create_db_session()
    try:
        latest_audit = db_session.query(Audit).filter_by(
            tenant_project_id=project_id,
            audit_name=audit_name,
            status="Success"
        ).order_by(Audit.run_timestamp.desc()).first()

        if not latest_audit:
            raise HTTPException(status_code=404, detail="No successful audit run found for this tenant and audit.")
        
        results_data = json.loads(latest_audit.results)
        size_bytes, item_count = get_response_details(results_data)

        # --- Token Estimation Logic ---
        token_count = 0
        try:
            config = configparser.ConfigParser()
            config_path = os.path.join(os.path.dirname(__file__), 'config.ini')
            config.read(config_path)
            model_name = config.get('gemini', 'model_name', fallback='gemini-1.5-flash')
            model = genai.GenerativeModel(model_name)
            token_count = model.count_tokens(latest_audit.results).total_tokens
        except Exception as e:
            print(f"--- WARN: Could not estimate tokens for '{audit_name}'. Error: {e} ---")
            # Fallback to a rough character-based estimate if the model fails
            token_count = len(latest_audit.results) // 4


        return {
            "results": results_data,
            "size_bytes": size_bytes,
            "item_count": item_count,
            "token_count": token_count
        }
    finally:
        db_session.close()

@app.get("/api/tenants/{project_id}/audits/{audit_name}/runs")
async def get_audit_runs(project_id: str, audit_name: str):
    """
    Returns a list of all successful runs for a specific audit.
    """
    db_session = create_db_session()
    try:
        runs = db_session.query(Audit).filter_by(
            tenant_project_id=project_id,
            audit_name=audit_name,
            status="Success"
        ).order_by(Audit.run_timestamp.desc()).all()

        return [
            {"id": run.id, "run_timestamp": run.run_timestamp} for run in runs
        ]
    finally:
        db_session.close()


@app.post("/api/tenants/{project_id}/audits/{audit_name}/preview_exclusions")
async def preview_audit_exclusions(project_id: str, audit_name: str, request: ExclusionsPreviewRequest):
    db_session = create_db_session()
    try:
        latest_audit = db_session.query(Audit).filter_by(
            tenant_project_id=project_id,
            audit_name=audit_name,
            status="Success"
        ).order_by(Audit.run_timestamp.desc()).first()

        if not latest_audit:
            raise HTTPException(status_code=404, detail="No successful audit run found for this tenant and audit. Please run the audit first.")
        
        results_data = json.loads(latest_audit.results)
        
        # Apply exclusions
        filtered_results = remove_excluded_fields(results_data, request.excluded_fields)
        
        # Get details of the filtered data
        size_bytes, item_count = get_response_details(filtered_results)

        return {
            "results": filtered_results,
            "size_bytes": size_bytes,
            "item_count": item_count
        }
    finally:
        db_session.close()

@app.post("/api/tenants/{project_id}/audits/{audit_name}/preview_exclusions")
async def preview_audit_exclusions(project_id: str, audit_name: str, request: ExclusionsPreviewRequest):
    db_session = create_db_session()
    try:
        latest_audit = db_session.query(Audit).filter_by(
            tenant_project_id=project_id,
            audit_name=audit_name,
            status="Success"
        ).order_by(Audit.run_timestamp.desc()).first()

        if not latest_audit:
            raise HTTPException(status_code=404, detail="No successful audit run found for this tenant and audit. Please run the audit first.")
        
        results_data = json.loads(latest_audit.results)
        
        # Apply exclusions
        filtered_results = remove_excluded_fields(results_data, request.excluded_fields)
        
        # Get details of the filtered data
        size_bytes, item_count = get_response_details(filtered_results)

        return {
            "results": filtered_results,
            "size_bytes": size_bytes,
            "item_count": item_count
        }
    finally:
        db_session.close()


@app.post("/api/tenants/{project_id}/reports/generate")
async def generate_report(project_id: str, request: GenerateReportRequest):
    """
    Starts the report generation task in the background.
    """
    task = generate_report_task.delay(project_id, request.audit_names)
    print(f"--- Started report generation task with ID: {task.id} ---") # Troubleshooting log
    return {"message": "Report generation started.", "task_id": task.id}

@app.post("/api/reports/generate_diff")
async def generate_diff_report(request: GenerateDiffRequest):
    """
    Starts the diff report generation task for two specific audit runs.
    """
    task = generate_diff_report_task.delay(request.audit_id_1, request.audit_id_2)
    print(f"--- Started diff report generation task with ID: {task.id} ---")
    return {"message": "Diff report generation started.", "task_id": task.id}


@app.get("/api/reports/status/{task_id}", response_model=ReportStatusResponse)
async def get_report_status(task_id: str):
    """
    Checks the status of a report generation task using Celery's AsyncResult.
    """
    task = celery_app.AsyncResult(task_id)
    status = str(task.info) if task.info else 'Processing...'
    report_id = None

    if task.state == 'SUCCESS':
        if isinstance(task.result, dict):
            status = task.result.get('status', 'Completed')
            report_id = task.result.get('report_id')
        else:
            status = 'Completed'
    elif task.state == 'FAILURE':
        # The result of a failed task is the exception object
        status = f"Failed: {str(task.result)}"
    elif task.state == 'PROGRESS':
        if isinstance(task.info, dict):
            status = task.info.get('status', 'In progress...')
    else:
        status = task.state  # PENDING, RETRY, etc.

    print(f"--- Checking status for task {task_id}: State={task.state}, Status='{status}' ---")
    return ReportStatusResponse(state=task.state, status=status, report_id=report_id)


@app.get("/api/reports")
async def get_reports(project_id: Optional[str] = None):
    db_session = create_db_session()
    try:
        query = db_session.query(Report, Project.display_name).join(Project)
        if project_id:
            query = query.filter(Report.tenant_project_id == project_id)
        
        reports_data = query.order_by(Report.generation_timestamp.desc()).all()

        reports_list = []
        for report, project_name in reports_data:
            reports_list.append({
                "id": report.id,
                "report_name": report.report_name,
                "generation_timestamp": report.generation_timestamp,
                "project_name": project_name
            })
        return reports_list
    finally:
        db_session.close()

@app.get("/api/reports/{report_id}")
async def get_report(report_id: int):
    db_session = create_db_session()
    try:
        report = db_session.query(Report).filter_by(id=report_id).first()
        if not report:
            raise HTTPException(status_code=404, detail="Report not found")
        return {
            "report_name": report.report_name,
            "generation_timestamp": report.generation_timestamp,
            "report_content": report.report_content
        }
    finally:
        db_session.close()

@app.put("/api/reports/{report_id}/rename")
async def rename_report(report_id: int, request: ReportRenameRequest):
    db_session = create_db_session()
    try:
        report = db_session.query(Report).filter_by(id=report_id).first()
        if not report:
            raise HTTPException(status_code=404, detail="Report not found")
        
        report.report_name = request.new_name
        db_session.commit()
        return {"message": "Report renamed successfully"}
    finally:
        db_session.close()


@app.post("/api/reports/delete")
async def delete_reports(request: DeleteReportsRequest):
    db_session = create_db_session()
    for report_id in request.report_ids:
        report = db_session.query(Report).filter_by(id=report_id).first()
        if report:
            db_session.delete(report)
    db_session.commit()
    db_session.close()
    return {"message": "Reports deleted successfully"}

@app.post("/api/audits/purge")
async def purge_old_audits(request: PurgeAuditsRequest):
    """
    Starts the background task to purge old audit records.
    """
    task = purge_audits_task.delay(request.older_than_days, request.audit_name)
    print(f"--- Started audit purge task with ID: {task.id} ---")
    return {"message": "Audit purge task started.", "task_id": task.id}


@app.get("/api/test_large_summary")
async def test_large_summary():
    """
    Temporary endpoint to test the large summary task.
    """
    task = celery_app.send_task('celery_worker.test_large_summary_task')
    print(f"--- Started large summary test task with ID: {task.id} ---")
    return {"message": "Large summary test task started.", "task_id": task.id}


@app.post("/api/reports/export")
async def export_reports(request: DeleteReportsRequest):
    """
    Exports multiple reports into a single downloadable Markdown file.
    """
    db_session = create_db_session()
    try:
        # Fetch all requested reports, ordering by timestamp
        reports = db_session.query(Report).filter(Report.id.in_(request.report_ids)).order_by(Report.generation_timestamp).all()
        
        if not reports:
            raise HTTPException(status_code=404, detail="No reports found for the given IDs.")

        # Combine the content of all reports into a single string
        combined_content = []
        for report in reports:
            # The timestamp is stored as an ISO string, so we need to parse it back into a datetime object first
            timestamp_obj = datetime.datetime.fromisoformat(report.generation_timestamp)
            header = f"# Report: {report.report_name}\n**Generated On:** {timestamp_obj.strftime('%Y-%m-%d %H:%M:%S UTC')}\n\n---\n\n"
            combined_content.append(header)
            combined_content.append(report.report_content)
            combined_content.append("\n\n") # Add space between reports

        full_report_string = "".join(combined_content)
        
        return HTMLResponse(
            content=full_report_string,
            headers={
                "Content-Disposition": "attachment; filename=secops_reports.md",
                "Content-Type": "text/markdown",
            }
        )
    finally:
        db_session.close()


# --- Setup Wizard Endpoints ---

@app.post("/api/setup/initialize_db")
async def initialize_database():
    """
    Initializes the database. This endpoint is safe to call even if the DB exists,
    but the frontend should ideally only call it once.
    """
    try:
        print("--- Received request to initialize database... ---")
        init_db()
        # We also call the seeder function here to be absolutely sure the types are created.
        seed_audit_types()
        print("--- Database initialization complete. ---")
        return {"message": "Database initialized successfully."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database initialization failed: {e}")

@app.post("/api/setup/discover_tenants")
async def discover_tenants(request: dict):
    """
    Triggers the background task to discover tenants from GCP Asset Inventory.
    """
    organization_id = request.get("organization_id")
    if not organization_id:
        raise HTTPException(status_code=400, detail="Organization ID is required.")
    
    task = discover_tenants_task.delay(organization_id)
    print(f"--- Tenant discovery task {task.id} started for Organization ID: {organization_id} ---")
    return {"message": "Tenant discovery started.", "task_id": task.id}


@app.post("/api/setup/manual_tenant")
async def create_manual_tenant(request: ManualTenantRequest):
    """
    Manually adds a new tenant (Project) to the database.
    """
    db_session = create_db_session()
    try:
        existing_project = db_session.query(Project).filter_by(id=request.project_id).first()
        if existing_project:
            raise HTTPException(status_code=409, detail="A project with this ID already exists.")

        new_project = Project(
            id=request.project_id,
            display_name=request.display_name,
            discovery_method="MANUAL"
        )
        db_session.add(new_project)
        db_session.commit()
        db_session.refresh(new_project)
        return {"message": "Manual tenant created successfully", "project_id": new_project.id}
    except Exception as e:
        db_session.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to create manual tenant: {e}")
    finally:
        db_session.close()


# --- Custom YL2 Query Endpoints ---

@app.get("/api/yl2_queries")
async def get_yl2_queries():
    db_session = create_db_session()
    try:
        queries = db_session.query(CustomYL2Query).all()
        return [
            {
                "id": q.id,
                "name": q.name,
                "category": q.category,
                "query": q.yl2_query,
                "time_unit": q.time_unit,
                "time_value": q.time_value
            } for q in queries
        ]
    finally:
        db_session.close()

@app.post("/api/yl2_queries")
def create_yl2_query(request: CustomYL2QueryRequest):
    print(f"--- Received YL2 Query Request: {request.model_dump_json()} ---")
    db_session = create_db_session()
    try:
        new_query = CustomYL2Query(**request.model_dump())
        db_session.add(new_query)
        db_session.commit()
        db_session.refresh(new_query)
        return {"message": "Custom query created successfully", "id": new_query.id}
    except IntegrityError:
        db_session.rollback()
        raise HTTPException(status_code=409, detail="A custom query with this name already exists.")
    finally:
        db_session.close()

@app.put("/api/yl2_queries/{query_id}")
async def update_yl2_query(query_id: int, request: CustomYL2QueryRequest):
    db_session = create_db_session()
    try:
        query = db_session.query(CustomYL2Query).filter_by(id=query_id).first()
        if not query:
            raise HTTPException(status_code=404, detail="Custom query not found")
        
        query.name = request.name
        query.category = request.category
        query.yl2_query = request.yl2_query
        query.time_unit = request.time_unit
        query.time_value = request.time_value
        
        db_session.commit()
        return {"message": "Custom query updated successfully"}
    except IntegrityError:
        db_session.rollback()
        raise HTTPException(status_code=409, detail="A custom query with this name already exists.")
    finally:
        db_session.close()

@app.delete("/api/yl2_queries/{query_id}")
async def delete_yl2_query(query_id: int):
    db_session = create_db_session()
    try:
        query = db_session.query(CustomYL2Query).filter_by(id=query_id).first()
        if not query:
            raise HTTPException(status_code=404, detail="Custom query not found")
        
        db_session.delete(query)
        db_session.commit()
        return {"message": "Custom query deleted successfully"}
    finally:
        db_session.close()


# --- Configurable Audit Endpoints ---

@app.get("/api/audit_types")
async def get_audit_types():
    db_session = create_db_session()
    try:
        types = db_session.query(AuditType).all()
        return [{"id": type.id, "name": type.name, "description": type.description} for type in types]
    finally:
        db_session.close()

@app.get("/api/configurable_audits")
async def get_configurable_audits():
    db_session = create_db_session()
    try:
        audits = db_session.query(ConfigurableAudit).join(AuditType).all()
        return [
            {
                "id": audit.id,
                "name": audit.name,
                "category": audit.category,
                "api_path": audit.api_path,
                "method": audit.method,
                "response_key": audit.response_key,
                "default_page_size": audit.default_page_size,
                "audit_type_id": audit.audit_type_id,
                "audit_type_name": audit.audit_type.name,
                "audit_type_icon": audit.audit_type.icon,
                "response_format": audit.response_format,
                "pagination_token_key": audit.pagination_token_key,
                "pagination_results_key": audit.pagination_results_key,
                "pagination_request_token_key": audit.pagination_request_token_key,
                "max_pages": audit.max_pages
            } for audit in audits
        ]
    finally:
        db_session.close()

@app.get("/api/audits/export")
async def export_audits_configuration():
    """
    Exports the current configurable audits, their prompts, and custom YL2 queries as a JSON file.
    """
    db_session = create_db_session()
    try:
        export_data = []

        # 1. Fetch all standard configurable audits and their prompts
        audits = db_session.query(ConfigurableAudit).options(joinedload(ConfigurableAudit.audit_type)).all()
        prompts = db_session.query(AuditPrompt).all()
        prompts_map = {p.audit_name: p for p in prompts}

        for audit in audits:
            prompt_obj = prompts_map.get(audit.name)
            export_data.append({
                "name": audit.name,
                "category": audit.category,
                "api_path": audit.api_path,
                "method": audit.method,
                "response_key": audit.response_key,
                "default_page_size": audit.default_page_size,
                "max_pages": audit.max_pages,
                "audit_type_name": audit.audit_type.name,
                "response_format": audit.response_format,
                "pagination_token_key": audit.pagination_token_key,
                "pagination_results_key": audit.pagination_results_key,
                "pagination_request_token_key": audit.pagination_request_token_key,
                "prompt_text": prompt_obj.prompt_text if prompt_obj else "",
                "excluded_fields": prompt_obj.excluded_fields if prompt_obj else ""
            })

        # 2. Fetch all Custom YL2 Queries
        custom_queries = db_session.query(CustomYL2Query).all()
        for q in custom_queries:
            prompt_obj = prompts_map.get(q.name)
            export_data.append({
                "name": q.name,
                "category": q.category,
                "audit_type_name": "Custom YL2", # Explicitly set the type
                "yl2_query": q.yl2_query,
                "time_unit": q.time_unit,
                "time_value": q.time_value,
                "prompt_text": prompt_obj.prompt_text if prompt_obj else "",
                "excluded_fields": prompt_obj.excluded_fields if prompt_obj else ""
            })

        return export_data
    finally:
        db_session.close()


@app.post("/api/configurable_audits")
async def create_configurable_audit(request: ConfigurableAuditRequest):
    db_session = create_db_session()
    try:
        request_data = request.model_dump()
        api_path = request_data.get('api_path')
        if api_path and api_path.startswith('/'):
            request_data['api_path'] = api_path.lstrip('/')

        new_audit = ConfigurableAudit(**request_data)
        db_session.add(new_audit)
        db_session.commit()
        db_session.refresh(new_audit)
        return {"message": "Audit created successfully", "id": new_audit.id}
    except IntegrityError:
        db_session.rollback()
        raise HTTPException(status_code=409, detail="An audit with this name already exists.")
    finally:
        db_session.close()

@app.put("/api/configurable_audits/{audit_id}")
async def update_configurable_audit(audit_id: int, request: ConfigurableAuditRequest):
    db_session = create_db_session()
    try:
        audit = db_session.query(ConfigurableAudit).filter_by(id=audit_id).first()
        if not audit:
            raise HTTPException(status_code=404, detail="Audit not found")
        
        request_data = request.model_dump()
        api_path = request_data.get('api_path')
        if api_path and api_path.startswith('/'):
            request_data['api_path'] = api_path.lstrip('/')

        for key, value in request_data.items():
            setattr(audit, key, value)
            
        db_session.commit()
        return {"message": "Audit updated successfully"}
    except IntegrityError:
        db_session.rollback()
        raise HTTPException(status_code=409, detail="An audit with this name already exists.")
    finally:
        db_session.close()

@app.delete("/api/configurable_audits/{audit_id}")
async def delete_configurable_audit(audit_id: int):
    db_session = create_db_session()
    try:
        audit = db_session.query(ConfigurableAudit).filter_by(id=audit_id).first()
        if not audit:
            raise HTTPException(status_code=404, detail="Audit not found")
        
        db_session.delete(audit)
        db_session.commit()
        return {"message": "Audit deleted successfully"}
    finally:
        db_session.close()


# --- Insight Endpoints ---

@app.get("/api/insights")
async def get_insights():
    db_session = create_db_session()
    try:
        insights = db_session.query(Insight).all()
        return [
            {
                "id": insight.id,
                "title": insight.title,
                "prompt": insight.prompt,
                "audit_sources": insight.audit_sources.split(','),
                "excluded_fields": insight.excluded_fields
            } for insight in insights
        ]
    finally:
        db_session.close()

@app.post("/api/insights")
def create_insight(request: InsightCreate):
    db_session = create_db_session()
    try:
        # Proactively check if an insight with the same title already exists
        existing_insight = db_session.query(Insight).filter_by(title=request.title).first()
        if existing_insight:
            raise HTTPException(status_code=409, detail="An insight with this title already exists.")

        # --- New Logic: Validate against all available audits ---
        all_audits = list_available_audits()
        for source_name in request.audit_sources:
            if source_name not in all_audits:
                raise HTTPException(status_code=404, detail=f"Audit source '{source_name}' not found.")

        new_insight = Insight(
            title=request.title,
            prompt=request.prompt,
            excluded_fields=request.excluded_fields,
            audit_sources=",".join(request.audit_sources) # Store as comma-separated string
        )
        db_session.add(new_insight)
        db_session.commit()
        db_session.refresh(new_insight)
        return {"message": "Insight created successfully", "insight_id": new_insight.id}
    except IntegrityError: # Fallback for race conditions
        db_session.rollback()
        raise HTTPException(status_code=409, detail="An insight with this title already exists.")
    except HTTPException as e:
        # Re-raise HTTP exceptions to return proper status codes
        raise e
    except Exception as e:
        db_session.rollback()
        print(f"--- Unexpected error creating insight: {e} ---")
        # Use the detail from the original exception if it's an HTTPException
        error_detail = e.detail if isinstance(e, HTTPException) else "An internal server error occurred."
        raise HTTPException(status_code=500, detail=error_detail)
    finally:
        db_session.close()

@app.put("/api/insights/{insight_id}")
def update_insight(insight_id: int, request: InsightCreate):
    db_session = create_db_session()
    try:
        insight = db_session.query(Insight).filter_by(id=insight_id).first()
        if not insight:
            raise HTTPException(status_code=404, detail="Insight not found")

        # --- New Logic: Validate against all available audits ---
        all_audits = list_available_audits()
        for source_name in request.audit_sources:
            if source_name not in all_audits:
                raise HTTPException(status_code=404, detail=f"Audit source '{source_name}' not found.")

        insight.title = request.title
        insight.prompt = request.prompt
        insight.excluded_fields = request.excluded_fields
        insight.audit_sources = ",".join(request.audit_sources)
        
        db_session.commit()
        return {"message": "Insight updated successfully"}
    finally:
        db_session.close()

@app.delete("/api/insights/{insight_id}")
async def delete_insight(insight_id: int):
    db_session = create_db_session()
    insight = db_session.query(Insight).filter_by(id=insight_id).first()
    if not insight:
        raise HTTPException(status_code=404, detail="Insight not found")
    
    db_session.delete(insight)
    db_session.commit()
    db_session.close()
    return {"message": "Insight deleted successfully"}

@app.post("/api/tenants/{project_id}/insights/{insight_id}/run")
async def run_insight(project_id: str, insight_id: int):
    """
    Starts the Insight report generation task in the background.
    """
    task = generate_insight_report_task.delay(project_id, insight_id)
    print(f"--- Started Insight generation task with ID: {task.id} ---")
    return {"message": "Insight generation started.", "task_id": task.id}


# --- MCP Agent Endpoint ---

@app.get("/api/mcp/tools")
async def get_mcp_tools():
    """
    Returns a list of available tool names for the MCP Assistant.
    """
    return {"tools": list(TOOL_REGISTRY.keys())}

@app.post("/api/mcp/chat")
async def chat_with_agent(request: ChatRequest):
    """
    Handles a chat message from the user and returns the agent's response.
    """
    if not mcp_chat_session:
        raise HTTPException(status_code=503, detail="MCP Agent not initialized. Check server startup logs.")
    
    print(f"--- Received user message for MCP Agent: '{request.message}' ---")
    agent_response = mcp_agent.run_chat_message(mcp_chat_session, request.message)
    
    return {"response": agent_response}

@app.post("/api/mcp/new_session")
async def new_chat_session():
    """
    Resets the current MCP agent chat session.
    """
    global mcp_chat_session
    print("--- Received request to start a new MCP chat session... ---")
    mcp_chat_session = mcp_agent.start_chat_session()
    clear_session_state() # Clear the session state for the new session
    print("--- New MCP Agent session created. ---")
    return {"message": "New chat session started."}

@app.post("/api/mcp/run_tool")
async def run_tool_directly(request: ToolRunRequest):
    """
    Directly executes a tool from the TOOL_REGISTRY.
    """
    command_parts = request.command.strip().split(maxsplit=1)
    tool_name = command_parts[0]
    args_str = command_parts[1] if len(command_parts) > 1 else ""

    if tool_name not in TOOL_REGISTRY:
        raise HTTPException(status_code=404, detail=f"Tool '{tool_name}' not found.")

    tool_function = TOOL_REGISTRY[tool_name]
    
    # Basic parsing of string args into a dict. This is a simplified approach.
    # For example: "arg1='value1' arg2='value2'"
    try:
        kwargs = {}
        if args_str:
            # This is a simple parser; it might not handle complex cases.
            # It assumes args are space-separated key='value' pairs.
            import shlex
            parts = shlex.split(args_str)
            for part in parts:
                key, value = part.split('=', 1)
                # Remove quotes from value if present
                if (value.startswith("'") and value.endswith("'")) or \
                   (value.startswith('"') and value.endswith('"')):
                    value = value[1:-1]
                kwargs[key] = value
        
        # Execute the tool
        result = tool_function(**kwargs)
        return {"response": result}

    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error executing tool '{tool_name}': {e}")


# --- Dashboard Endpoints ---

@app.get("/api/dashboard/stats")
async def get_dashboard_stats():
    db_session = create_db_session()
    try:
        # 1. Tenants
        all_projects = db_session.query(Project).all()
        total_tenants = len(all_projects)
        configured_tenants = sum(1 for p in all_projects if p.secops_config is not None)
        unconfigured_tenants = total_tenants - configured_tenants

        # 2. Audits
        total_audit_definitions = db_session.query(ConfigurableAudit).count() + db_session.query(CustomYL2Query).count()
        total_audit_runs = db_session.query(Audit).count()

        # 3. Insights
        total_insights = db_session.query(Insight).count()

        # 4. Schedules
        total_schedules = db_session.query(Schedule).count()
        active_schedules = db_session.query(Schedule).filter_by(is_enabled=True).count()
        
        # Get the latest run time across all schedules (string comparison works for ISO format)
        last_schedule_run = db_session.query(func.max(Schedule.last_run_at)).scalar()

        # 5. Settings Stats
        custom_prompts_count = db_session.query(AuditPrompt).count()
        custom_yl2_queries_count = db_session.query(CustomYL2Query).count()
        configurable_audits_count = db_session.query(ConfigurableAudit).count()

        # 6. Recent Reports (Last 5)
        recent_reports = db_session.query(Report, Project.display_name)\
            .join(Project)\
            .order_by(Report.generation_timestamp.desc())\
            .limit(5).all()
        
        recent_reports_list = [
            {
                "id": r.id,
                "report_name": r.report_name,
                "generation_timestamp": r.generation_timestamp,
                "project_name": p_name
            } for r, p_name in recent_reports
        ]

        return {
            "tenants": {
                "total": total_tenants,
                "configured": configured_tenants,
                "unconfigured": unconfigured_tenants
            },
            "audits": {
                "total_definitions": total_audit_definitions,
                "total_runs": total_audit_runs
            },
            "insights": {
                "total": total_insights
            },
            "schedules": {
                "total": total_schedules,
                "active": active_schedules,
                "last_run": last_schedule_run
            },
            "settings": {
                "custom_prompts": custom_prompts_count,
                "yl2_queries": custom_yl2_queries_count,
                "configurable_audits": configurable_audits_count
            },
            "recent_reports": recent_reports_list
        }
    finally:
        db_session.close()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
