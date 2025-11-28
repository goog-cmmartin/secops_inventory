import os
from sqlalchemy import create_engine, Column, Integer, String, ForeignKey, Table, Text
from sqlalchemy.orm import relationship, sessionmaker
from sqlalchemy.ext.declarative import declarative_base

# --- Database Configuration ---
db_path = os.path.join(os.path.dirname(__file__), "gcp_inventory.db")
DATABASE_URL = f"sqlite:///{db_path}"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()



class Organization(Base):
    __tablename__ = 'organization'
    id = Column(String, primary_key=True)
    display_name = Column(String)
    folders = relationship("Folder", back_populates="organization")

class Folder(Base):
    __tablename__ = 'folder'
    id = Column(String, primary_key=True)
    display_name = Column(String)
    
    parent_folder_id = Column(String, ForeignKey('folder.id'))
    parent_folder = relationship("Folder", remote_side=[id], backref="sub_folders")
    
    organization_id = Column(String, ForeignKey('organization.id'))
    organization = relationship("Organization", back_populates="folders")
    
    projects = relationship("Project", back_populates="folder")

class Project(Base):
    __tablename__ = 'project'
    id = Column(String, primary_key=True)
    display_name = Column(String)
    discovery_method = Column(String, nullable=True) # e.g., "AUTOMATIC", "MANUAL"
    
    folder_id = Column(String, ForeignKey('folder.id'))
    folder = relationship("Folder", back_populates="projects")
    
    secops_config = relationship("SecopsTenantConfig", back_populates="project", uselist=False)

class SecopsTenantConfig(Base):
    __tablename__ = 'secops_tenant_config'
    id = Column(Integer, primary_key=True)
    name = Column(String)
    secops_customer_id = Column(String)
    secops_region = Column(String)
    soar_url = Column(String)
    soar_api_key = Column(String) 
    bindplane_url = Column(String, nullable=True)
    bindplane_api_key = Column(String, nullable=True)

    project_id = Column(String, ForeignKey('project.id'))
    project = relationship("Project", back_populates="secops_config")

class Audit(Base):
    __tablename__ = 'audit'
    id = Column(Integer, primary_key=True)
    audit_category = Column(String, nullable=False)
    audit_name = Column(String, nullable=False)
    run_timestamp = Column(String, nullable=False)
    status = Column(String, nullable=False) # e.g., "Success", "Failed"
    results = Column(String) # Storing the full JSON response as a string

    tenant_project_id = Column(String, ForeignKey('project.id'))
    project = relationship("Project")

class AuditPrompt(Base):
    __tablename__ = 'audit_prompt'
    id = Column(Integer, primary_key=True)
    audit_name = Column(String, unique=True, nullable=False)
    prompt_text = Column(String)
    excluded_fields = Column(String) # Comma-separated list of fields to exclude

class Report(Base):
    __tablename__ = 'report'
    id = Column(Integer, primary_key=True)
    tenant_project_id = Column(String, ForeignKey('project.id'))
    report_name = Column(String, nullable=False)
    generation_timestamp = Column(String, nullable=False)
    report_content = Column(String) # Storing the HTML report content
    status = Column(String, nullable=True) # e.g., "Completed", "Failed"

    project = relationship("Project")

class Insight(Base):
    __tablename__ = 'insight'
    id = Column(Integer, primary_key=True)
    title = Column(String, nullable=False, unique=True)
    prompt = Column(String, nullable=False)
    excluded_fields = Column(String, nullable=True)
    audit_sources = Column(String, nullable=False) # Comma-separated list of audit source names

class CustomYL2Query(Base):
    __tablename__ = 'custom_yl2_queries'
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False)
    category = Column(String, nullable=False)
    yl2_query = Column(String, nullable=False)
    time_unit = Column(String, nullable=False, default='DAY')
    time_value = Column(Integer, nullable=False, default=30)

class AuditType(Base):
    __tablename__ = 'audit_type'
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False)
    description = Column(Text, nullable=True)
    icon = Column(String, nullable=True)
    auth_method = Column(String, nullable=False, default='GCP') # e.g., GCP, SOAR_API_KEY, BINDPLANE_API_KEY
    
    # Relationship to ConfigurableAudit
    configurable_audits = relationship("ConfigurableAudit", back_populates="audit_type")

class ConfigurableAudit(Base):
    __tablename__ = 'configurable_audit'
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False)
    category = Column(String, nullable=False)
    api_path = Column(String, nullable=True)
    method = Column(String, nullable=True)
    response_key = Column(String, nullable=True)
    default_page_size = Column(Integer, nullable=True)
    default_page_size = Column(Integer)
    audit_type_id = Column(Integer, ForeignKey('audit_type.id'), nullable=False)
    audit_type = relationship("AuditType")
    response_format = Column(String, default='JSON')
    pagination_token_key = Column(String, nullable=True)
    pagination_results_key = Column(String, nullable=True)
    pagination_request_token_key = Column(String, nullable=True)
    max_pages = Column(Integer, nullable=True)
    
    audit_type_id = Column(Integer, ForeignKey('audit_type.id'))
    audit_type = relationship("AuditType", back_populates="configurable_audits")
    schedules_to_run = relationship("Schedule", secondary="scheduled_audits", back_populates="audits_to_run")
    schedules_for_report = relationship("Schedule", secondary="scheduled_reports_audits", back_populates="audits_for_report")
    schedules_for_diff = relationship("Schedule", secondary="scheduled_diffs_audits", back_populates="audits_for_diff")

# --- Many-to-many association table for Schedules and Audits (for running audits) ---
scheduled_audits = Table('scheduled_audits', Base.metadata,
    Column('schedule_id', Integer, ForeignKey('schedule.id'), primary_key=True),
    Column('configurable_audit_id', Integer, ForeignKey('configurable_audit.id'), primary_key=True)
)

# --- Many-to-many association table for Schedules and Audits (for generating reports) ---
scheduled_reports_audits = Table('scheduled_reports_audits', Base.metadata,
    Column('schedule_id', Integer, ForeignKey('schedule.id'), primary_key=True),
    Column('configurable_audit_id', Integer, ForeignKey('configurable_audit.id'), primary_key=True)
)

# --- Many-to-many association table for Schedules and Audits (for generating diffs) ---
scheduled_diffs_audits = Table('scheduled_diffs_audits', Base.metadata,
    Column('schedule_id', Integer, ForeignKey('schedule.id'), primary_key=True),
    Column('configurable_audit_id', Integer, ForeignKey('configurable_audit.id'), primary_key=True)
)

class Schedule(Base):
    __tablename__ = 'schedule'
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    tenant_project_id = Column(String, ForeignKey('project.id'), nullable=False)
    cron_schedule = Column(String, nullable=False) # e.g., "0 1 * * *"
    is_enabled = Column(Integer, nullable=False, default=1) # Using Integer for broader compatibility (1=True, 0=False)
    last_run_at = Column(String, nullable=True)
    schedule_type = Column(String, nullable=False, default='audit') # 'audit', 'report', or 'diff'
    report_name_format = Column(String, nullable=True) # e.g., "Weekly Security Report - {date}"

    project = relationship("Project")
    audits_to_run = relationship("ConfigurableAudit", secondary="scheduled_audits")
    audits_for_report = relationship("ConfigurableAudit", secondary="scheduled_reports_audits")
    audits_for_diff = relationship("ConfigurableAudit", secondary="scheduled_diffs_audits")


def create_db_session():
    """Creates a new database session."""
    return SessionLocal()

def init_db():
    """Initializes the database, creating tables if they don't exist."""
    # This will create tables for all models that inherit from Base
    Base.metadata.create_all(bind=engine)


if __name__ == '__main__':
    # This will create the database and tables when the script is run directly
    print("Creating database and tables...")
    init_db()
    print("Database and tables created successfully.")
