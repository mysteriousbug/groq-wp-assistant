"""
UC-01 v2: Agentic AI Audit Workpaper Assistant
Data Models — Multi-Control, Non-Linear Workflow

Author: Ananya Aithal
"""

from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum
from datetime import datetime
import uuid


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


# ─────────────────────────────────────────────
# Transcript & Walkthrough
# ─────────────────────────────────────────────

class Transcript(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    filename: str
    content: str
    uploaded_at: datetime = Field(default_factory=datetime.now)
    phase: TestingPhase = TestingPhase.WALKTHROUGH
    summary: Optional[str] = None  # AI-generated summary


class WalkthroughExtraction(BaseModel):
    """AI-extracted data from a control walkthrough transcript."""
    control_objective: str = ""
    control_description: str = ""
    control_owner: str = ""
    control_frequency: str = ""  # e.g., Daily, Weekly, Monthly, Ad-hoc
    control_type: str = ""  # Preventive, Detective, Corrective
    control_nature: str = ""  # Manual, Automated, IT-Dependent Manual
    risk_description: str = ""
    risk_category: str = ""  # e.g., Operational, Financial, Compliance
    key_mitigating_activities: list[str] = []
    systems_applications: list[str] = []  # Systems involved
    evidence_expected: list[str] = []  # What evidence to request
    walkthrough_notes: str = ""
    confidence_score: float = 0.0  # 0-1, how confident the AI is


# ─────────────────────────────────────────────
# RCM (Risk Control Matrix)
# ─────────────────────────────────────────────

class RCMRow(BaseModel):
    risk_id: str = ""
    risk_description: str = ""
    risk_category: str = ""
    control_id: str = ""
    control_objective: str = ""
    control_description: str = ""
    control_owner: str = ""
    control_frequency: str = ""
    control_type: str = ""
    control_nature: str = ""
    key_mitigating_activities: str = ""
    systems_applications: str = ""
    testing_approach: str = ""  # CDE, COE, DA, or combination
    evidence_required: str = ""


# ─────────────────────────────────────────────
# Testing Results
# ─────────────────────────────────────────────

class CDEResult(BaseModel):
    """Control Design Evaluation result."""
    design_assessment: str = ""  # Well designed / Needs improvement / Poorly designed
    design_gaps: list[str] = []
    design_strengths: list[str] = []
    compensating_controls: list[str] = []
    conclusion: str = ""
    ai_generated: bool = True
    manually_edited: bool = False


class COEResult(BaseModel):
    """Control Operating Effectiveness result."""
    sample_size: str = ""
    sample_period: str = ""
    testing_procedure: str = ""
    results_summary: str = ""
    deviations_found: int = 0
    deviation_details: list[str] = []
    conclusion: str = ""
    ai_generated: bool = True
    manually_edited: bool = False


class DAResult(BaseModel):
    """Data Analytics result."""
    data_sources: list[str] = []
    analytics_performed: str = ""
    population_size: str = ""
    exceptions_identified: int = 0
    exception_details: list[str] = []
    visualizations_notes: str = ""
    conclusion: str = ""
    ai_generated: bool = True
    manually_edited: bool = False


class ExceptionRecord(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    source_phase: TestingPhase = TestingPhase.CDE
    description: str = ""
    severity: ExceptionSeverity = ExceptionSeverity.MEDIUM
    root_cause: str = ""
    management_response: str = ""
    remediation_plan: str = ""
    target_date: str = ""
    ai_generated: bool = True


# ─────────────────────────────────────────────
# Control Workpaper (the main entity)
# ─────────────────────────────────────────────

class ControlWorkpaper(BaseModel):
    """
    One workpaper per control. This is the central object that
    accumulates data as the auditor moves through phases
    in any order (principle-based methodology).
    """
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    created_at: datetime = Field(default_factory=datetime.now)
    last_updated: datetime = Field(default_factory=datetime.now)

    # ── Audit context ──
    audit_name: str = ""  # e.g., "Database Services Audit"
    control_name: str = ""  # e.g., "Database Privileged Access Management"

    # ── Transcripts (multiple per control) ──
    transcripts: list[Transcript] = []

    # ── RCM (populated from walkthrough transcripts) ──
    rcm: list[RCMRow] = []

    # ── Testing results (filled in any order) ──
    cde_result: Optional[CDEResult] = None
    coe_result: Optional[COEResult] = None
    da_result: Optional[DAResult] = None

    # ── Exceptions ──
    exceptions: list[ExceptionRecord] = []

    # ── AI Conclusion ──
    effectiveness: ControlEffectiveness = ControlEffectiveness.NOT_ASSESSED
    ai_conclusion_rationale: str = ""
    auditor_override_rationale: str = ""  # If auditor disagrees with AI

    # ── Workflow tracking ──
    completed_phases: list[TestingPhase] = []

    def mark_phase_complete(self, phase: TestingPhase):
        if phase not in self.completed_phases:
            self.completed_phases.append(phase)
        self.last_updated = datetime.now()

    def progress_pct(self) -> int:
        """5 possible phases, return % complete."""
        return int((len(self.completed_phases) / 5) * 100)


# ─────────────────────────────────────────────
# Audit Project (container for multiple controls)
# ─────────────────────────────────────────────

class AuditProject(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    name: str = ""  # e.g., "Database Services Audit Q2 2026"
    created_at: datetime = Field(default_factory=datetime.now)
    workpapers: list[ControlWorkpaper] = []

    def get_workpaper(self, control_name: str) -> Optional[ControlWorkpaper]:
        for wp in self.workpapers:
            if wp.control_name == control_name:
                return wp
        return None

    def add_workpaper(self, control_name: str) -> ControlWorkpaper:
        wp = ControlWorkpaper(
            audit_name=self.name,
            control_name=control_name
        )
        self.workpapers.append(wp)
        return wp
