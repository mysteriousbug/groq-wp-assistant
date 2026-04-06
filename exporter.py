"""
UC-01 v2: DOCX Workpaper Exporter
Matches SCB GIA Workpaper Template exactly:
  - Table 0: CORE DETAILS (22 rows)
  - Table 1: CDE (21 rows)
  - Table 2: COE (25 rows)

All tables: 2 columns, blue header (#0473EA), white text, 8pt body.

Author: Ananya Aithal
"""

from docx import Document
from docx.shared import Pt, RGBColor, Cm, Emu
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from io import BytesIO
from datetime import datetime

from models import ControlWorkpaper, ControlEffectiveness, TestingPhase


# ─────────────────────────────────────────────
# Styling Constants (from template analysis)
# ─────────────────────────────────────────────

HEADER_FILL = "0473EA"
HEADER_TEXT_COLOR = RGBColor(0xFF, 0xFF, 0xFF)
LABEL_FONT_SIZE = Pt(8)
VALUE_FONT_SIZE = Pt(8)
COL_WIDTH = 10530
TABLE_WIDTH = 21060
PAGE_WIDTH = 7560310
PAGE_HEIGHT = 10692130
MARGIN = 914400


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def _set_cell_shading(cell, color_hex: str):
    tc_pr = cell._element.get_or_add_tcPr()
    for existing in tc_pr.findall(qn('w:shd')):
        tc_pr.remove(existing)
    shading = tc_pr.makeelement(qn('w:shd'), {
        qn('w:fill'): color_hex,
        qn('w:val'): 'clear',
    })
    tc_pr.append(shading)


def _set_cell_width(cell, width_dxa: int):
    tc_pr = cell._element.get_or_add_tcPr()
    for existing in tc_pr.findall(qn('w:tcW')):
        tc_pr.remove(existing)
    tc_w = tc_pr.makeelement(qn('w:tcW'), {
        qn('w:w'): str(width_dxa),
        qn('w:type'): 'dxa',
    })
    tc_pr.append(tc_w)


def _add_header_row(table, row_idx, text: str):
    row = table.rows[row_idx]
    row.cells[0].merge(row.cells[1])
    cell = row.cells[0]
    _set_cell_shading(cell, HEADER_FILL)
    cell.paragraphs[0].clear()
    run = cell.paragraphs[0].add_run(text + "  ")
    run.bold = True
    run.font.size = LABEL_FONT_SIZE
    run.font.color.rgb = HEADER_TEXT_COLOR


def _add_label_value_row(table, row_idx, label: str, value: str = ""):
    row = table.rows[row_idx]
    label_cell = row.cells[0]
    _set_cell_width(label_cell, COL_WIDTH)
    label_cell.paragraphs[0].clear()
    run = label_cell.paragraphs[0].add_run(label)
    run.bold = True
    run.font.size = LABEL_FONT_SIZE

    value_cell = row.cells[1]
    _set_cell_width(value_cell, COL_WIDTH)
    value_cell.paragraphs[0].clear()
    if value:
        lines = value.split("\n")
        for i, line in enumerate(lines):
            if i == 0:
                run = value_cell.paragraphs[0].add_run(line)
                run.font.size = VALUE_FONT_SIZE
            else:
                p = value_cell.add_paragraph()
                run = p.add_run(line)
                run.font.size = VALUE_FONT_SIZE


def _build_table(doc, num_rows: int):
    table = doc.add_table(rows=num_rows, cols=2)
    table.style = 'Table Grid'
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    tbl = table._element
    tbl_pr = tbl.find(qn('w:tblPr'))
    if tbl_pr is None:
        tbl_pr = tbl.makeelement(qn('w:tblPr'), {})
        tbl.insert(0, tbl_pr)
    for existing in tbl_pr.findall(qn('w:tblW')):
        tbl_pr.remove(existing)
    tbl_w = tbl_pr.makeelement(qn('w:tblW'), {
        qn('w:w'): str(TABLE_WIDTH),
        qn('w:type'): 'dxa',
    })
    tbl_pr.append(tbl_w)
    return table


# ─────────────────────────────────────────────
# Table 0: CORE DETAILS
# ─────────────────────────────────────────────

def _build_core_details(doc, wp: ControlWorkpaper):
    table = _build_table(doc, 22)
    _add_header_row(table, 0, "CORE DETAILS")

    rcm = wp.rcm[0] if wp.rcm else None
    has_cde = wp.cde_result is not None
    has_coe = wp.coe_result is not None
    has_da = wp.da_result is not None

    rows = [
        ("Country", "Group-wide"),
        ("Legal Entity", "Standard Chartered Bank"),
        ("Risk Radar Themes", rcm.risk_category if rcm else ""),
        ("Assigned Team Member (CDE)", "Audit Team"),
        ("Assigned Team Member (COE)", "Audit Team"),
        ("Assigned Team Member (Substantive Testing)", "N/A"),
        ("Process", rcm.risk_category if rcm else ""),
        ("Key Risk", rcm.risk_description if rcm else ""),
        ("Reference Number (Key Control)", rcm.control_id if rcm else ""),
        ("Title (Key Control)", wp.control_name),
        ("Due Date (Key Control)", datetime.now().strftime("%d %B %Y")),
        ("Key Control Description", rcm.control_description if rcm else ""),
        ("CDE Required", "Yes" if has_cde else "No"),
        ("Data Analytics (CDE)", "Yes" if has_da else "No"),
        ("Rationale for Skipping (CDE)", "N/A" if has_cde else "CDE not yet performed"),
        ("COE Required", "Yes" if has_coe else "No"),
        ("Data Analytics (COE)", "Yes" if has_da else "No"),
        ("Rationale for Skipping (COE)", "N/A" if has_coe else "COE not yet performed"),
        ("Substantive Test", "No"),
        ("Rationale for Skipping (Substantive Test)",
         "This is a controls testing and not a transactional testing, hence, substantive testing is not required."),
        ("Data Analytics (Substantive Test)", "No"),
    ]
    for i, (label, value) in enumerate(rows):
        _add_label_value_row(table, i + 1, label, value)


# ─────────────────────────────────────────────
# Table 1: CDE
# ─────────────────────────────────────────────

def _build_cde_table(doc, wp: ControlWorkpaper):
    table = _build_table(doc, 21)
    _add_header_row(table, 0, "CDE")

    rcm = wp.rcm[0] if wp.rcm else None
    cde = wp.cde_result
    has_da = wp.da_result is not None

    # Build CDE testing outcome — walkthrough populates this IMMEDIATELY
    wt_ts = [t for t in wp.transcripts if t.phase == TestingPhase.WALKTHROUGH]
    cde_ts = [t for t in wp.transcripts if t.phase == TestingPhase.CDE]

    parts = ["CDE Source Data:"]

    # Process Walkthrough section — populated as soon as transcripts are uploaded
    if wt_ts:
        parts.append("Process Walkthrough:")
        parts.append(f"Discussion and walkthrough with the following stakeholders:")
        # Extract participant names from walkthrough extractions if available
        if rcm and rcm.control_owner:
            parts.append(f"- {rcm.control_owner} (Control Owner)")
        parts.append("")
        parts.append("Walkthrough transcripts reviewed:")
        for t in wt_ts:
            date_str = t.uploaded_at.strftime("%d %b %Y")
            parts.append(f"- {t.filename} ({date_str})")
        parts.append("")
        # Include walkthrough summaries if available
        for t in wt_ts:
            if t.summary:
                parts.append(f"Summary ({t.filename}):")
                parts.append(t.summary)
                parts.append("")

    if cde_ts:
        parts.append("CDE Discussion transcripts:")
        for t in cde_ts:
            date_str = t.uploaded_at.strftime("%d %b %Y")
            parts.append(f"- {t.filename} ({date_str})")
        parts.append("")

    # Documents reviewed section
    all_transcripts = wt_ts + cde_ts
    if all_transcripts:
        parts.append("Documents reviewed:")
        for i, t in enumerate(all_transcripts):
            ref_prefix = f"{rcm.control_id}_" if rcm and rcm.control_id else f"C{i+1}_"
            parts.append(f"{ref_prefix}WT{i+1}_{t.filename}")
        parts.append("")

    # CDE analysis results — added when CDE is run
    if cde:
        parts.append("CDE Assessment:")
        if cde.design_strengths:
            parts.append("Design Strengths:")
            for s in cde.design_strengths:
                parts.append(f"- {s}")
            parts.append("")
        if cde.design_gaps:
            parts.append("Design Gaps Identified:")
            for g in cde.design_gaps:
                parts.append(f"- {g}")
            parts.append("")
        if cde.compensating_controls:
            parts.append("Compensating Controls:")
            for c in cde.compensating_controls:
                parts.append(f"- {c}")
            parts.append("")
        parts.append(f"Assessment: {cde.design_assessment}")

    cde_outcome = "\n".join(parts) if len(parts) > 1 else ""

    # CDE procedures — always show if walkthrough exists
    cde_procedures = ""
    if wt_ts or cde:
        cde_procedures = (
            "Reviewed control design documentation and conducted walkthrough with control owner "
            "to understand the design and operating procedures of the control. Assessed whether "
            "the control is appropriately designed to mitigate the identified risks."
        )

    # Determine control attributes
    proc_or_mon = "Monitoring"
    if rcm and "Preventive" in (rcm.control_type or ""):
        proc_or_mon = "Processing"

    manual_auto = "Manual"
    if rcm and rcm.control_nature:
        if "Automated" in rcm.control_nature:
            manual_auto = "Automated"
        elif "IT-Dependent" in rcm.control_nature:
            manual_auto = "IT-Dependent Manual"

    cde_conclusion = "Not Assessed"
    if cde:
        if "Well" in cde.design_assessment:
            cde_conclusion = "Effective"
        elif "Needs" in cde.design_assessment:
            cde_conclusion = "Partially Effective"
        elif "Poorly" in cde.design_assessment:
            cde_conclusion = "Ineffective"

    rows = [
        ("Control Design Description", rcm.control_description if rcm else ""),
        ("Control Objective", rcm.control_objective if rcm else ""),
        ("Control Frequency", rcm.control_frequency if rcm else ""),
        ("Applications Covered", rcm.systems_applications if rcm else "N/A"),
        ("CDE Testing Procedures", cde_procedures),
        ("CDE Testing Outcome (Results)", cde_outcome),
        ("Processing or Monitoring Control?", proc_or_mon),
        ("Manual or Automated Control?", manual_auto),
        ("Nature of Control", rcm.control_type if rcm else ""),
        ("Complexity", "Moderate"),
        ("Testing completed by", "Audit Team"),
        ("Source Systems", rcm.systems_applications if rcm else "N/A"),
        ("Other Data Sources / Systems", "Yes" if has_da else "No"),
        ("Other Data Sources / Systems Description",
         ", ".join(wp.da_result.data_sources) if has_da and wp.da_result and wp.da_result.data_sources else "N/A"),
        ("Did analytics influence control outcome?", "Yes" if has_da else "No"),
        ("Analytics CT (control testing) coverage", "Full population" if has_da else "N/A"),
        ("Total Record Count",
         wp.da_result.population_size if has_da and wp.da_result and wp.da_result.population_size else "N/A"),
        ("Analytics Procedure Description",
         wp.da_result.analytics_performed if has_da and wp.da_result and wp.da_result.analytics_performed else "N/A"),
        ("CDE Conclusion:", cde_conclusion),
        ("Comments/Rationale", cde.conclusion if cde else ""),
    ]
    for i, (label, value) in enumerate(rows):
        _add_label_value_row(table, i + 1, label, value)


# ─────────────────────────────────────────────
# Table 2: COE
# ─────────────────────────────────────────────

def _build_coe_table(doc, wp: ControlWorkpaper):
    table = _build_table(doc, 25)
    _add_header_row(table, 0, "COE")

    coe = wp.coe_result
    rcm = wp.rcm[0] if wp.rcm else None
    has_da = wp.da_result is not None

    # COE procedures
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

    # COE outcome
    coe_outcome = ""
    if coe:
        parts = ["COE Test Step\n", coe.results_summary]
        if coe.deviation_details:
            parts.append("\nDeviations noted:")
            for d in coe.deviation_details:
                parts.append(f"- {d}")
        coe_outcome = "\n".join(parts)

    # Sample dates
    sample_start = ""
    sample_end = ""
    if coe and coe.sample_period:
        if " - " in coe.sample_period:
            sample_start, sample_end = coe.sample_period.split(" - ", 1)
        elif " to " in coe.sample_period.lower():
            parts = coe.sample_period.lower().split(" to ", 1)
            sample_start = parts[0].strip()
            sample_end = parts[1].strip()
        else:
            sample_start = coe.sample_period

    # COE conclusion
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

    # Comments with exceptions
    comments = coe.conclusion if coe else ""
    if wp.exceptions:
        comments += "\n\nExceptions identified:"
        for i, exc in enumerate(wp.exceptions):
            comments += f"\n{i+1}. [{exc.severity.value}] {exc.description}"

    rows = [
        ("COE Testing Procedures", coe_procedures),
        ("COE Testing Outcome (Results)", coe_outcome),
        ("Population Title", f"{wp.control_name} — Operating Evidence" if coe else ""),
        ("Population Description",
         f"Population of {rcm.control_frequency.lower() if rcm else ''} control execution records "
         f"for {wp.control_name} during the audit period." if coe else ""),
        ("Number of Items", coe.sample_size if coe else ""),
        ("Source", rcm.systems_applications if rcm else ""),
        ("Relevance and Reliability",
         "Data obtained directly from production systems and verified against control documentation." if coe else ""),
        ("Stratification of Population",
         "Stratified by time period and database platform to ensure representative coverage." if coe else ""),
        ("Stratification Rationale",
         "To ensure coverage across different database platforms and time periods within the audit scope." if coe else ""),
        ("Sample Size", coe.sample_size if coe else ""),
        ("Sample Approach", "Representative sampling per GIA methodology" if coe else ""),
        ("Sample Start Date", sample_start),
        ("Sample End Date", sample_end),
        ("Complexity", "Moderate"),
        ("Testing completed by", "Audit Team"),
        ("Source Systems", rcm.systems_applications if rcm else "N/A"),
        ("Other Data Sources / Systems", "Yes" if has_da else "No"),
        ("Other Data Sources / Systems Description",
         ", ".join(wp.da_result.data_sources) if has_da and wp.da_result and wp.da_result.data_sources else "N/A"),
        ("Did analytics influence control outcome?", "Yes" if has_da else "No"),
        ("Analytics CT (control testing) coverage", "Full population" if has_da else "N/A"),
        ("Total Record Count",
         wp.da_result.population_size if has_da and wp.da_result and wp.da_result.population_size else "N/A"),
        ("Analytics Procedure Description",
         wp.da_result.analytics_performed if has_da and wp.da_result and wp.da_result.analytics_performed else "N/A"),
        ("COE Conclusion:", coe_conclusion),
        ("Comments/Rationale", comments),
    ]
    for i, (label, value) in enumerate(rows):
        _add_label_value_row(table, i + 1, label, value)


# ─────────────────────────────────────────────
# Main Export
# ─────────────────────────────────────────────

def export_workpaper(workpaper: ControlWorkpaper) -> BytesIO:
    """Export matching SCB GIA template: 3 tables (Core Details, CDE, COE)."""
    doc = Document()

    section = doc.sections[0]
    section.page_width = PAGE_WIDTH
    section.page_height = PAGE_HEIGHT
    section.top_margin = MARGIN
    section.bottom_margin = MARGIN
    section.left_margin = MARGIN
    section.right_margin = MARGIN

    style = doc.styles['Normal']
    style.font.size = Pt(8)

    _build_core_details(doc, workpaper)
    doc.add_paragraph()
    _build_cde_table(doc, workpaper)
    doc.add_paragraph()
    _build_coe_table(doc, workpaper)

    doc.add_paragraph()
    p = doc.add_paragraph()
    run = p.add_run(
        f"Generated by UC-01 v2 Agentic AI Audit Workpaper Assistant | "
        f"{datetime.now().strftime('%d %B %Y %H:%M')}"
    )
    run.italic = True
    run.font.size = Pt(7)
    run.font.color.rgb = RGBColor(0x95, 0xA5, 0xA6)
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER

    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    return buffer