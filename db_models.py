"""
UC-01 v2: Database Models (SQLAlchemy)
Persistent storage with pluggable backend (SQLite / PostgreSQL / Azure SQL).

Author: Ananya Aithal
"""

import os
import json
from datetime import datetime
from typing import Optional
from sqlalchemy import (
    create_engine, Column, Integer, String, Text, DateTime,
    Float, Boolean, ForeignKey, Enum as SAEnum
)
from sqlalchemy.orm import (
    declarative_base, relationship, sessionmaker, Session
)
from enum import Enum

from dotenv import load_dotenv
load_dotenv()

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///uc01.db")

# Handle SQLite-specific args
connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_engine(DATABASE_URL, connect_args=connect_args, echo=False)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
Base = declarative_base()


# ─────────────────────────────────────────────
# Enums
# ─────────────────────────────────────────────

class ControlEffectiveness(str, Enum):
    NOT_ASSESSED = "Not Assessed"
    EFFECTIVE = "Effective"
    PARTIALLY_EFFECTIVE = "Partially Effective"
    INEFFECTIVE = "Ineffective"


class TestingPhase(str, Enum):
    WALKTHROUGH = "Control Walkthrough"
    CDE = "CDE Testing"
    COE = "COE Testing"
    DA = "Data Analytics"
    EXCEPTIONS = "Exception Reporting"


class ExceptionSeverity(str, Enum):
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"
    CRITICAL = "Critical"


class DocumentType(str, Enum):
    TRANSCRIPT = "Transcript"
    PROCESS_DOC = "Process Document"
    ACCESS_MATRIX = "Access Matrix"
    TECH_IMPL = "Technical Implementation"
    RISK_RATING = "Risk Rating"
    POLICY = "Policy / Standard"
    EVIDENCE = "Evidence / Screenshot"
    OTHER = "Other"


# ─────────────────────────────────────────────
# Tables
# ─────────────────────────────────────────────

class AuditProject(Base):
    __tablename__ = "audit_projects"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(500), nullable=False)
    created_at = Column(DateTime, default=datetime.now)

    workpapers = relationship("ControlWorkpaper", back_populates="project", cascade="all, delete-orphan")


class ControlWorkpaper(Base):
    __tablename__ = "control_workpapers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("audit_projects.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.now)
    last_updated = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    # ── Audit context ──
    control_name = Column(String(500), nullable=False)

    # ── RCM (stored as JSON — flexible for varying column counts) ──
    rcm_json = Column(Text, default="[]")

    # ── CDE result (JSON) ──
    cde_json = Column(Text, default=None, nullable=True)

    # ── COE result (JSON) ──
    coe_json = Column(Text, default=None, nullable=True)

    # ── DA result (JSON) ──
    da_json = Column(Text, default=None, nullable=True)

    # ── AI-suggested test procedures (JSON) ──
    suggested_tests_json = Column(Text, default=None, nullable=True)

    # ── Exceptions (JSON array) ──
    exceptions_json = Column(Text, default="[]")

    # ── Conclusion ──
    effectiveness = Column(String(50), default=ControlEffectiveness.NOT_ASSESSED.value)
    ai_conclusion_rationale = Column(Text, default="")
    auditor_override_rationale = Column(Text, default="")

    # ── Workflow tracking (JSON list of completed phase names) ──
    completed_phases_json = Column(Text, default="[]")

    # ── Relationships ──
    project = relationship("AuditProject", back_populates="workpapers")
    documents = relationship("WorkpaperDocument", back_populates="workpaper", cascade="all, delete-orphan")

    # ── Helpers ──
    @property
    def rcm(self) -> list[dict]:
        return json.loads(self.rcm_json) if self.rcm_json else []

    @rcm.setter
    def rcm(self, value: list[dict]):
        self.rcm_json = json.dumps(value, default=str)

    @property
    def cde_result(self) -> Optional[dict]:
        return json.loads(self.cde_json) if self.cde_json else None

    @cde_result.setter
    def cde_result(self, value: Optional[dict]):
        self.cde_json = json.dumps(value, default=str) if value else None

    @property
    def coe_result(self) -> Optional[dict]:
        return json.loads(self.coe_json) if self.coe_json else None

    @coe_result.setter
    def coe_result(self, value: Optional[dict]):
        self.coe_json = json.dumps(value, default=str) if value else None

    @property
    def da_result(self) -> Optional[dict]:
        return json.loads(self.da_json) if self.da_json else None

    @da_result.setter
    def da_result(self, value: Optional[dict]):
        self.da_json = json.dumps(value, default=str) if value else None

    @property
    def suggested_tests(self) -> Optional[dict]:
        return json.loads(self.suggested_tests_json) if self.suggested_tests_json else None

    @suggested_tests.setter
    def suggested_tests(self, value: Optional[dict]):
        self.suggested_tests_json = json.dumps(value, default=str) if value else None

    @property
    def exceptions(self) -> list[dict]:
        return json.loads(self.exceptions_json) if self.exceptions_json else []

    @exceptions.setter
    def exceptions(self, value: list[dict]):
        self.exceptions_json = json.dumps(value, default=str)

    @property
    def completed_phases(self) -> list[str]:
        return json.loads(self.completed_phases_json) if self.completed_phases_json else []

    @completed_phases.setter
    def completed_phases(self, value: list[str]):
        self.completed_phases_json = json.dumps(value)

    def mark_phase_complete(self, phase: str):
        phases = self.completed_phases
        if phase not in phases:
            phases.append(phase)
            self.completed_phases = phases
        self.last_updated = datetime.now()

    def progress_pct(self) -> int:
        return int((len(self.completed_phases) / 5) * 100)

    def get_transcripts(self, phase: str = None) -> list["WorkpaperDocument"]:
        docs = [d for d in self.documents if d.doc_type == DocumentType.TRANSCRIPT.value]
        if phase:
            docs = [d for d in docs if d.phase == phase]
        return docs

    def get_supporting_docs(self) -> list["WorkpaperDocument"]:
        return [d for d in self.documents if d.doc_type != DocumentType.TRANSCRIPT.value]


class WorkpaperDocument(Base):
    """
    Any uploaded file — transcript, process doc, access matrix, etc.
    Content stored as text (for transcripts) or filepath (for binaries).
    """
    __tablename__ = "workpaper_documents"

    id = Column(Integer, primary_key=True, autoincrement=True)
    workpaper_id = Column(Integer, ForeignKey("control_workpapers.id"), nullable=False)
    uploaded_at = Column(DateTime, default=datetime.now)

    filename = Column(String(500), nullable=False)
    doc_type = Column(String(100), default=DocumentType.TRANSCRIPT.value)
    phase = Column(String(100), default=TestingPhase.WALKTHROUGH.value)

    # Text content (for transcripts, extracted text from docs)
    content = Column(Text, default="")

    # File path on disk / blob storage (for original binary files)
    file_path = Column(String(1000), default="")

    # AI-generated summary
    summary = Column(Text, default="")

    workpaper = relationship("ControlWorkpaper", back_populates="documents")


# ─────────────────────────────────────────────
# Database initialization
# ─────────────────────────────────────────────

def init_db():
    """Create all tables."""
    Base.metadata.create_all(bind=engine)


def get_db() -> Session:
    """Get a database session."""
    return SessionLocal()
