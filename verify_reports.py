import os
from database_setup import create_db_session, Report

def verify_reports():
    """
    Connects to the database and prints all reports found in the 'report' table.
    """
    db_path = 'gcp_inventory.db'
    if not os.path.exists(db_path):
        print(f"Database file '{db_path}' not found.")
        return

    print(f"Connecting to '{db_path}'...")
    db_session = create_db_session(db_name=db_path)
    try:
        print("Querying for all reports...")
        reports = db_session.query(Report).all()

        if not reports:
            print("No reports found in the database.")
        else:
            print(f"Found {len(reports)} report(s):")
            print("-" * 30)
            for report in reports:
                print(f"  ID: {report.id}")
                print(f"  Project ID: {report.tenant_project_id}")
                print(f"  Report Name: {report.report_name}")
                print(f"  Generated On: {report.generation_timestamp}")
                # Print a small snippet of the content
                content_snippet = report.report_content[:100].replace('\n', ' ') + "..."
                print(f"  Content Snippet: {content_snippet}")
                print("-" * 30)
    finally:
        db_session.close()
        print("Database connection closed.")

if __name__ == "__main__":
    verify_reports()
