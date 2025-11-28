
import os
from sqlalchemy import create_engine, Column, Integer, String, Text, Table, ForeignKey
from sqlalchemy.orm import sessionmaker, declarative_base, relationship

# --- Database Configuration ---
db_path = os.path.join(os.path.dirname(__file__), "gcp_inventory.db")
DATABASE_URL = f"sqlite:///{db_path}"

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# --- Model Definitions ---
# Define only the models needed for this script to avoid dependency issues.

insight_audit_association = Table('insight_audit_association', Base.metadata,
    Column('insight_id', Integer, ForeignKey('insights.id'), primary_key=True),
    Column('audit_prompt_id', Integer, ForeignKey('audit_prompts.id'), primary_key=True)
)

class AuditPrompt(Base):
    __tablename__ = 'audit_prompts'
    id = Column(Integer, primary_key=True)
    audit_name = Column(String, unique=True, nullable=False)
    insights = relationship("Insight", secondary=insight_audit_association, back_populates="audits")

class Insight(Base):
    __tablename__ = 'insights'
    id = Column(Integer, primary_key=True)
    title = Column(String, unique=True, nullable=False)
    prompt = Column(Text, nullable=False)
    audits = relationship("AuditPrompt", secondary=insight_audit_association, back_populates="insights")


def check_insights():
    """Connects to the database and prints the contents of the insights table."""
    db = SessionLocal()
    try:
        insights = db.query(Insight).all()
        
        if not insights:
            print("The 'insights' table is empty.")
        else:
            print(f"Found {len(insights)} insight(s):")
            for insight in insights:
                print(f"  - ID: {insight.id}, Title: {insight.title}")
                # Eagerly load the related audits to check the relationship
                audit_names = [audit.audit_name for audit in insight.audits]
                print(f"    - Associated Audits: {', '.join(audit_names) if audit_names else 'None'}")

    except Exception as e:
        print(f"An error occurred during the query: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    check_insights()
