
import argparse
from database_setup import create_db_session, Project, SecopsTenantConfig

def add_configuration(session, project_id, name, customer_id, region, soar_url, soar_api_key):
    """Adds or updates a SecOps configuration for a given project."""
    project = session.query(Project).filter_by(id=project_id).first()
    if not project:
        print(f"Error: Project with ID '{project_id}' not found in the inventory.")
        return

    config = session.query(SecopsTenantConfig).filter_by(project_id=project_id).first()
    if config:
        # Update existing configuration
        config.name = name
        config.secops_customer_id = customer_id
        config.secops_region = region
        config.soar_url = soar_url
        config.soar_api_key = soar_api_key
        print(f"Successfully updated configuration for project: {project.display_name}")
    else:
        # Add new configuration
        new_config = SecopsTenantConfig(
            name=name,
            secops_customer_id=customer_id,
            secops_region=region,
            soar_url=soar_url,
            soar_api_key=soar_api_key,
            project=project
        )
        session.add(new_config)
        print(f"Successfully added new configuration for project: {project.display_name}")
    
    session.commit()

def view_configuration(session, project_id):
    """Views the SecOps configuration for a given project."""
    project = session.query(Project).filter_by(id=project_id).first()
    if not project:
        print(f"Error: Project with ID '{project_id}' not found in the inventory.")
        return

    config = project.secops_config
    if config:
        print(f"\n--- Configuration for Project: {project.display_name} (ID: {project.id}) ---")
        print(f"  Name: {config.name}")
        print(f"  SecOps Customer ID: {config.secops_customer_id}")
        print(f"  SecOps Region: {config.secops_region}")
        print(f"  SOAR URL: {config.soar_url}")
        # Note: Be cautious about displaying sensitive info like API keys
        print(f"  SOAR API Key: {'*' * len(config.soar_api_key) if config.soar_api_key else 'Not Set'}")
    else:
        print(f"No configuration found for project: {project.display_name}")

def main():
    parser = argparse.ArgumentParser(description="Manage SecOps Tenant Configurations.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Add command
    add_parser = subparsers.add_parser("add", help="Add or update a configuration.")
    add_parser.add_argument("--project-id", required=True, help="GCP Project ID.")
    add_parser.add_argument("--name", required=True, help="Configuration name.")
    add_parser.add_argument("--customer-id", required=True, help="SecOps Customer ID.")
    add_parser.add_argument("--region", required=True, help="SecOps Region.")
    add_parser.add_argument("--soar-url", required=True, help="SOAR URL.")
    add_parser.add_argument("--soar-api-key", required=True, help="SOAR API Key.")

    # View command
    view_parser = subparsers.add_parser("view", help="View a configuration.")
    view_parser.add_argument("--project-id", required=True, help="GCP Project ID.")

    args = parser.parse_args()
    session = create_db_session()

    try:
        if args.command == "add":
            add_configuration(
                session, args.project_id, args.name, args.customer_id, 
                args.region, args.soar_url, args.soar_api_key
            )
        elif args.command == "view":
            view_configuration(session, args.project_id)
    finally:
        session.close()

if __name__ == "__main__":
    main()
