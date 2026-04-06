"""
UC-01 v2: Template-Driven DOCX Workpaper Exporter

Reads templates/workpaper_template.docx, matches cells by label text
in column 0, and fills column 1 with workpaper data.
Preserves all original formatting, shading, and structure.

To update the template: just replace templates/workpaper_template.docx.
No code changes needed unless new fields are added.

Author: Ananya Aithal
"""

import os
import copy
from docx import Document
from docx.shared import Pt, RGBColor
from io import BytesIO
from datetime import datetime

from models import ControlWorkpaper, ControlEffectiveness, TestingPhase


TEMPLATE_PATH = os.path.join(os.path.dirname(__file__), "templates", "workpaper_template.docx")


# ─────────────────────────────────────────────
# Core: Fill a cell's value while keeping format
# ─────────────────────────────────────────────

def _set_cell_value(cell, value: str):
    """
    Clear the value cell and write new content,
    preserving the formatting of the first existing run.
    Handles multiline values by adding new paragraphs.
    """
    if not value:
        return

    # Capture formatting from first existing run (if any)
    ref_run = None
    for p in cell.paragraphs:
        for r in p.runs:
            ref_run = r
            break
        if ref_run:
            break

    # Clear all paragraphs except the first
    for p in cell.paragraphs[1:]:
        p_elem = p._element
        p_elem.getparent().remove(p_elem)

    # Clear the first paragraph
    first_para = cell.paragraphs[0]
    first_para.clear()

    # Write new content
    lines = value.split("\n")
    for i, line in enumerate(lines):
        if i == 0:
            run = first_para.add_run(line)
        else:
            new_para = cell.add_paragraph()
            run = new_para.add_run(line)

        # Copy formatting from reference run
        if ref_run:
            run.font.size = ref_run.font.size
            run.font.name = ref_run.font.name
            if ref_run.font.color and ref_run.font.color.rgb:
                run.font.color.rgb = ref_run.font.color.rgb
        else:
            run.font.size = Pt(8)


def _find_and_fill(table, label: str, value: str):
    """
    Find a row by its label text (column 0) and fill column 1.
    Matches by checking if the label starts with the search text
    (handles trailing whitespace/colons in the template).
    """
    label_clean = label.strip().lower().rstrip(":")
    for row in table.rows:
        cell_text = row.cells[0].text.strip().lower().rstrip(":")
        if cell_text == label_clean:
            _set_cell_value(row.cells[1], value)
            return True
    return False


# ─────────────────────────────────────────────
# Build value mappings from workpaper data
# ─────────────────────────────────────────────

def _build_core_details_map(wp: ControlWorkpaper) -> dict:
    rcm = wp.rcm[0] if wp.rcm else None
    has_cde = wp.cde_result is not None
    has_coe = wp.coe_result is not None
    has_da = wp.da_result is not None

    return {
        "Country": "Group-wide",
        "Legal Entity": "Standard Chartered Bank",
        "Risk Radar Themes": rcm.risk_category if rcm else "",
        "Assigned Team Member (CDE)": "Audit Team",
        "Assigned Team Member (COE)": "Audit Team",
        "Assigned Team Member (Substantive Testing)": "N/A",
        "Process": rcm.risk_category if rcm else "",
        "Key Risk": rcm.risk_description if rcm else "",
        "Reference Number (Key Control)": rcm.control_id if rcm else "",
        "Title (Key Control)": wp.control_name,
        "Due Date (Key Control)": datetime.now().strftime("%d %B %Y"),
        "Key Control Description": rcm.control_description if rcm else "",
        "CDE Required": "Yes" if has_cde or wp.transcripts else "No",
        "Data Analytics (CDE)": "Yes" if has_da else "No",
        "Rationale for Skipping (CDE)": "N/A" if (has_cde or wp.transcripts) else "CDE not yet performed",
        "COE Required": "Yes" if has_coe else "No",
        "Data Analytics (COE)": "Yes" if has_da else "No",
        "Rationale for Skipping (COE)": "N/A" if has_coe else "COE not yet performed",
        "Substantive Test": "No",
        "Rationale for Skipping (Substantive Test)":
            "This is a controls testing and not a transactional testing, hence, substantive testing is not required.",
        "Data Analytics (Substantive Test)": "No",
    }


def _build_cde_map(wp: ControlWorkpaper) -> dict:
    rcm = wp.rcm[0] if wp.rcm else None
    cde = wp.cde_result
    has_da = wp.da_result is not None
    wt_ts = [t for t in wp.transcripts if t.phase == TestingPhase.WALKTHROUGH]
    cde_ts = [t for t in wp.transcripts if t.phase == TestingPhase.CDE]

    # ── CDE Testing Outcome: Process Walkthrough populates immediately ──
    outcome_parts = ["CDE Source Data:"]

    if wt_ts:
        outcome_parts.append("Process Walkthrough:")
        outcome_parts.append("Discussion and walkthrough with the following stakeholders:")
        if rcm and rcm.control_owner:
            outcome_parts.append(f"- {rcm.control_owner} (Control Owner)")
        outcome_parts.append("")
        outcome_parts.append("Walkthrough transcripts reviewed:")
        for t in wt_ts:
            date_str = t.uploaded_at.strftime("%d %b %Y")
            outcome_parts.append(f"- {t.filename} ({date_str})")
        outcome_parts.append("")
        for t in wt_ts:
            if t.summary:
                outcome_parts.append(f"Summary ({t.filename}):")
                outcome_parts.append(t.summary)
                outcome_parts.append("")

    if cde_ts:
        outcome_parts.append("CDE Discussion transcripts:")
        for t in cde_ts:
            outcome_parts.append(f"- {t.filename} ({t.uploaded_at.strftime('%d %b %Y')})")
        outcome_parts.append("")

    all_ts = wt_ts + cde_ts
    if all_ts:
        outcome_parts.append("Documents reviewed:")
        for i, t in enumerate(all_ts):
            ref = f"{rcm.control_id}_" if rcm and rcm.control_id else ""
            outcome_parts.append(f"{ref}WT{i+1}_{t.filename}")
        outcome_parts.append("")

    if cde:
        outcome_parts.append("CDE Assessment:")
        if cde.design_strengths:
            outcome_parts.append("Design Strengths:")
            for s in cde.design_strengths:
                outcome_parts.append(f"- {s}")
            outcome_parts.append("")
        if cde.design_gaps:
            outcome_parts.append("Design Gaps Identified:")
            for g in cde.design_gaps:
                outcome_parts.append(f"- {g}")
            outcome_parts.append("")
        if cde.compensating_controls:
            outcome_parts.append("Compensating Controls:")
            for c in cde.compensating_controls:
                outcome_parts.append(f"- {c}")
            outcome_parts.append("")
        outcome_parts.append(f"Assessment: {cde.design_assessment}")

    cde_outcome = "\n".join(outcome_parts) if len(outcome_parts) > 1 else ""

    # ── CDE Procedures ──
    cde_procedures = ""
    if wt_ts or cde:
        cde_procedures = (
            "Reviewed control design documentation and conducted walkthrough with control owner "
            "to understand the design and operating procedures of the control. Assessed whether "
            "the control is appropriately designed to mitigate the identified risks."
        )

    # ── Control attributes ──
    proc_or_mon = "Monitoring"
    if rcm and "Preventive" in (rcm.control_type or ""):
        proc_or_mon = "Processing"

    manual_auto = "Manual"
    if rcm and rcm.control_nature:
        if "Automated" in rcm.control_nature:
            manual_auto = "Automated"
        elif "IT-Dependent" in rcm.control_nature:
            manual_auto = "IT-Dependent Manual"

    # ── CDE Conclusion ──
    cde_conclusion = "Not Assessed"
    if cde:
        if "Well" in cde.design_assessment:
            cde_conclusion = "Effective"
        elif "Needs" in cde.design_assessment:
            cde_conclusion = "Partially Effective"
        elif "Poorly" in cde.design_assessment:
            cde_conclusion = "Ineffective"

    return {
        "Control Design Description": rcm.control_description if rcm else "",
        "Control Objective": rcm.control_objective if rcm else "",
        "Control Frequency": rcm.control_frequency if rcm else "",
        "Applications Covered": rcm.systems_applications if rcm else "N/A",
        "CDE Testing Procedures": cde_procedures,
        "CDE Testing Outcome (Results)": cde_outcome,
        "Processing or Monitoring Control?": proc_or_mon,
        "Manual or Automated Control?": manual_auto,
        "Nature of Control": rcm.control_type if rcm else "",
        "Complexity": "Moderate",
        "Testing completed by": "Audit Team",
        "Source Systems": rcm.systems_applications if rcm else "N/A",
        "Other Data Sources / Systems": "Yes" if has_da else "No",
        "Other Data Sources / Systems Description":
            ", ".join(wp.da_result.data_sources) if has_da and wp.da_result and wp.da_result.data_sources else "N/A",
        "Did analytics influence control outcome?": "Yes" if has_da else "No",
        "Analytics CT (control testing) coverage": "Full population" if has_da else "N/A",
        "Total Record Count":
            wp.da_result.population_size if has_da and wp.da_result and wp.da_result.population_size else "N/A",
        "Analytics Procedure Description":
            wp.da_result.analytics_performed if has_da and wp.da_result and wp.da_result.analytics_performed else "N/A",
        "CDE Conclusion:": cde_conclusion,
        "Comments/Rationale": cde.conclusion if cde else "",
    }


def _build_coe_map(wp: ControlWorkpaper) -> dict:
    coe = wp.coe_result
    rcm = wp.rcm[0] if wp.rcm else None
    has_da = wp.da_result is not None

    # ── COE Procedures ──
    coe_procedures = ""
    if coe:
        coe_procedures = (
            "Select a representative sample within the audit period as per GIA methodology "
            "and assess for appropriateness as per CDE."
            f"\n\nTesting Procedure: {coe.testing_procedure}"
        )
        coe_ts = [t for t in wp.transcripts if t.phase == TestingPhase.COE]
        if coe_ts:
            coe_procedures += "\n\nDocuments reviewed:"
            for t in coe_ts:
                coe_procedures += f"\n{t.filename}"

    # ── COE Outcome ──
    coe_outcome = ""
    if coe:
        parts = ["COE Test Step\n", coe.results_summary]
        if coe.deviation_details:
            parts.append("\nDeviations noted:")
            for d in coe.deviation_details:
                parts.append(f"- {d}")
        coe_outcome = "\n".join(parts)

    # ── Sample dates ──
    sample_start, sample_end = "", ""
    if coe and coe.sample_period:
        for sep in [" - ", " to ", " – "]:
            if sep in coe.sample_period:
                sample_start, sample_end = coe.sample_period.split(sep, 1)
                break
        else:
            sample_start = coe.sample_period

    # ── COE Conclusion ──
    coe_conclusion = "Not Assessed"
    if wp.effectiveness != ControlEffectiveness.NOT_ASSESSED:
        coe_conclusion = wp.effectiveness.value
    elif coe:
        if coe.deviations_found == 0:
            coe_conclusion = "Effective"
        elif coe.deviations_found <= 2:
            coe_conclusion = "Partially Effective"
        else:
            coe_conclusion = "Ineffective"

    # ── Comments with exceptions ──
    comments = coe.conclusion if coe else ""
    if wp.exceptions:
        comments += "\n\nExceptions identified:"
        for i, exc in enumerate(wp.exceptions):
            comments += f"\n{i+1}. [{exc.severity.value}] {exc.description}"

    return {
        "COE Testing Procedures": coe_procedures,
        "COE Testing Outcome (Results)": coe_outcome,
        "Population Title": f"{wp.control_name} — Operating Evidence" if coe else "",
        "Population Description":
            f"Population of {rcm.control_frequency.lower() if rcm else ''} control execution records "
            f"for {wp.control_name} during the audit period." if coe else "",
        "Number of Items": coe.sample_size if coe else "",
        "Source": rcm.systems_applications if rcm else "",
        "Relevance and Reliability":
            "Data obtained directly from production systems and verified against control documentation." if coe else "",
        "Stratification of Population":
            "Stratified by time period and database platform to ensure representative coverage." if coe else "",
        "Stratification Rationale":
            "To ensure coverage across different database platforms and time periods within the audit scope." if coe else "",
        "Sample Size": coe.sample_size if coe else "",
        "Sample Approach": "Representative sampling per GIA methodology" if coe else "",
        "Sample Start Date": sample_start,
        "Sample End Date": sample_end,
        "Complexity": "Moderate" if coe else "",
        "Testing completed by": "Audit Team" if coe else "",
        "Source Systems": rcm.systems_applications if rcm else "",
        "Other Data Sources / Systems": "Yes" if has_da else "No",
        "Other Data Sources / Systems Description":
            ", ".join(wp.da_result.data_sources) if has_da and wp.da_result and wp.da_result.data_sources else "N/A",
        "Did analytics influence control outcome?": "Yes" if has_da else "No",
        "Analytics CT (control testing) coverage": "Full population" if has_da else "N/A",
        "Total Record Count":
            wp.da_result.population_size if has_da and wp.da_result and wp.da_result.population_size else "N/A",
        "Analytics Procedure Description":
            wp.da_result.analytics_performed if has_da and wp.da_result and wp.da_result.analytics_performed else "N/A",
        "COE Conclusion:": coe_conclusion,
        "Comments/Rationale": comments,
    }


# ─────────────────────────────────────────────
# Main Export Function
# ─────────────────────────────────────────────

def export_workpaper(workpaper: ControlWorkpaper, template_path: str = None) -> BytesIO:
    """
    Clone the template .docx and fill it with workpaper data.
    Matches cells by label text — no hardcoded row indices.
    """
    path = template_path or TEMPLATE_PATH
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"Template not found at {path}. "
            f"Place your workpaper template at templates/workpaper_template.docx"
        )

    doc = Document(path)

    if len(doc.tables) < 3:
        raise ValueError(
            f"Template has {len(doc.tables)} tables, expected at least 3 "
            f"(Core Details, CDE, COE)."
        )

    # Table 0: Core Details
    core_map = _build_core_details_map(workpaper)
    for label, value in core_map.items():
        _find_and_fill(doc.tables[0], label, value)

    # Table 1: CDE
    cde_map = _build_cde_map(workpaper)
    for label, value in cde_map.items():
        _find_and_fill(doc.tables[1], label, value)

    # Table 2: COE
    coe_map = _build_coe_map(workpaper)
    for label, value in coe_map.items():
        _find_and_fill(doc.tables[2], label, value)

    # Save to buffer
    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    return buffer