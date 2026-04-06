"""
UC-01 v2: DOCX Workpaper Exporter
Generates professional audit workpaper documents.

Author: Ananya Aithal
"""

from docx import Document
from docx.shared import Inches, Pt, Cm, RGBColor
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.section import WD_ORIENT
from docx.oxml.ns import qn
from io import BytesIO
from datetime import datetime

from models import ControlWorkpaper, ControlEffectiveness, TestingPhase


def _set_cell_shading(cell, color_hex: str):
    """Set cell background color."""
    shading = cell._element.get_or_add_tcPr()
    shading_elem = shading.makeelement(qn('w:shd'), {
        qn('w:fill'): color_hex,
        qn('w:val'): 'clear',
    })
    shading.append(shading_elem)


def _add_styled_table(doc, headers: list[str], rows: list[list[str]], header_color: str = "1B3A5C"):
    """Add a formatted table to the document."""
    table = doc.add_table(rows=1 + len(rows), cols=len(headers))
    table.style = 'Table Grid'
    table.alignment = WD_TABLE_ALIGNMENT.CENTER

    # Header row
    for i, header in enumerate(headers):
        cell = table.rows[0].cells[i]
        cell.text = header
        for paragraph in cell.paragraphs:
            paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
            for run in paragraph.runs:
                run.bold = True
                run.font.color.rgb = RGBColor(255, 255, 255)
                run.font.size = Pt(9)
                run.font.name = 'Calibri'
        _set_cell_shading(cell, header_color)

    # Data rows
    for row_idx, row_data in enumerate(rows):
        for col_idx, value in enumerate(row_data):
            cell = table.rows[row_idx + 1].cells[col_idx]
            cell.text = str(value)
            for paragraph in cell.paragraphs:
                for run in paragraph.runs:
                    run.font.size = Pt(9)
                    run.font.name = 'Calibri'
            # Alternate row shading
            if row_idx % 2 == 0:
                _set_cell_shading(cell, "F2F6FA")

    return table


def _effectiveness_color(eff: ControlEffectiveness) -> str:
    colors = {
        ControlEffectiveness.EFFECTIVE: "27AE60",
        ControlEffectiveness.PARTIALLY_EFFECTIVE: "F39C12",
        ControlEffectiveness.INEFFECTIVE: "E74C3C",
        ControlEffectiveness.NOT_ASSESSED: "95A5A6",
    }
    return colors.get(eff, "95A5A6")


def export_workpaper(workpaper: ControlWorkpaper) -> BytesIO:
    """Export a ControlWorkpaper to a .docx BytesIO object."""
    doc = Document()

    # ── Page setup ──
    section = doc.sections[0]
    section.page_width = Cm(21)
    section.page_height = Cm(29.7)
    section.top_margin = Cm(2)
    section.bottom_margin = Cm(2)
    section.left_margin = Cm(2.5)
    section.right_margin = Cm(2.5)

    # ── Title ──
    title = doc.add_heading(workpaper.audit_name, level=0)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    for run in title.runs:
        run.font.color.rgb = RGBColor(0x1B, 0x3A, 0x5C)

    subtitle = doc.add_heading(f"Control Workpaper: {workpaper.control_name}", level=1)
    subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER

    # ── Metadata table ──
    doc.add_heading("Workpaper Information", level=2)
    meta_data = [
        ["Audit Name", workpaper.audit_name],
        ["Control Name", workpaper.control_name],
        ["Workpaper ID", workpaper.id],
        ["Created", workpaper.created_at.strftime("%Y-%m-%d %H:%M")],
        ["Last Updated", workpaper.last_updated.strftime("%Y-%m-%d %H:%M")],
        ["Completed Phases", ", ".join([p.value for p in workpaper.completed_phases]) or "None"],
        ["Overall Effectiveness", workpaper.effectiveness.value],
        ["Progress", f"{workpaper.progress_pct()}%"],
    ]
    _add_styled_table(doc, ["Field", "Value"], meta_data)

    # ── RCM Section ──
    if workpaper.rcm:
        doc.add_page_break()
        doc.add_heading("Risk Control Matrix (RCM)", level=2)
        for i, row in enumerate(workpaper.rcm):
            doc.add_heading(f"Risk-Control Pair {i+1}: {row.risk_id} / {row.control_id}", level=3)
            rcm_data = [
                ["Risk ID", row.risk_id],
                ["Risk Description", row.risk_description],
                ["Risk Category", row.risk_category],
                ["Control ID", row.control_id],
                ["Control Objective", row.control_objective],
                ["Control Description", row.control_description],
                ["Control Owner", row.control_owner],
                ["Frequency", row.control_frequency],
                ["Type", row.control_type],
                ["Nature", row.control_nature],
                ["Mitigating Activities", row.key_mitigating_activities],
                ["Systems/Applications", row.systems_applications],
                ["Testing Approach", row.testing_approach],
                ["Evidence Required", row.evidence_required],
            ]
            _add_styled_table(doc, ["Attribute", "Detail"], rcm_data)
            doc.add_paragraph()

    # ── CDE Section ──
    if workpaper.cde_result:
        doc.add_page_break()
        doc.add_heading("Control Design Evaluation (CDE)", level=2)
        cde = workpaper.cde_result

        doc.add_heading("Design Assessment", level=3)
        p = doc.add_paragraph()
        run = p.add_run(cde.design_assessment)
        run.bold = True
        run.font.size = Pt(14)

        if cde.design_strengths:
            doc.add_heading("Design Strengths", level=3)
            for s in cde.design_strengths:
                doc.add_paragraph(s, style='List Bullet')

        if cde.design_gaps:
            doc.add_heading("Design Gaps", level=3)
            for g in cde.design_gaps:
                doc.add_paragraph(g, style='List Bullet')

        if cde.compensating_controls:
            doc.add_heading("Compensating Controls", level=3)
            for c in cde.compensating_controls:
                doc.add_paragraph(c, style='List Bullet')

        doc.add_heading("CDE Conclusion", level=3)
        doc.add_paragraph(cde.conclusion)

        if cde.manually_edited:
            p = doc.add_paragraph()
            run = p.add_run("[This section was manually edited by the auditor]")
            run.italic = True
            run.font.color.rgb = RGBColor(0x7F, 0x8C, 0x8D)

    # ── COE Section ──
    if workpaper.coe_result:
        doc.add_page_break()
        doc.add_heading("Control Operating Effectiveness (COE)", level=2)
        coe = workpaper.coe_result

        coe_data = [
            ["Sample Size", coe.sample_size],
            ["Sample Period", coe.sample_period],
            ["Testing Procedure", coe.testing_procedure],
            ["Results Summary", coe.results_summary],
            ["Deviations Found", str(coe.deviations_found)],
        ]
        _add_styled_table(doc, ["Attribute", "Detail"], coe_data)

        if coe.deviation_details:
            doc.add_heading("Deviation Details", level=3)
            for d in coe.deviation_details:
                doc.add_paragraph(d, style='List Bullet')

        doc.add_heading("COE Conclusion", level=3)
        doc.add_paragraph(coe.conclusion)

        if coe.manually_edited:
            p = doc.add_paragraph()
            run = p.add_run("[This section was manually edited by the auditor]")
            run.italic = True
            run.font.color.rgb = RGBColor(0x7F, 0x8C, 0x8D)

    # ── DA Section ──
    if workpaper.da_result:
        doc.add_page_break()
        doc.add_heading("Data Analytics (DA)", level=2)
        da = workpaper.da_result

        da_data = [
            ["Data Sources", ", ".join(da.data_sources) if da.data_sources else "N/A"],
            ["Analytics Performed", da.analytics_performed],
            ["Population Size", da.population_size],
            ["Exceptions Identified", str(da.exceptions_identified)],
        ]
        _add_styled_table(doc, ["Attribute", "Detail"], da_data)

        if da.exception_details:
            doc.add_heading("Exception Details", level=3)
            for e in da.exception_details:
                doc.add_paragraph(e, style='List Bullet')

        if da.visualizations_notes:
            doc.add_heading("Visualizations & Notes", level=3)
            doc.add_paragraph(da.visualizations_notes)

        doc.add_heading("DA Conclusion", level=3)
        doc.add_paragraph(da.conclusion)

        if da.manually_edited:
            p = doc.add_paragraph()
            run = p.add_run("[This section was manually edited by the auditor]")
            run.italic = True
            run.font.color.rgb = RGBColor(0x7F, 0x8C, 0x8D)

    # ── Exceptions Section ──
    if workpaper.exceptions:
        doc.add_page_break()
        doc.add_heading("Exceptions / Findings", level=2)

        headers = ["#", "Source", "Description", "Severity", "Root Cause", "Remediation"]
        rows = []
        for i, exc in enumerate(workpaper.exceptions):
            rows.append([
                str(i + 1),
                exc.source_phase.value,
                exc.description,
                exc.severity.value,
                exc.root_cause,
                exc.remediation_plan,
            ])
        _add_styled_table(doc, headers, rows)

    # ── Overall Conclusion ──
    doc.add_page_break()
    doc.add_heading("Overall Conclusion", level=2)

    p = doc.add_paragraph()
    run = p.add_run(f"Control Effectiveness: {workpaper.effectiveness.value}")
    run.bold = True
    run.font.size = Pt(14)

    if workpaper.ai_conclusion_rationale:
        doc.add_heading("AI-Generated Rationale", level=3)
        doc.add_paragraph(workpaper.ai_conclusion_rationale)

    if workpaper.auditor_override_rationale:
        doc.add_heading("Auditor Override Rationale", level=3)
        doc.add_paragraph(workpaper.auditor_override_rationale)

    # ── Footer ──
    doc.add_paragraph()
    p = doc.add_paragraph()
    run = p.add_run(f"Generated by UC-01 v2 Agentic AI Audit Workpaper Assistant | {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    run.italic = True
    run.font.size = Pt(8)
    run.font.color.rgb = RGBColor(0x95, 0xA5, 0xA6)
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER

    # ── Save to buffer ──
    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    return buffer
