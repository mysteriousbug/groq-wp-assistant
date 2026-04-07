"""
UC-01 v2: Agentic AI Audit Workpaper Assistant
Streamlit App with persistent DB storage.

Features:
  - Persistent storage (SQLite / Azure PostgreSQL / Azure SQL)
  - Multi-document uploads (transcripts + process docs, access matrices, etc.)
  - AI-suggested CDE/COE/DA test procedures from RCM
  - Auditor override of suggestions before testing
  - Non-linear workflow, live preview, .docx export

Author: Ananya Aithal
"""

import streamlit as st
import os
import json
from datetime import datetime

from db_models import (
    init_db, get_db, AuditProject, ControlWorkpaper,
    WorkpaperDocument, TestingPhase, DocumentType,
    ControlEffectiveness, ExceptionSeverity
)
from ai_engine import (
    build_rcm, suggest_test_procedures, analyze_cde, analyze_coe,
    analyze_da, identify_exceptions, generate_conclusion,
    summarize_document
)
from exporter import export_workpaper

# ─────────────────────────────────────────────
# Init
# ─────────────────────────────────────────────

st.set_page_config(
    page_title="UC-01 v2 | Audit Workpaper Assistant",
    page_icon="📋", layout="wide", initial_sidebar_state="expanded",
)

init_db()

UPLOAD_DIR = os.environ.get("UPLOAD_DIR", "./uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

DOC_TYPE_OPTIONS = [dt.value for dt in DocumentType]
PHASE_OPTIONS = [tp.value for tp in TestingPhase]

st.markdown("""
<style>
    .main-header { background: linear-gradient(135deg, #1B3A5C 0%, #2C5F8A 100%);
        padding: 1.5rem 2rem; border-radius: 12px; margin-bottom: 1.5rem; color: white; }
    .main-header h1 { margin: 0; font-size: 1.8rem; }
    .main-header p { margin: 0.3rem 0 0 0; opacity: 0.85; }
    .phase-complete { color: #27AE60; font-weight: bold; }
    .phase-pending { color: #95A5A6; }
    .badge-effective { background: #27AE60; color: white; padding: 2px 8px; border-radius: 10px; }
    .badge-partial { background: #F39C12; color: white; padding: 2px 8px; border-radius: 10px; }
    .badge-ineffective { background: #E74C3C; color: white; padding: 2px 8px; border-radius: 10px; }
    .badge-pending { background: #95A5A6; color: white; padding: 2px 8px; border-radius: 10px; }
</style>
""", unsafe_allow_html=True)


def eff_badge(eff: str) -> str:
    m = {"Effective": "badge-effective", "Partially Effective": "badge-partial",
         "Ineffective": "badge-ineffective"}
    cls = m.get(eff, "badge-pending")
    return f'<span class="{cls}">{eff}</span>'


# ─────────────────────────────────────────────
# SIDEBAR
# ─────────────────────────────────────────────

def render_sidebar():
    with st.sidebar:
        st.markdown("### 🏗️ Audit Project")

        # Groq key
        import os as _os
        groq_key = st.text_input("Groq API Key", type="password",
                                  value=_os.environ.get("GROQ_API_KEY", ""), key="groq_key")
        if groq_key:
            _os.environ["GROQ_API_KEY"] = groq_key

        db = get_db()

        # Select or create project
        projects = db.query(AuditProject).all()
        project_names = ["-- Create New --"] + [p.name for p in projects]
        selected = st.selectbox("Select Project", project_names, key="project_select")

        if selected == "-- Create New --":
            new_name = st.text_input("New Audit Name", placeholder="e.g., Database Services Audit Q2 2026")
            if st.button("Create Project", type="primary", use_container_width=True):
                if new_name:
                    proj = AuditProject(name=new_name)
                    db.add(proj)
                    db.commit()
                    st.session_state["project_id"] = proj.id
                    st.rerun()
            db.close()
            return
        else:
            proj = db.query(AuditProject).filter(AuditProject.name == selected).first()
            st.session_state["project_id"] = proj.id

        st.caption(f"Created: {proj.created_at.strftime('%d %b %Y')}")

        # Add control
        st.markdown("---")
        new_ctrl = st.text_input("Add Control", placeholder="e.g., DB Privileged Access Mgmt")
        if st.button("➕ Add Control", use_container_width=True):
            if new_ctrl:
                existing = db.query(ControlWorkpaper).filter(
                    ControlWorkpaper.project_id == proj.id,
                    ControlWorkpaper.control_name == new_ctrl
                ).first()
                if not existing:
                    wp = ControlWorkpaper(project_id=proj.id, control_name=new_ctrl)
                    db.add(wp)
                    db.commit()
                    st.session_state["workpaper_id"] = wp.id
                    st.rerun()
                else:
                    st.warning("Control already exists.")

        # Control list
        st.markdown("---")
        workpapers = db.query(ControlWorkpaper).filter(
            ControlWorkpaper.project_id == proj.id
        ).all()

        for wp in workpapers:
            is_active = st.session_state.get("workpaper_id") == wp.id
            label = f"{'▶ ' if is_active else ''}{wp.control_name}"
            if st.button(label, key=f"nav_{wp.id}", use_container_width=True,
                        type="primary" if is_active else "secondary"):
                st.session_state["workpaper_id"] = wp.id
                st.session_state["active_phase"] = None
                st.rerun()

        # DB info
        st.markdown("---")
        st.caption(f"💾 DB: {os.environ.get('DATABASE_URL', 'sqlite:///uc01.db')[:40]}...")

        db.close()


# ─────────────────────────────────────────────
# DOCUMENT UPLOAD (shared component)
# ─────────────────────────────────────────────

def render_document_upload(wp_id: int, phase: str, allow_supporting: bool = True):
    """Upload transcripts and optionally supporting documents."""
    db = get_db()

    st.markdown("#### 📄 Upload Transcripts")
    uploaded_transcripts = st.file_uploader(
        f"Upload {phase} transcript(s)",
        type=["txt", "vtt", "md", "docx"],
        accept_multiple_files=True,
        key=f"transcript_upload_{wp_id}_{phase}"
    )

    if uploaded_transcripts:
        for uf in uploaded_transcripts:
            existing = db.query(WorkpaperDocument).filter(
                WorkpaperDocument.workpaper_id == wp_id,
                WorkpaperDocument.filename == uf.name,
                WorkpaperDocument.phase == phase,
            ).first()
            if not existing:
                content = uf.read().decode("utf-8", errors="replace")
                # Save file to disk
                fpath = os.path.join(UPLOAD_DIR, f"{wp_id}_{phase}_{uf.name}")
                with open(fpath, "w") as f:
                    f.write(content)

                doc = WorkpaperDocument(
                    workpaper_id=wp_id,
                    filename=uf.name,
                    doc_type=DocumentType.TRANSCRIPT.value,
                    phase=phase,
                    content=content,
                    file_path=fpath,
                )
                db.add(doc)
                db.commit()
                st.success(f"Uploaded: {uf.name}")

    if allow_supporting:
        st.markdown("#### 📎 Upload Supporting Documents")
        st.caption("Process docs, access matrices, technical implementation procedures, risk ratings, etc.")

        col1, col2 = st.columns([2, 1])
        with col2:
            doc_type = st.selectbox("Document Type", DOC_TYPE_OPTIONS[1:], key=f"doctype_{wp_id}_{phase}")

        with col1:
            uploaded_docs = st.file_uploader(
                "Upload supporting document(s)",
                type=["txt", "md", "docx", "pdf", "xlsx", "csv", "msg"],
                accept_multiple_files=True,
                key=f"support_upload_{wp_id}_{phase}"
            )

        if uploaded_docs:
            for uf in uploaded_docs:
                existing = db.query(WorkpaperDocument).filter(
                    WorkpaperDocument.workpaper_id == wp_id,
                    WorkpaperDocument.filename == uf.name,
                ).first()
                if not existing:
                    raw = uf.read()
                    # Try text decode, fallback to noting it's binary
                    try:
                        content = raw.decode("utf-8", errors="replace")
                    except Exception:
                        content = f"[Binary file: {uf.name} — {len(raw)} bytes]"

                    fpath = os.path.join(UPLOAD_DIR, f"{wp_id}_{uf.name}")
                    with open(fpath, "wb") as f:
                        f.write(raw)

                    d = WorkpaperDocument(
                        workpaper_id=wp_id,
                        filename=uf.name,
                        doc_type=doc_type,
                        phase=phase,
                        content=content,
                        file_path=fpath,
                    )
                    db.add(d)
                    db.commit()
                    st.success(f"Uploaded: {uf.name} ({doc_type})")

    # Show uploaded docs
    docs = db.query(WorkpaperDocument).filter(
        WorkpaperDocument.workpaper_id == wp_id,
        WorkpaperDocument.phase == phase
    ).all()
    if docs:
        st.markdown("**Uploaded files:**")
        for d in docs:
            icon = "📝" if d.doc_type == DocumentType.TRANSCRIPT.value else "📎"
            with st.expander(f"{icon} {d.filename} ({d.doc_type})"):
                if d.summary:
                    st.markdown(f"**Summary:** {d.summary}")
                st.text_area("Content preview", d.content[:2000], height=100, disabled=True, key=f"prev_{d.id}")

    db.close()
    return docs


# ─────────────────────────────────────────────
# PHASE: Walkthrough & RCM
# ─────────────────────────────────────────────

def render_walkthrough_phase(wp: ControlWorkpaper):
    st.markdown("## 📝 Control Walkthrough & RCM")
    db = get_db()

    # Upload section
    docs = render_document_upload(wp.id, TestingPhase.WALKTHROUGH.value, allow_supporting=True)

    transcripts = [d for d in docs if d.doc_type == DocumentType.TRANSCRIPT.value]
    support_docs = [d for d in docs if d.doc_type != DocumentType.TRANSCRIPT.value]

    if transcripts or support_docs:
        col1, col2 = st.columns(2)
        with col1:
            if st.button("🤖 Build RCM from Documents", type="primary", use_container_width=True):
                with st.spinner("AI is reading all documents and building the RCM..."):
                    try:
                        t_texts = [{"filename": d.filename, "content": d.content} for d in transcripts]
                        s_texts = [{"filename": d.filename, "doc_type": d.doc_type, "content": d.content}
                                   for d in support_docs]

                        # Summarize docs
                        for d in transcripts + support_docs:
                            if not d.summary:
                                d.summary = summarize_document(d.content, d.doc_type)

                        rcm_rows = build_rcm(wp.control_name, wp.project.name, t_texts, s_texts)
                        wp.rcm = rcm_rows
                        wp.mark_phase_complete(TestingPhase.WALKTHROUGH.value)
                        db.commit()

                        # Now suggest test procedures
                        st.info("Generating AI-suggested test procedures...")
                        summaries = [d.summary for d in support_docs if d.summary]
                        suggestions = suggest_test_procedures(wp.control_name, rcm_rows, summaries)
                        wp.suggested_tests = suggestions
                        db.commit()

                        st.rerun()
                    except Exception as e:
                        st.error(f"Error: {e}")

        with col2:
            if st.button("🔄 Re-build RCM", use_container_width=True):
                wp.rcm = []
                phases = wp.completed_phases
                phases = [p for p in phases if p != TestingPhase.WALKTHROUGH.value]
                wp.completed_phases = phases
                db.commit()
                st.rerun()

    # ── Editable RCM ──
    rcm = wp.rcm
    if rcm:
        st.markdown("### Risk Control Matrix")
        st.caption("Edit any field. Click 'Save RCM Changes' when done.")

        rcm_headers = [
            "process_ref", "process_title", "process_description",
            "risk_ref", "risk_title", "risk_description",
            "control_ref", "control_title", "control_description",
            "related_key_questions", "cde_required", "coe_required",
            "cde_or_coe_da_required",
            "cde_test_procedures", "coe_test_procedures",
            "da_test_procedure", "audit_team_member"
        ]

        for i, row in enumerate(rcm):
            with st.expander(f"**{row.get('control_ref', f'Row {i+1}')}** — {row.get('control_title', '')[:60]}", expanded=(i == 0)):
                col1, col2 = st.columns(2)
                with col1:
                    row["process_ref"] = st.text_input("Process Ref", row.get("process_ref", ""), key=f"rcm_pref_{i}")
                    row["process_title"] = st.text_input("Process Title", row.get("process_title", ""), key=f"rcm_ptitle_{i}")
                    row["risk_ref"] = st.text_input("Risk Ref", row.get("risk_ref", ""), key=f"rcm_rref_{i}")
                    row["risk_title"] = st.text_input("Risk Title", row.get("risk_title", ""), key=f"rcm_rtitle_{i}")
                    row["risk_description"] = st.text_area("Risk Description", row.get("risk_description", ""), height=80, key=f"rcm_rdesc_{i}")
                    row["control_ref"] = st.text_input("Control Ref", row.get("control_ref", ""), key=f"rcm_cref_{i}")
                    row["control_title"] = st.text_input("Control Title", row.get("control_title", ""), key=f"rcm_ctitle_{i}")
                    row["control_description"] = st.text_area("Control Description", row.get("control_description", ""), height=100, key=f"rcm_cdesc_{i}")
                with col2:
                    row["related_key_questions"] = st.text_area("Related Key Questions", row.get("related_key_questions", ""), height=80, key=f"rcm_kq_{i}")
                    row["cde_required"] = st.selectbox("CDE Required", ["Yes", "No"], index=0 if row.get("cde_required", "Yes") == "Yes" else 1, key=f"rcm_cde_{i}")
                    row["coe_required"] = st.selectbox("COE Required", ["Yes", "No"], index=0 if row.get("coe_required", "Yes") == "Yes" else 1, key=f"rcm_coe_{i}")
                    row["cde_or_coe_da_required"] = st.selectbox("DA Required", ["Yes", "No"], index=0 if row.get("cde_or_coe_da_required", "No") == "Yes" else 1, key=f"rcm_da_{i}")
                    row["cde_test_procedures"] = st.text_area("CDE Test Procedures", row.get("cde_test_procedures", ""), height=100, key=f"rcm_cdep_{i}")
                    row["coe_test_procedures"] = st.text_area("COE Test Procedures", row.get("coe_test_procedures", ""), height=100, key=f"rcm_coep_{i}")
                    row["da_test_procedure"] = st.text_area("DA Test Procedure", row.get("da_test_procedure", ""), height=80, key=f"rcm_dap_{i}")
                    row["audit_team_member"] = st.text_input("Audit Team Member", row.get("audit_team_member", ""), key=f"rcm_atm_{i}")

        if st.button("💾 Save RCM Changes", type="primary", use_container_width=True):
            wp.rcm = rcm
            db.commit()
            st.success("RCM saved.")

    # ── AI Suggested Test Procedures ──
    suggestions = wp.suggested_tests
    if suggestions:
        st.markdown("---")
        st.markdown("### 🤖 AI-Suggested Test Procedures")
        st.caption("Review and override before proceeding to testing phases.")

        for phase_key, label in [("cde_procedures", "CDE"), ("coe_procedures", "COE"), ("da_procedures", "DA")]:
            phase_data = suggestions.get(phase_key, {})
            if phase_data:
                recommended = phase_data.get("recommended", True)
                icon = "✅" if recommended else "⬜"
                with st.expander(f"{icon} **{label}** — {'Recommended' if recommended else 'Not Recommended'}: {phase_data.get('rationale', '')[:100]}"):
                    st.markdown(f"**Rationale:** {phase_data.get('rationale', '')}")
                    steps = phase_data.get("test_steps", phase_data.get("analytics_to_perform", []))
                    if steps:
                        st.markdown("**Suggested Steps:**")
                        for s in steps:
                            st.markdown(f"- {s}")
                    evidence = phase_data.get("evidence_to_request", phase_data.get("data_sources", []))
                    if evidence:
                        st.markdown("**Evidence / Data Sources:**")
                        for e in evidence:
                            st.markdown(f"- {e}")

    db.close()
    st.markdown("---")
    render_workpaper_preview(wp)


# ─────────────────────────────────────────────
# PHASE: CDE
# ─────────────────────────────────────────────

def render_cde_phase(wp: ControlWorkpaper):
    st.markdown("## 🔍 Control Design Evaluation (CDE)")
    db = get_db()

    if not wp.rcm:
        st.warning("Build the RCM first (Walkthrough phase).")

    docs = render_document_upload(wp.id, TestingPhase.CDE.value, allow_supporting=True)
    additional = st.text_area("Additional auditor notes", key=f"cde_notes_{wp.id}")

    if st.button("🤖 Run CDE Analysis", type="primary", use_container_width=True):
        with st.spinner("AI is evaluating control design..."):
            try:
                t_texts = [{"filename": d.filename, "content": d.content} for d in docs if d.doc_type == DocumentType.TRANSCRIPT.value]
                s_texts = [{"filename": d.filename, "doc_type": d.doc_type, "content": d.content} for d in docs if d.doc_type != DocumentType.TRANSCRIPT.value]
                # Also include walkthrough supporting docs
                wt_support = wp.get_supporting_docs()
                s_texts += [{"filename": d.filename, "doc_type": d.doc_type, "content": d.content} for d in wt_support]

                result = analyze_cde(wp.control_name, wp.project.name, wp.rcm, t_texts, s_texts, additional)
                wp.cde_result = result
                wp.mark_phase_complete(TestingPhase.CDE.value)
                db.commit()
                st.rerun()
            except Exception as e:
                st.error(f"Error: {e}")

    cde = wp.cde_result
    if cde:
        st.markdown("### CDE Results")
        cde["design_assessment"] = st.selectbox("Assessment", ["Well Designed", "Needs Improvement", "Poorly Designed"],
            index=["Well Designed", "Needs Improvement", "Poorly Designed"].index(cde.get("design_assessment", "Well Designed"))
            if cde.get("design_assessment") in ["Well Designed", "Needs Improvement", "Poorly Designed"] else 0,
            key=f"cde_assess_{wp.id}")
        strengths = st.text_area("Strengths (one per line)", "\n".join(cde.get("design_strengths", [])), key=f"cde_str_{wp.id}")
        cde["design_strengths"] = [s.strip() for s in strengths.split("\n") if s.strip()]
        gaps = st.text_area("Gaps (one per line)", "\n".join(cde.get("design_gaps", [])), key=f"cde_gaps_{wp.id}")
        cde["design_gaps"] = [g.strip() for g in gaps.split("\n") if g.strip()]
        cde["conclusion"] = st.text_area("CDE Conclusion", cde.get("conclusion", ""), height=150, key=f"cde_conc_{wp.id}")
        cde["manually_edited"] = True

        if st.button("💾 Save CDE Changes", use_container_width=True):
            wp.cde_result = cde
            db.commit()
            st.success("CDE saved.")

    db.close()
    st.markdown("---")
    render_workpaper_preview(wp)


# ─────────────────────────────────────────────
# PHASE: COE
# ─────────────────────────────────────────────

def render_coe_phase(wp: ControlWorkpaper):
    st.markdown("## ⚙️ Control Operating Effectiveness (COE)")
    db = get_db()

    if not wp.rcm:
        st.warning("Build the RCM first (Walkthrough phase).")

    docs = render_document_upload(wp.id, TestingPhase.COE.value, allow_supporting=True)
    additional = st.text_area("Additional auditor notes", key=f"coe_notes_{wp.id}")

    if st.button("🤖 Run COE Analysis", type="primary", use_container_width=True):
        with st.spinner("AI is evaluating operating effectiveness..."):
            try:
                t_texts = [{"filename": d.filename, "content": d.content} for d in docs if d.doc_type == DocumentType.TRANSCRIPT.value]
                s_texts = [{"filename": d.filename, "doc_type": d.doc_type, "content": d.content} for d in docs if d.doc_type != DocumentType.TRANSCRIPT.value]
                result = analyze_coe(wp.control_name, wp.project.name, wp.rcm, t_texts, s_texts, additional)
                wp.coe_result = result
                wp.mark_phase_complete(TestingPhase.COE.value)
                db.commit()
                st.rerun()
            except Exception as e:
                st.error(f"Error: {e}")

    coe = wp.coe_result
    if coe:
        st.markdown("### COE Results")
        col1, col2 = st.columns(2)
        with col1:
            coe["sample_size"] = st.text_input("Sample Size", coe.get("sample_size", ""), key=f"coe_ss_{wp.id}")
            coe["sample_period"] = st.text_input("Sample Period", coe.get("sample_period", ""), key=f"coe_sp_{wp.id}")
            coe["deviations_found"] = st.number_input("Deviations", min_value=0, value=coe.get("deviations_found", 0), key=f"coe_dev_{wp.id}")
        with col2:
            coe["testing_procedure"] = st.text_area("Testing Procedure", coe.get("testing_procedure", ""), height=100, key=f"coe_proc_{wp.id}")
            coe["results_summary"] = st.text_area("Results Summary", coe.get("results_summary", ""), height=100, key=f"coe_res_{wp.id}")
        coe["conclusion"] = st.text_area("COE Conclusion", coe.get("conclusion", ""), height=150, key=f"coe_conc_{wp.id}")
        coe["manually_edited"] = True

        if st.button("💾 Save COE Changes", use_container_width=True):
            wp.coe_result = coe
            db.commit()
            st.success("COE saved.")

    db.close()
    st.markdown("---")
    render_workpaper_preview(wp)


# ─────────────────────────────────────────────
# PHASE: DA
# ─────────────────────────────────────────────

def render_da_phase(wp: ControlWorkpaper):
    st.markdown("## 📊 Data Analytics (DA)")
    db = get_db()

    docs = render_document_upload(wp.id, TestingPhase.DA.value, allow_supporting=True)
    additional = st.text_area("Additional DA context", key=f"da_notes_{wp.id}")

    if st.button("🤖 Run DA Analysis", type="primary", use_container_width=True):
        with st.spinner("Analyzing..."):
            try:
                t_texts = [{"filename": d.filename, "content": d.content} for d in docs if d.doc_type == DocumentType.TRANSCRIPT.value]
                s_texts = [{"filename": d.filename, "doc_type": d.doc_type, "content": d.content} for d in docs if d.doc_type != DocumentType.TRANSCRIPT.value]
                result = analyze_da(wp.control_name, wp.project.name, wp.rcm, t_texts, s_texts, additional)
                wp.da_result = result
                wp.mark_phase_complete(TestingPhase.DA.value)
                db.commit()
                st.rerun()
            except Exception as e:
                st.error(f"Error: {e}")

    da = wp.da_result
    if da:
        st.markdown("### DA Results")
        ds = st.text_area("Data Sources (one per line)", "\n".join(da.get("data_sources", [])), key=f"da_ds_{wp.id}")
        da["data_sources"] = [s.strip() for s in ds.split("\n") if s.strip()]
        da["analytics_performed"] = st.text_area("Analytics Performed", da.get("analytics_performed", ""), key=f"da_ap_{wp.id}")
        da["population_size"] = st.text_input("Population Size", da.get("population_size", ""), key=f"da_pop_{wp.id}")
        da["exceptions_identified"] = st.number_input("Exceptions", min_value=0, value=da.get("exceptions_identified", 0), key=f"da_exc_{wp.id}")
        da["conclusion"] = st.text_area("DA Conclusion", da.get("conclusion", ""), height=150, key=f"da_conc_{wp.id}")
        da["manually_edited"] = True

        if st.button("💾 Save DA Changes", use_container_width=True):
            wp.da_result = da
            db.commit()
            st.success("DA saved.")

    db.close()
    st.markdown("---")
    render_workpaper_preview(wp)


# ─────────────────────────────────────────────
# PHASE: Exceptions
# ─────────────────────────────────────────────

def render_exceptions_phase(wp: ControlWorkpaper):
    st.markdown("## ⚠️ Exception Reporting")
    db = get_db()

    additional = st.text_area("Additional context", key=f"exc_notes_{wp.id}")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("🤖 AI: Identify Exceptions", type="primary", use_container_width=True):
            with st.spinner("Reviewing..."):
                try:
                    excs = identify_exceptions(wp.control_name, wp.cde_result, wp.coe_result, wp.da_result, additional)
                    wp.exceptions = excs
                    wp.mark_phase_complete(TestingPhase.EXCEPTIONS.value)
                    db.commit()
                    st.rerun()
                except Exception as e:
                    st.error(f"Error: {e}")
    with col2:
        if st.button("➕ Add Manually", use_container_width=True):
            excs = wp.exceptions
            excs.append({"description": "", "severity": "Medium", "source_phase": "CDE Testing",
                         "root_cause": "", "management_response": "", "remediation_plan": "", "target_date": ""})
            wp.exceptions = excs
            db.commit()
            st.rerun()

    excs = wp.exceptions
    if excs:
        for i, exc in enumerate(excs):
            with st.expander(f"Exception {i+1}: {exc.get('description', 'New')[:50]}", expanded=True):
                exc["description"] = st.text_area("Description", exc.get("description", ""), key=f"exc_d_{wp.id}_{i}")
                exc["severity"] = st.selectbox("Severity", ["Low", "Medium", "High", "Critical"],
                    index=["Low", "Medium", "High", "Critical"].index(exc.get("severity", "Medium")), key=f"exc_s_{wp.id}_{i}")
                exc["root_cause"] = st.text_area("Root Cause", exc.get("root_cause", ""), height=80, key=f"exc_rc_{wp.id}_{i}")
                exc["remediation_plan"] = st.text_area("Remediation", exc.get("remediation_plan", ""), height=80, key=f"exc_rp_{wp.id}_{i}")

        if st.button("💾 Save Exceptions", use_container_width=True):
            wp.exceptions = excs
            if TestingPhase.EXCEPTIONS.value not in wp.completed_phases:
                wp.mark_phase_complete(TestingPhase.EXCEPTIONS.value)
            db.commit()
            st.success("Saved.")

    db.close()
    st.markdown("---")
    render_workpaper_preview(wp)


# ─────────────────────────────────────────────
# LIVE WORKPAPER PREVIEW
# ─────────────────────────────────────────────

def render_workpaper_preview(wp: ControlWorkpaper):
    st.markdown("## 📄 Live Workpaper Preview")

    rcm = wp.rcm
    rcm0 = rcm[0] if rcm else {}
    cde = wp.cde_result
    coe = wp.coe_result
    da = wp.da_result
    wt_docs = wp.get_transcripts(TestingPhase.WALKTHROUGH.value)

    # Core Details
    st.markdown("### 🔵 CORE DETAILS")
    st.markdown(f"**Control:** {wp.control_name}")
    st.markdown(f"**Risk:** {rcm0.get('risk_description', '—')[:150]}")
    st.markdown(f"**Status:** {eff_badge(wp.effectiveness)}", unsafe_allow_html=True)
    st.markdown(f"**Progress:** {wp.progress_pct()}%")

    # CDE section (shows walkthrough data immediately)
    if wt_docs or cde:
        st.markdown("---")
        st.markdown("### 🔵 CDE")
        if wt_docs:
            st.markdown("**Process Walkthrough:**")
            for d in wt_docs:
                st.markdown(f"- {d.filename} ({d.uploaded_at.strftime('%d %b %Y')})")
            support = wp.get_supporting_docs()
            if support:
                st.markdown("**Supporting Documents:**")
                for d in support:
                    st.markdown(f"- {d.filename} ({d.doc_type})")
        if cde:
            st.markdown(f"**Assessment:** {cde.get('design_assessment', '')}")
            st.markdown(f"**Conclusion:** {cde.get('conclusion', '')[:200]}")

    if coe:
        st.markdown("---")
        st.markdown("### 🔵 COE")
        st.markdown(f"**Samples:** {coe.get('sample_size', '')} | **Deviations:** {coe.get('deviations_found', 0)}")
        st.markdown(f"**Conclusion:** {coe.get('conclusion', '')[:200]}")

    if da:
        st.markdown("---")
        st.markdown("### 📊 DA")
        st.markdown(f"**Population:** {da.get('population_size', '')} | **Exceptions:** {da.get('exceptions_identified', 0)}")

    if wp.exceptions:
        st.markdown("---")
        st.markdown("### ⚠️ Exceptions")
        for i, exc in enumerate(wp.exceptions):
            st.markdown(f"**{i+1}.** [{exc.get('severity', '')}] {exc.get('description', '')}")

    if wp.ai_conclusion_rationale:
        st.markdown("---")
        st.markdown(f"### Conclusion: {eff_badge(wp.effectiveness)}", unsafe_allow_html=True)
        st.markdown(wp.ai_conclusion_rationale[:400])


# ─────────────────────────────────────────────
# CONTROL DASHBOARD
# ─────────────────────────────────────────────

def render_control_dashboard(wp: ControlWorkpaper):
    st.markdown(f"""<div class="main-header">
        <h1>{wp.control_name}</h1>
        <p>{wp.project.name} | {eff_badge(wp.effectiveness)} | Progress: {wp.progress_pct()}%</p>
    </div>""", unsafe_allow_html=True)

    # Phase nav
    phases = [
        (TestingPhase.WALKTHROUGH.value, "📝", "Walkthrough & RCM"),
        (TestingPhase.CDE.value, "🔍", "CDE Testing"),
        (TestingPhase.COE.value, "⚙️", "COE Testing"),
        (TestingPhase.DA.value, "📊", "Data Analytics"),
        (TestingPhase.EXCEPTIONS.value, "⚠️", "Exceptions"),
    ]
    cols = st.columns(5)
    for i, (phase, icon, label) in enumerate(phases):
        with cols[i]:
            done = phase in wp.completed_phases
            active = st.session_state.get("active_phase") == phase
            status = "✅" if done else ("🔶" if active else "⬜")
            if st.button(f"{icon} {label}\n{status}", key=f"ph_{phase}",
                        use_container_width=True, type="primary" if active else "secondary"):
                st.session_state["active_phase"] = phase
                st.rerun()

    db = get_db()
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🤖 Generate AI Conclusion", type="primary", use_container_width=True):
            with st.spinner("Analyzing all evidence..."):
                try:
                    eff, rationale = generate_conclusion(
                        wp.control_name, wp.rcm, wp.cde_result, wp.coe_result,
                        wp.da_result, wp.exceptions, wp.completed_phases
                    )
                    wp.effectiveness = eff
                    wp.ai_conclusion_rationale = rationale
                    db.commit()
                    st.rerun()
                except Exception as e:
                    st.error(f"Error: {e}")
    with col2:
        if st.button("📥 Download Workpaper (.docx)", use_container_width=True):
            try:
                buffer = export_workpaper(wp)
                st.download_button("⬇️ Save", data=buffer,
                    file_name=f"WP_{wp.control_name.replace(' ','_')}_{datetime.now().strftime('%Y%m%d')}.docx",
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    use_container_width=True)
            except Exception as e:
                st.error(f"Export error: {e}")

    # Auditor override
    with st.expander("✏️ Auditor Override"):
        eff_options = ["Not Assessed", "Effective", "Partially Effective", "Ineffective"]
        override_eff = st.selectbox("Override Effectiveness", eff_options,
            index=eff_options.index(wp.effectiveness) if wp.effectiveness in eff_options else 0, key=f"ov_eff_{wp.id}")
        override_rat = st.text_area("Override Rationale", wp.auditor_override_rationale or "", key=f"ov_rat_{wp.id}")
        if st.button("Save Override", key=f"ov_save_{wp.id}"):
            wp.effectiveness = override_eff
            wp.auditor_override_rationale = override_rat
            db.commit()
            st.success("Override saved.")
            st.rerun()

    db.close()
    st.markdown("---")

    # Render active phase
    phase = st.session_state.get("active_phase")
    if phase == TestingPhase.WALKTHROUGH.value:
        render_walkthrough_phase(wp)
    elif phase == TestingPhase.CDE.value:
        render_cde_phase(wp)
    elif phase == TestingPhase.COE.value:
        render_coe_phase(wp)
    elif phase == TestingPhase.DA.value:
        render_da_phase(wp)
    elif phase == TestingPhase.EXCEPTIONS.value:
        render_exceptions_phase(wp)
    else:
        render_workpaper_preview(wp)


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

def main():
    render_sidebar()

    wp_id = st.session_state.get("workpaper_id")
    if not wp_id:
        st.markdown("""<div class="main-header">
            <h1>📋 UC-01 v2 — Agentic AI Audit Workpaper Assistant</h1>
            <p>Persistent storage | Multi-document | AI-suggested test procedures</p>
        </div>""", unsafe_allow_html=True)
        st.markdown("👈 **Select or create a project and add controls in the sidebar.**")
        return

    db = get_db()
    wp = db.get(ControlWorkpaper, wp_id)
    if not wp:
        st.error("Workpaper not found.")
        db.close()
        return

    render_control_dashboard(wp)
    db.close()


if __name__ == "__main__":
    main()