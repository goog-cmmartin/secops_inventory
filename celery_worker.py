from celery import Celery
from celery.schedules import crontab
import json
import datetime
import configparser
import os
import google.generativeai as genai
import io # Import the io module
from croniter import croniter

from database_setup import create_db_session, Project, Audit, Report, Insight, Schedule, AuditPrompt, ConfigurableAudit
from utils import generate_gemini_summary, remove_excluded_fields, generate_json_diff, convert_secops_json_to_csv
from audit_logic import list_available_audits_from_db # Import the function
from sqlalchemy.orm import joinedload

# --- Celery Configuration ---
celery_app = Celery(
    "tasks",
    broker="redis://localhost:6379/0",
    backend="redis://localhost:6379/0",
    include=['audit_logic', 'gcp_asset_inventory']
)
celery_app.conf.update(
    task_serializer='pickle',
    result_serializer='pickle',
    event_serializer='pickle',
    accept_content=['pickle']
)

# --- Celery Beat Schedule ---
celery_app.conf.beat_schedule = {
    'schedule-ticker-every-minute': {
        'task': 'celery_worker.schedule_ticker',
        'schedule': crontab(),  # This runs every minute
    },
}
celery_app.conf.timezone = 'UTC'


@celery_app.task
def schedule_ticker():
    """
    This task runs every minute, checks for due schedules, and triggers them.
    """
    now = datetime.datetime.now(datetime.timezone.utc)
    print(f"--- Schedule Ticker Running at {now.isoformat()} ---")
    db_session = create_db_session()
    try:
        schedules = db_session.query(Schedule).filter_by(is_enabled=True).all()
        for schedule in schedules:
            # A more robust check to see if a scheduled time has passed since the last run.
            itr = croniter(schedule.cron_schedule, now)
            prev_run = itr.get_prev(datetime.datetime)

            should_run = False
            # If it has run before, check if the previous scheduled time is after the last run time.
            if schedule.last_run_at:
                last_run_time = datetime.datetime.fromisoformat(schedule.last_run_at)
                if prev_run > last_run_time:
                    should_run = True
            # If it has never run, check if the previous scheduled time is recent (e.g., within the last 5 mins).
            # This handles the case where a schedule is created just before its run time.
            else:
                if (now - prev_run).total_seconds() < 300: # 5 minutes
                    should_run = True
            
            print(f"--- Checking '{schedule.name}': Last run={schedule.last_run_at}, Prev run={prev_run.isoformat()}, Now={now.isoformat()}, Should run={should_run} ---")

            if should_run:
                print(f"--- Triggering schedule: {schedule.name} (ID: {schedule.id}) ---")
                run_scheduled_job.delay(schedule.id)
                schedule.last_run_at = now.isoformat()
                db_session.commit()
    finally:
        db_session.close()


@celery_app.task
def run_scheduled_job(schedule_id):
    """
    Runs a scheduled job based on its type (audit or report).
    """
    from audit_logic import run_audit_logic # Defer import to avoid circular dependency
    db_session = create_db_session()
    try:
        schedule = db_session.query(Schedule).get(schedule_id)
        if not schedule:
            return

        project_id = schedule.tenant_project_id

        if schedule.schedule_type == 'audit':
            audit_names = [audit.name for audit in schedule.audits_to_run]
            # Run all audits sequentially
            for audit_name in audit_names:
                try:
                    run_audit_logic(project_id, {"audit_name": audit_name})
                except Exception as e:
                    print(f"--- Error running audit '{audit_name}' for schedule '{schedule.name}': {e} ---")
                    continue
        
        elif schedule.schedule_type == 'report':
            audit_names = [audit.name for audit in schedule.audits_for_report]
            # Trigger the report generation
            generate_report_task.delay(project_id, audit_names, schedule.report_name_format)
        
        elif schedule.schedule_type == 'diff':
            audit_names = [audit.name for audit in schedule.audits_for_diff]
            # Trigger the combined diff report generation
            generate_combined_diff_report_task.delay(project_id, audit_names, schedule.report_name_format)

    finally:
        db_session.close()


@celery_app.task(bind=True)
def generate_report_task(self, project_id: str, audit_names: list[str], report_name_format: str = None):
    """
    Celery task to generate a report from multiple audit results.
    """
    db_session = create_db_session()
    try:
        # --- Load Model for Token Counting ---
        config = configparser.ConfigParser()
        config_path = os.path.join(os.path.dirname(__file__), 'config.ini')
        config.read(config_path)
        model_name = config.get('gemini', 'model_name', fallback='gemini-1.5-flash')
        model = genai.GenerativeModel(model_name)

        try:
            report_content = []
            total_audits = len(audit_names)
            
            for i, audit_name in enumerate(audit_names):
                self.update_state(state='PROGRESS', meta={'status': f"Processing {audit_name} ({i+1}/{total_audits})..."})
                
                latest_audit = db_session.query(Audit).options(joinedload(Audit.project)).filter_by(
                    tenant_project_id=project_id,
                    audit_name=audit_name,
                    status="Success"
                ).order_by(Audit.run_timestamp.desc()).first()

                if not latest_audit:
                    report_content.append(f"## {audit_name}\n\nNo successful audit run found.\n\n")
                    continue

                # Fetch prompt and exclusions
                prompt_obj = db_session.query(AuditPrompt).filter_by(audit_name=audit_name).first()
                prompt_text = prompt_obj.prompt_text if prompt_obj else f"Summarize the key findings for the '{audit_name}' audit."
                excluded_fields = prompt_obj.excluded_fields.split(',') if prompt_obj and prompt_obj.excluded_fields else []

                # Fetch all available audit definitions to check the type
                all_audits = list_available_audits_from_db()
                audit_definition = all_audits.get(audit_name)

                try:
                    audit_results = json.loads(latest_audit.results)
                    data_to_summarize_str = ""

                    if audit_definition and audit_definition.get("audit_type_name") == "Custom YL2":
                        print(f"--- DEBUG: Converting YL2 JSON to CSV for '{audit_name}'. ---")
                        
                        original_tokens = model.count_tokens(json.dumps(audit_results, indent=2)).total_tokens
                        print(f"--- DEBUG: Original JSON token count for '{audit_name}': {original_tokens} ---")

                        data_to_summarize_str = convert_secops_json_to_csv(audit_results)
                        
                        new_tokens = model.count_tokens(data_to_summarize_str).total_tokens
                        print(f"--- DEBUG: Converted CSV token count for '{audit_name}': {new_tokens} ---")

                    else:
                        # Fallback for non-YL2 audits
                        configurable_audit = db_session.query(ConfigurableAudit).options(joinedload(ConfigurableAudit.audit_type)).filter(ConfigurableAudit.name == audit_name).first()
                        response_key = configurable_audit.response_key if configurable_audit else None
                        
                        filtered_results = remove_excluded_fields(audit_results, excluded_fields)
                        final_data = filtered_results
                        if response_key and isinstance(filtered_results, dict) and response_key in filtered_results:
                            final_data = filtered_results[response_key]
                        
                        data_to_summarize_str = json.dumps(final_data, indent=2)

                    summary = generate_gemini_summary(self, prompt_text, data_to_summarize_str, audit_name)
                    if isinstance(summary, dict) and "error" in summary:
                        summary_content = f"Error generating summary: {summary['error']}"
                    else:
                        summary_content = summary
                    report_content.append(f"## {audit_name}\n\n{summary_content}\n\n")

                except AttributeError as e:
                    print(f"--- ERROR: Skipping audit '{audit_name}' due to a data error: {e} ---")
                    report_content.append(f"## {audit_name}\n\nCould not process this audit due to a data error.\n\n")
                    continue

            self.update_state(state='PROGRESS', meta={'status': 'Finalizing report...'})
            full_report = "".join(report_content)
            
            now = datetime.datetime.utcnow()
            if report_name_format:
                report_name = report_name_format.format(date=now.strftime("%Y-%m-%d"), time=now.strftime("%H:%M"))
            else:
                report_name = f"Ad-Hoc Report - {now.strftime('%Y-%m-%d %H:%M')}"

            new_report = Report(
                tenant_project_id=project_id,
                report_name=report_name,
                generation_timestamp=now.isoformat(),
                report_content=full_report,
                status="Completed"
            )
            db_session.add(new_report)
            db_session.commit()
            
            return {'status': 'Report generated successfully!', 'report_id': new_report.id}
        except Exception as e:
            import traceback
            print(f"--- UNHANDLED EXCEPTION IN GENERATE_REPORT_TASK: {e} ---")
            print(traceback.format_exc())
            self.update_state(state='FAILURE', meta={'status': str(e)})
            raise e
    finally:
        db_session.close()


@celery_app.task(bind=True)
def generate_combined_diff_report_task(self, project_id: str, audit_names: list[str], report_name_format: str = None):
    """
    Celery task to generate a combined diff report for multiple audits (comparing last 2 runs).
    """
    db_session = create_db_session()
    try:
        report_content = []
        total_audits = len(audit_names)
        
        # --- Load Model for Token Counting (if needed later) ---
        # config = configparser.ConfigParser()
        # ... (setup if needed)

        changes_found = False

        for i, audit_name in enumerate(audit_names):
            self.update_state(state='PROGRESS', meta={'status': f"Analyzing diffs for {audit_name} ({i+1}/{total_audits})..."})
            
            # Fetch last 2 successful runs
            last_two_runs = db_session.query(Audit).filter_by(
                tenant_project_id=project_id,
                audit_name=audit_name,
                status="Success"
            ).order_by(Audit.run_timestamp.desc()).limit(2).all()

            if len(last_two_runs) < 2:
                report_content.append(f"## {audit_name}\n\n*Insufficient history to generate a diff (needs at least 2 successful runs).*\n\n")
                continue

            latest_run = last_two_runs[0]
            previous_run = last_two_runs[1]

            # --- Apply Field Exclusions ---
            try:
                # Fetch exclusions configuration
                prompt_obj = db_session.query(AuditPrompt).filter_by(audit_name=audit_name).first()
                excluded_fields = prompt_obj.excluded_fields.split(',') if prompt_obj and prompt_obj.excluded_fields else []

                # Parse JSON results
                latest_data = json.loads(latest_run.results)
                previous_data = json.loads(previous_run.results)

                # Filter data
                if excluded_fields:
                    latest_data = remove_excluded_fields(latest_data, excluded_fields)
                    previous_data = remove_excluded_fields(previous_data, excluded_fields)
                
                # Dump back to string for diffing (or modify generate_json_diff to accept dicts, but string is safer for now)
                # generate_json_diff expects strings if they are raw JSON, or we can pass dicts if it supports it.
                # Let's check utils.py... generate_json_diff takes (json_data_old, json_data_new, ...) and handles loading if string.
                # So we can pass the dicts directly if modified, or dump them.
                # To be safe and consistent with previous logic, let's pass them as strings if that's what it expects, 
                # but wait, let's check generate_json_diff signature in utils.py.
                # Assuming it takes strings or dicts. Let's pass the filtered dicts directly if possible, or dumps.
                # Checking imports: from utils import ..., generate_json_diff
                
                # Let's assume we pass the filtered data. To be 100% sure we match the expected input types of generate_json_diff
                # (which likely does a json.loads if input is string), let's verify or just pass strings.
                # Passing strings is safest without seeing utils.py source right now.
                latest_data_str = json.dumps(latest_data)
                previous_data_str = json.dumps(previous_data)

            except Exception as e:
                print(f"--- Error applying exclusions for '{audit_name}': {e} ---")
                # Fallback to raw results if parsing/filtering fails
                latest_data_str = latest_run.results
                previous_data_str = previous_run.results

            # Generate Diff
            try:
                diff_text = generate_json_diff(
                    previous_data_str, 
                    latest_data_str,
                    fromfile=f"Previous Run ({previous_run.run_timestamp})",
                    tofile=f"Latest Run ({latest_run.run_timestamp})"
                )

                if "No differences found" in diff_text:
                    # Option 1: Complete Suppression - Do not append anything if no changes
                    pass 
                else:
                    changes_found = True
                    # Summarize the diff
                    diff_prompt = (
                        f"You are a security analyst. The following is a 'diff' report for the '{audit_name}' audit. "
                        "Lines starting with '+' indicate additions, and lines starting with '-' indicate deletions. "
                        "Please provide a concise, high-level summary of the most significant changes. "
                        "Focus on what was added, removed, or modified that would be important for a security team to know. "
                        "Use Markdown for formatting."
                    )
                    summary = generate_gemini_summary(self, diff_prompt, diff_text, f"Diff Summary: {audit_name}")
                    if isinstance(summary, dict) and "error" in summary:
                         report_content.append(f"## {audit_name}\n\nError generating diff summary: {summary['error']}\n\n")
                    else:
                        report_content.append(f"## {audit_name}\n\n{summary}\n\n")

            except Exception as e:
                print(f"--- Error generating diff for '{audit_name}': {e} ---")
                report_content.append(f"## {audit_name}\n\nError processing diff: {e}\n\n")

        self.update_state(state='PROGRESS', meta={'status': 'Finalizing report...'})
        
        full_report = "".join(report_content)
        
        if not changes_found and not report_content: # If no actual diffs and no errors/warnings
            full_report = "## No Significant Changes Detected\n\nNo configuration changes were detected across the selected audits for this period. All systems are consistent with the previous audit run.\n\n"
        elif not changes_found and report_content: # If only warnings/errors, but no actual diffs
            full_report = "## Audit Status Summary (No Configuration Changes Detected)\n\nWhile no configuration changes were found, the following audits reported issues or insufficient history:\n\n" + full_report

        now = datetime.datetime.utcnow()
        if report_name_format:
            report_name = report_name_format.format(date=now.strftime("%Y-%m-%d"), time=now.strftime("%H:%M"))
        else:
            report_name = f"Daily Change Report - {now.strftime('%Y-%m-%d %H:%M')}"

        new_report = Report(
            tenant_project_id=project_id,
            report_name=report_name,
            generation_timestamp=now.isoformat(),
            report_content=full_report,
            status="Completed"
        )
        db_session.add(new_report)
        db_session.commit()
        
        return {'status': 'Diff report generated successfully!', 'report_id': new_report.id}

    except Exception as e:
        self.update_state(state='FAILURE', meta={'status': str(e)})
        raise e
    finally:
        db_session.close()


@celery_app.task(bind=True)
def generate_insight_report_task(self, project_id: str, insight_id: int):
    """
    Celery task to generate a report from multiple audit sources based on an Insight.
    """
    db_session = create_db_session()
    try:
        insight = db_session.query(Insight).get(insight_id)
        if not insight:
            raise ValueError("Insight not found.")

        self.update_state(state='PROGRESS', meta={'status': 'Fetching audit data...'}) 
        
        combined_audit_data = {}
        audit_sources = insight.audit_sources.split(',')
        excluded_fields = insight.excluded_fields.split(',') if insight.excluded_fields else []

        for audit_name in audit_sources:
            latest_audit = db_session.query(Audit).filter_by(
                tenant_project_id=project_id,
                audit_name=audit_name,
                status="Success"
            ).order_by(Audit.run_timestamp.desc()).first()

            if latest_audit:
                audit_results = json.loads(latest_audit.results)
                filtered_results = remove_excluded_fields(audit_results, excluded_fields)
                combined_audit_data[audit_name] = filtered_results
            else:
                combined_audit_data[audit_name] = "No successful audit run found."

        self.update_state(state='PROGRESS', meta={'status': 'Generating AI summary...'}) 
        
        summary = generate_gemini_summary(self, insight.prompt, json.dumps(combined_audit_data, indent=2), insight.title)
        
        self.update_state(state='PROGRESS', meta={'status': 'Finalizing report...'}) 

        timestamp = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M")
        report_name = f"Insight Report: {insight.title} - {timestamp}"

        new_report = Report(
            tenant_project_id=project_id,
            report_name=report_name,
            generation_timestamp=datetime.datetime.utcnow().isoformat(),
            report_content=summary,
            status="Completed"
        )
        db_session.add(new_report)
        db_session.commit()

        return {'status': 'Insight report generated successfully!', 'report_id': new_report.id}

    except Exception as e:
        self.update_state(state='FAILURE', meta={'status': str(e)})
        return {'status': f"An error occurred: {e}"}
    finally:
        db_session.close()


@celery_app.task(bind=True)
def discover_tenants_task(self, organization_id: str):
    """
    Celery task to discover tenants from GCP Asset Inventory.
    """
    from gcp_asset_inventory import main as run_discovery # Local import
    
    self.update_state(state='PROGRESS', meta={'status': 'Starting GCP Asset Inventory discovery...'}) 
    try:
        # This is a simplified call; you might need to adapt how you pass arguments
        # or handle the output of your script.
        run_discovery(organization_id) 
        
        self.update_state(state='PROGRESS', meta={'status': 'Discovery process finished.'})
        return {'status': 'Tenant discovery completed successfully!'}
    except Exception as e:
        self.update_state(state='FAILURE', meta={'status': f"An error occurred during discovery: {e}"})
        return {'status': f"An error occurred: {e}"}


@celery_app.task(bind=True)
def generate_diff_report_task(self, audit_id_1: int, audit_id_2: int):
    """
    Celery task to generate a diff report between two specific successful audits.
    """
    db_session = create_db_session()
    try:
        self.update_state(state='PROGRESS', meta={'status': 'Finding specified audit runs...'})
        
        # Query for the two specific audits
        audit1 = db_session.query(Audit).get(audit_id_1)
        audit2 = db_session.query(Audit).get(audit_id_2)

        # --- Validation ---
        if not audit1 or not audit2:
            raise ValueError("One or both of the specified audit runs could not be found.")
        if audit1.status != "Success" or audit2.status != "Success":
            raise ValueError("One or both of the selected audits were not successful runs.")
        if audit1.tenant_project_id != audit2.tenant_project_id or audit1.audit_name != audit2.audit_name:
            raise ValueError("The selected audits are not from the same tenant and for the same audit type.")

        # Determine which is older (previous) and newer (latest)
        if audit1.run_timestamp < audit2.run_timestamp:
            previous_run, latest_run = audit1, audit2
        else:
            previous_run, latest_run = audit2, audit1
        
        project_id = latest_run.tenant_project_id
        audit_name = latest_run.audit_name

        self.update_state(state='PROGRESS', meta={'status': 'Generating difference report...'})
        
        # Call the diff utility
        diff_text = generate_json_diff(
            previous_run.results, 
            latest_run.results,
            fromfile=f"run_at_{previous_run.run_timestamp}",
            tofile=f"run_at_{latest_run.run_timestamp}"
        )

        if "No differences found" in diff_text:
             summary = "No differences found between the two selected audit runs."
        else:
            self.update_state(state='PROGRESS', meta={'status': 'Summarizing changes with AI...'})
            
            # Create a specialized prompt
            diff_prompt = (
                "You are a security analyst. The following is a 'diff' report showing the changes between two security audits. "
                "Lines starting with '+' indicate additions, and lines starting with '-' indicate deletions. "
                "Please provide a concise, high-level summary of the most significant changes. "
                "Focus on what was added, removed, or modified that would be important for a security team to know. "
                "Use Markdown for formatting. Do not simply list the changes; interpret them."
            )

            # Call Gemini
            summary = generate_gemini_summary(self, diff_prompt, diff_text, f"Diff for {audit_name}")

        self.update_state(state='PROGRESS', meta={'status': 'Finalizing report...'})
        
        # Save the new report
        timestamp = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M")
        report_name = f"Diff Report: {audit_name} - {timestamp}"

        new_report = Report(
            tenant_project_id=project_id,
            report_name=report_name,
            generation_timestamp=datetime.datetime.utcnow().isoformat(),
            report_content=summary,
            status="Completed"
        )
        db_session.add(new_report)
        db_session.commit()

        return {'status': 'Diff report generated successfully!', 'report_id': new_report.id}

    except Exception as e:
        self.update_state(state='FAILURE', meta={'status': str(e)})
        return {'status': f"An error occurred: {e}"}
    finally:
        db_session.close()


@celery_app.task(bind=True)
def purge_audits_task(self, older_than_days: int, audit_name: str = None):
    """
    Celery task to delete old audit records from the database.
    """
    db_session = create_db_session()
    try:
        self.update_state(state='PROGRESS', meta={'status': 'Calculating cutoff date...'})
        
        cutoff_date = datetime.datetime.utcnow() - datetime.timedelta(days=older_than_days)
        
        self.update_state(state='PROGRESS', meta={'status': f"Querying for audits older than {cutoff_date.strftime('%Y-%m-%d')}..."})

        query = db_session.query(Audit).filter(Audit.run_timestamp < cutoff_date.isoformat())

        if audit_name:
            self.update_state(state='PROGRESS', meta={'status': f"Filtering by audit name: {audit_name}..."})
            query = query.filter(Audit.audit_name == audit_name)

        # Get the count of records to be deleted for the report
        count_to_delete = query.count()

        if count_to_delete == 0:
            return {'status': 'No old audits found to purge.'}

        self.update_state(state='PROGRESS', meta={'status': f"Deleting {count_to_delete} audit records..."})
        
        query.delete(synchronize_session=False)
        db_session.commit()

        return {'status': f"Successfully purged {count_to_delete} audit records."}

    except Exception as e:
        db_session.rollback()
        self.update_state(state='FAILURE', meta={'status': str(e)})
        return {'status': f"An error occurred during purge: {e}"}
    finally:
        db_session.close()


@celery_app.task(bind=True)
def test_large_summary_task(self):
    """
    A test task to verify the chunking and map-reduce summarization logic.
    """
    try:
        self.update_state(state='PROGRESS', meta={'status': 'Generating large dummy data...'})
        print("--- Starting large summary test task. ---")

        # Generate a very large string (approx. 2 million chars)
        large_string = "This is a test string. " * 100000
        
        prompt = "This is a test. Please summarize the following text."
        audit_name = "Large Data Test"

        self.update_state(state='PROGRESS', meta={'status': 'Calling summarization function...'})
        
        # Call the summarization function with the oversized data
        summary = generate_gemini_summary(self, prompt, large_string, audit_name)

        print(f"--- Large summary test completed. Final summary length: {len(summary)} ---")
        return {'status': 'Test completed successfully!', 'summary': summary}

    except Exception as e:
        self.update_state(state='FAILURE', meta={'status': str(e)})
        return {'status': f"An error occurred during the test: {e}"}
        