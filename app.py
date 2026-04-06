"""
UC-01 v2: Agentic AI Audit Workpaper Assistant
Streamlit Application — Multi-Control, Non-Linear Workflow

Features:
  - Multi-control audit projects
  - Multiple transcript uploads per control
  - Non-linear workflow (CDE/COE/DA in any order)
  - Live workpaper preview after every step
  - Full manual editing capability
  - AI-powered conclusion generation
  - Professional .docx export

Author: Ananya Aithal
"""

import streamlit as st
import json
from datetime import datetime

from models import (
    AuditProject, ControlWorkpaper, Transcript, TestingPhase,
    ControlEffectiveness, ExceptionSeverity, ExceptionRecord,
    CDEResult, COEResult, DAResult, RCMRow, WalkthroughExtraction
)
from ai_engine import (
    extract_walkthrough, build_rcm_from_extractions,
    analyze_cde, analyze_coe, analyze_da,
    identify_exceptions, generate_conclusion,
    summarize_transcript
)
from exporter import export_workpaper


# ─────────────────────────────────────────────
# Page Config & Styling
# ─────────────────────────────────────────────

st.set_page_config(
    page_title="UC-01 v2 | Audit Workpaper Assistant",
    page_icon="📋",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;700&family=JetBrains+Mono:wght@400;500&display=swap');

    .stApp {
        font-family: 'DM Sans', sans-serif;
    }
    
    .main-header {
        background: linear-gradient(135deg, #1B3A5C 0%, #2C5F8A 100%);
        padding: 1.5rem 2rem;
        border-radius: 12px;
        margin-bottom: 1.5rem;
        color: white;
    }
    .main-header h1 {
        margin: 0; font-size: 1.8rem; font-weight: 700;
    }
    .main-header p {
        margin: 0.3rem 0 0 0; opacity: 0.85; font-size: 0.95rem;
    }

    .phase-card {
        border: 2px solid #e0e0e0;
        border-radius: 10px;
        padding: 1rem 1.2rem;
        margin-bottom: 0.8rem;
        transition: all 0.2s;
    }
    .phase-card:hover { border-color: #2C5F8A; }
    .phase-complete { border-color: #27AE60 !important; background: #f0faf4; }
    .phase-active { border-color: #F39C12 !important; background: #fef9ed; }

    .status-badge {
        display: inline-block;
        padding: 0.2rem 0.7rem;
        border-radius: 20px;
        font-size: 0.75rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    .badge-effective { background: #27AE60; color: white; }
    .badge-partial { background: #F39C12; color: white; }
    .badge-ineffective { background: #E74C3C; color: white; }
    .badge-pending { background: #95A5A6; color: white; }

    .metric-row {
        display: flex; gap: 1rem; margin-bottom: 1rem;
    }
    .metric-box {
        flex: 1;
        background: #f7f9fc;
        border-radius: 8px;
        padding: 0.8rem 1rem;
        text-align: center;
        border: 1px solid #e8edf2;
    }
    .metric-box .value { font-size: 1.5rem; font-weight: 700; color: #1B3A5C; }
    .metric-box .label { font-size: 0.75rem; color: #7f8c8d; text-transform: uppercase; }

    .transcript-chip {
        display: inline-block;
        background: #eef2f7;
        border-radius: 6px;
        padding: 0.3rem 0.7rem;
        margin: 0.2rem;
        font-size: 0.8rem;
        border: 1px solid #d5dde5;
    }

    div[data-testid="stSidebar"] {
        background: #f7f9fc;
    }
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────
# Session State Initialization
# ─────────────────────────────────────────────

def init_state():
    if "project" not in st.session_state:
        st.session_state.project = None
    if "active_control" not in st.session_state:
        st.session_state.active_control = None
    if "active_phase" not in st.session_state:
        st.session_state.active_phase = None
    if "extractions" not in st.session_state:
        st.session_state.extractions = {}  # control_name -> list[WalkthroughExtraction]

init_state()


# ─────────────────────────────────────────────
# Helper Functions
# ─────────────────────────────────────────────

def get_active_workpaper() -> ControlWorkpaper | None:
    if st.session_state.project and st.session_state.active_control:
        return st.session_state.project.get_workpaper(st.session_state.active_control)
    return None


def effectiveness_badge(eff: ControlEffectiveness) -> str:
    cls_map = {
        ControlEffectiveness.EFFECTIVE: "badge-effective",
        ControlEffectiveness.PARTIALLY_EFFECTIVE: "badge-partial",
        ControlEffectiveness.INEFFECTIVE: "badge-ineffective",
        ControlEffectiveness.NOT_ASSESSED: "badge-pending",
    }
    return f'<span class="status-badge {cls_map[eff]}">{eff.value}</span>'


# ─────────────────────────────────────────────
# SIDEBAR — Project & Control Navigation
# ─────────────────────────────────────────────

def render_sidebar():
    with st.sidebar:
        st.markdown("### 🏗️ Audit Project")

        if st.session_state.project is None:
            st.markdown("---")
            st.markdown("**Create New Project**")
            project_name = st.text_input(
                "Audit Name",
                placeholder="e.g., Database Services Audit Q2 2026",
                key="new_project_name"
            )
            if st.button("Create Project", use_container_width=True, type="primary"):
                if project_name:
                    st.session_state.project = AuditProject(name=project_name)
                    st.rerun()
                else:
                    st.warning("Enter a project name.")
            return

        project = st.session_state.project
        st.markdown(f"**{project.name}**")
        st.caption(f"Created: {project.created_at.strftime('%d %b %Y')}")

        # ── Add Control ──
        st.markdown("---")
        st.markdown("**Controls**")

        new_control = st.text_input(
            "Add Control",
            placeholder="e.g., DB Privileged Access Mgmt",
            key="new_control_input"
        )
        if st.button("➕ Add Control", use_container_width=True):
            if new_control and not project.get_workpaper(new_control):
                project.add_workpaper(new_control)
                st.session_state.active_control = new_control
                st.rerun()
            elif project.get_workpaper(new_control):
                st.warning("Control already exists.")

        # ── Control List ──
        if project.workpapers:
            st.markdown("---")
            for wp in project.workpapers:
                col1, col2 = st.columns([3, 1])
                with col1:
                    is_active = st.session_state.active_control == wp.control_name
                    btn_type = "primary" if is_active else "secondary"
                    if st.button(
                        f"{'▶ ' if is_active else ''}{wp.control_name}",
                        key=f"nav_{wp.id}",
                        use_container_width=True,
                        type=btn_type
                    ):
                        st.session_state.active_control = wp.control_name
                        st.session_state.active_phase = None
                        st.rerun()
                with col2:
                    st.markdown(f"**{wp.progress_pct()}%**")

        # ── GROQ API Key ──
        st.markdown("---")
        st.markdown("**⚙️ Settings**")
        import os
        groq_key = st.text_input(
            "Groq API Key",
            type="password",
            value=os.environ.get("GROQ_API_KEY", ""),
            key="groq_key_input"
        )
        if groq_key:
            os.environ["GROQ_API_KEY"] = groq_key

        # ── Reset ──
        st.markdown("---")
        if st.button("🗑️ Reset Project", use_container_width=True):
            st.session_state.project = None
            st.session_state.active_control = None
            st.session_state.active_phase = None
            st.session_state.extractions = {}
            st.rerun()


# ─────────────────────────────────────────────
# MAIN: No project yet
# ─────────────────────────────────────────────

def render_welcome():
    st.markdown("""
    <div class="main-header">
        <h1>📋 UC-01 v2 — Agentic AI Audit Workpaper Assistant</h1>
        <p>Multi-control, principle-based audit workpaper builder powered by AI</p>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("""
    ### How It Works

    **1. Create a Project** — Define your audit engagement (e.g., Database Services Audit).

    **2. Add Controls** — Each control (e.g., DB Privileged Access, DB Backup & Restore) gets its own workpaper.

    **3. Upload Transcripts** — Upload MS Teams walkthrough transcripts → AI extracts the RCM.

    **4. Test in Any Order** — CDE, COE, DA — in whatever sequence fits your methodology.

    **5. Review & Edit** — See the live workpaper draft after each step. Edit anything manually.

    **6. Conclude & Export** — AI recommends effectiveness. Override if needed. Download .docx.

    ---
    👈 **Start by creating a project in the sidebar.**
    """)


# ─────────────────────────────────────────────
# MAIN: Control Dashboard
# ─────────────────────────────────────────────

def render_control_dashboard(wp: ControlWorkpaper):
    st.markdown(f"""
    <div class="main-header">
        <h1>{wp.control_name}</h1>
        <p>{wp.audit_name} &nbsp;|&nbsp; {effectiveness_badge(wp.effectiveness)} &nbsp;|&nbsp; Progress: {wp.progress_pct()}%</p>
    </div>
    """, unsafe_allow_html=True)

    # ── Phase Navigation (Non-linear!) ──
    phases = [
        (TestingPhase.WALKTHROUGH, "📝", "Walkthrough & RCM"),
        (TestingPhase.CDE, "🔍", "CDE Testing"),
        (TestingPhase.COE, "⚙️", "COE Testing"),
        (TestingPhase.DA, "📊", "Data Analytics"),
        (TestingPhase.EXCEPTIONS, "⚠️", "Exceptions"),
    ]

    st.markdown("### Workflow Phases")
    st.caption("Click any phase — no fixed order required.")

    cols = st.columns(5)
    for i, (phase, icon, label) in enumerate(phases):
        with cols[i]:
            is_complete = phase in wp.completed_phases
            is_active = st.session_state.active_phase == phase
            status = "✅" if is_complete else ("🔶" if is_active else "⬜")

            if st.button(
                f"{icon} {label}\n{status}",
                key=f"phase_{phase.value}",
                use_container_width=True,
                type="primary" if is_active else "secondary"
            ):
                st.session_state.active_phase = phase
                st.rerun()

    # ── Conclusion & Export row ──
    col_conclude, col_export = st.columns(2)
    with col_conclude:
        if st.button("🤖 Generate AI Conclusion", use_container_width=True, type="primary"):
            with st.spinner("AI is analyzing all evidence..."):
                try:
                    eff, rationale = generate_conclusion(wp)
                    wp.effectiveness = eff
                    wp.ai_conclusion_rationale = rationale
                    wp.last_updated = datetime.now()
                    st.rerun()
                except Exception as e:
                    st.error(f"Error generating conclusion: {e}")

    with col_export:
        if st.button("📥 Download Workpaper (.docx)", use_container_width=True):
            try:
                buffer = export_workpaper(wp)
                st.download_button(
                    "⬇️ Save File",
                    data=buffer,
                    file_name=f"Workpaper_{wp.control_name.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d')}.docx",
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    use_container_width=True,
                )
            except Exception as e:
                st.error(f"Export error: {e}")

    st.markdown("---")

    # ── Render active phase ──
    if st.session_state.active_phase == TestingPhase.WALKTHROUGH:
        render_walkthrough_phase(wp)
    elif st.session_state.active_phase == TestingPhase.CDE:
        render_cde_phase(wp)
    elif st.session_state.active_phase == TestingPhase.COE:
        render_coe_phase(wp)
    elif st.session_state.active_phase == TestingPhase.DA:
        render_da_phase(wp)
    elif st.session_state.active_phase == TestingPhase.EXCEPTIONS:
        render_exceptions_phase(wp)
    else:
        render_workpaper_preview(wp)


# ─────────────────────────────────────────────
# PHASE: Walkthrough & RCM
# ─────────────────────────────────────────────

def render_walkthrough_phase(wp: ControlWorkpaper):
    st.markdown("## 📝 Control Walkthrough & RCM")

    # ── Upload transcripts ──
    st.markdown("### Upload Walkthrough Transcripts")
    st.caption("Upload one or more MS Teams transcript files (.txt, .vtt, .docx). Multiple walkthroughs will be merged into the RCM.")

    uploaded_files = st.file_uploader(
        "Upload transcript(s)",
        type=["txt", "vtt", "docx", "md"],
        accept_multiple_files=True,
        key=f"wt_upload_{wp.id}"
    )

    if uploaded_files:
        for uf in uploaded_files:
            # Check if already uploaded
            existing = [t.filename for t in wp.transcripts if t.phase == TestingPhase.WALKTHROUGH]
            if uf.name not in existing:
                content = uf.read().decode("utf-8", errors="replace")
                transcript = Transcript(
                    filename=uf.name,
                    content=content,
                    phase=TestingPhase.WALKTHROUGH,
                )
                wp.transcripts.append(transcript)

    # ── Show uploaded transcripts ──
    wt_transcripts = [t for t in wp.transcripts if t.phase == TestingPhase.WALKTHROUGH]
    if wt_transcripts:
        st.markdown("**Uploaded Transcripts:**")
        for t in wt_transcripts:
            with st.expander(f"📄 {t.filename} ({t.uploaded_at.strftime('%H:%M')})"):
                if t.summary:
                    st.markdown(f"**Summary:** {t.summary}")
                st.text_area("Content", t.content[:3000], height=150, disabled=True, key=f"tc_{t.id}")

    # ── Extract & Build RCM ──
    if wt_transcripts:
        col1, col2 = st.columns(2)
        with col1:
            if st.button("🤖 Extract from Transcripts & Build RCM", type="primary", use_container_width=True):
                with st.spinner("AI is reading transcripts and building the RCM..."):
                    try:
                        extractions = []
                        for t in wt_transcripts:
                            ext = extract_walkthrough(t.content, wp.control_name)
                            extractions.append(ext)
                            t.summary = summarize_transcript(t.content)

                        st.session_state.extractions[wp.control_name] = extractions
                        rcm_rows = build_rcm_from_extractions(extractions, wp.control_name, wp.audit_name)
                        wp.rcm = rcm_rows
                        wp.mark_phase_complete(TestingPhase.WALKTHROUGH)
                        wp.last_updated = datetime.now()
                        st.rerun()
                    except Exception as e:
                        st.error(f"Extraction error: {e}")

        with col2:
            if st.button("🔄 Re-extract (overwrite RCM)", use_container_width=True):
                wp.rcm = []
                wp.completed_phases = [p for p in wp.completed_phases if p != TestingPhase.WALKTHROUGH]
                st.rerun()

    # ── Editable RCM ──
    if wp.rcm:
        st.markdown("### Risk Control Matrix")
        st.caption("Edit any field directly. Changes are saved automatically.")

        for i, row in enumerate(wp.rcm):
            with st.expander(f"**{row.risk_id} / {row.control_id}** — {row.control_objective[:80]}...", expanded=(i == 0)):
                col1, col2 = st.columns(2)
                with col1:
                    row.risk_id = st.text_input("Risk ID", row.risk_id, key=f"rcm_rid_{wp.id}_{i}")
                    row.risk_description = st.text_area("Risk Description", row.risk_description, height=80, key=f"rcm_rdesc_{wp.id}_{i}")
                    row.risk_category = st.text_input("Risk Category", row.risk_category, key=f"rcm_rcat_{wp.id}_{i}")
                    row.control_id = st.text_input("Control ID", row.control_id, key=f"rcm_cid_{wp.id}_{i}")
                    row.control_objective = st.text_area("Control Objective", row.control_objective, height=80, key=f"rcm_cobj_{wp.id}_{i}")
                    row.control_description = st.text_area("Control Description", row.control_description, height=100, key=f"rcm_cdesc_{wp.id}_{i}")
                with col2:
                    row.control_owner = st.text_input("Control Owner", row.control_owner, key=f"rcm_cown_{wp.id}_{i}")
                    row.control_frequency = st.selectbox("Frequency", ["Daily", "Weekly", "Monthly", "Quarterly", "Annually", "Ad-hoc", "Event-driven"], index=0, key=f"rcm_freq_{wp.id}_{i}")
                    row.control_type = st.selectbox("Type", ["Preventive", "Detective", "Corrective"], index=0, key=f"rcm_type_{wp.id}_{i}")
                    row.control_nature = st.selectbox("Nature", ["Manual", "Automated", "IT-Dependent Manual"], index=0, key=f"rcm_nat_{wp.id}_{i}")
                    row.key_mitigating_activities = st.text_area("Mitigating Activities", row.key_mitigating_activities, height=80, key=f"rcm_mit_{wp.id}_{i}")
                    row.testing_approach = st.text_input("Testing Approach", row.testing_approach, key=f"rcm_test_{wp.id}_{i}")
                    row.evidence_required = st.text_area("Evidence Required", row.evidence_required, height=80, key=f"rcm_evid_{wp.id}_{i}")

    # ── Live preview ──
    st.markdown("---")
    render_workpaper_preview(wp)


# ─────────────────────────────────────────────
# PHASE: CDE
# ─────────────────────────────────────────────

def render_cde_phase(wp: ControlWorkpaper):
    st.markdown("## 🔍 Control Design Evaluation (CDE)")

    if not wp.rcm:
        st.warning("RCM not yet populated. Complete the Walkthrough phase first, or build the RCM manually.")

    # ── Upload CDE-specific transcripts ──
    st.markdown("### Upload CDE Meeting Notes / Transcripts")
    uploaded = st.file_uploader("Upload CDE transcript(s)", type=["txt", "vtt", "md"], accept_multiple_files=True, key=f"cde_upload_{wp.id}")
    if uploaded:
        for uf in uploaded:
            existing = [t.filename for t in wp.transcripts if t.phase == TestingPhase.CDE]
            if uf.name not in existing:
                content = uf.read().decode("utf-8", errors="replace")
                wp.transcripts.append(Transcript(filename=uf.name, content=content, phase=TestingPhase.CDE))

    additional = st.text_area("Additional auditor notes for CDE", placeholder="Any observations, concerns, or context for the AI...", key=f"cde_notes_{wp.id}")

    if st.button("🤖 Run CDE Analysis", type="primary", use_container_width=True):
        with st.spinner("AI is evaluating control design..."):
            try:
                result = analyze_cde(wp, additional)
                wp.cde_result = result
                wp.mark_phase_complete(TestingPhase.CDE)
                wp.last_updated = datetime.now()
                st.rerun()
            except Exception as e:
                st.error(f"CDE analysis error: {e}")

    # ── Editable CDE result ──
    if wp.cde_result:
        st.markdown("### CDE Results")
        st.caption("Edit any field below. Your changes are preserved.")
        cde = wp.cde_result

        cde.design_assessment = st.selectbox(
            "Design Assessment",
            ["Well Designed", "Needs Improvement", "Poorly Designed"],
            index=["Well Designed", "Needs Improvement", "Poorly Designed"].index(cde.design_assessment) if cde.design_assessment in ["Well Designed", "Needs Improvement", "Poorly Designed"] else 0,
            key=f"cde_assess_{wp.id}"
        )

        cde_strengths_str = st.text_area("Design Strengths (one per line)", "\n".join(cde.design_strengths), height=100, key=f"cde_str_{wp.id}")
        cde.design_strengths = [s.strip() for s in cde_strengths_str.split("\n") if s.strip()]

        cde_gaps_str = st.text_area("Design Gaps (one per line)", "\n".join(cde.design_gaps), height=100, key=f"cde_gaps_{wp.id}")
        cde.design_gaps = [g.strip() for g in cde_gaps_str.split("\n") if g.strip()]

        cde_comp_str = st.text_area("Compensating Controls (one per line)", "\n".join(cde.compensating_controls), height=80, key=f"cde_comp_{wp.id}")
        cde.compensating_controls = [c.strip() for c in cde_comp_str.split("\n") if c.strip()]

        cde.conclusion = st.text_area("CDE Conclusion", cde.conclusion, height=150, key=f"cde_conc_{wp.id}")
        cde.manually_edited = True

    st.markdown("---")
    render_workpaper_preview(wp)


# ─────────────────────────────────────────────
# PHASE: COE
# ─────────────────────────────────────────────

def render_coe_phase(wp: ControlWorkpaper):
    st.markdown("## ⚙️ Control Operating Effectiveness (COE)")

    if not wp.rcm:
        st.warning("RCM not yet populated. Complete the Walkthrough phase first, or build the RCM manually.")

    st.markdown("### Upload COE Meeting Notes / Transcripts")
    uploaded = st.file_uploader("Upload COE transcript(s)", type=["txt", "vtt", "md"], accept_multiple_files=True, key=f"coe_upload_{wp.id}")
    if uploaded:
        for uf in uploaded:
            existing = [t.filename for t in wp.transcripts if t.phase == TestingPhase.COE]
            if uf.name not in existing:
                content = uf.read().decode("utf-8", errors="replace")
                wp.transcripts.append(Transcript(filename=uf.name, content=content, phase=TestingPhase.COE))

    additional = st.text_area("Additional auditor notes for COE", placeholder="Sample details, testing observations...", key=f"coe_notes_{wp.id}")

    if st.button("🤖 Run COE Analysis", type="primary", use_container_width=True):
        with st.spinner("AI is evaluating operating effectiveness..."):
            try:
                result = analyze_coe(wp, additional)
                wp.coe_result = result
                wp.mark_phase_complete(TestingPhase.COE)
                wp.last_updated = datetime.now()
                st.rerun()
            except Exception as e:
                st.error(f"COE analysis error: {e}")

    if wp.coe_result:
        st.markdown("### COE Results")
        coe = wp.coe_result

        col1, col2 = st.columns(2)
        with col1:
            coe.sample_size = st.text_input("Sample Size", coe.sample_size, key=f"coe_ss_{wp.id}")
            coe.sample_period = st.text_input("Sample Period", coe.sample_period, key=f"coe_sp_{wp.id}")
            coe.deviations_found = st.number_input("Deviations Found", min_value=0, value=coe.deviations_found, key=f"coe_dev_{wp.id}")
        with col2:
            coe.testing_procedure = st.text_area("Testing Procedure", coe.testing_procedure, height=100, key=f"coe_proc_{wp.id}")
            coe.results_summary = st.text_area("Results Summary", coe.results_summary, height=100, key=f"coe_res_{wp.id}")

        dev_str = st.text_area("Deviation Details (one per line)", "\n".join(coe.deviation_details), height=80, key=f"coe_devd_{wp.id}")
        coe.deviation_details = [d.strip() for d in dev_str.split("\n") if d.strip()]

        coe.conclusion = st.text_area("COE Conclusion", coe.conclusion, height=150, key=f"coe_conc_{wp.id}")
        coe.manually_edited = True

    st.markdown("---")
    render_workpaper_preview(wp)


# ─────────────────────────────────────────────
# PHASE: DA
# ─────────────────────────────────────────────

def render_da_phase(wp: ControlWorkpaper):
    st.markdown("## 📊 Data Analytics (DA)")

    if not wp.rcm:
        st.warning("RCM not yet populated. Complete the Walkthrough phase first, or build the RCM manually.")

    st.markdown("### Upload DA Meeting Notes / Results")
    uploaded = st.file_uploader("Upload DA transcript(s)", type=["txt", "vtt", "md", "csv"], accept_multiple_files=True, key=f"da_upload_{wp.id}")
    if uploaded:
        for uf in uploaded:
            existing = [t.filename for t in wp.transcripts if t.phase == TestingPhase.DA]
            if uf.name not in existing:
                content = uf.read().decode("utf-8", errors="replace")
                wp.transcripts.append(Transcript(filename=uf.name, content=content, phase=TestingPhase.DA))

    additional = st.text_area("Additional DA context", placeholder="Data sources used, analytics performed, key findings...", key=f"da_notes_{wp.id}")

    if st.button("🤖 Run DA Analysis", type="primary", use_container_width=True):
        with st.spinner("AI is analyzing data analytics results..."):
            try:
                result = analyze_da(wp, additional)
                wp.da_result = result
                wp.mark_phase_complete(TestingPhase.DA)
                wp.last_updated = datetime.now()
                st.rerun()
            except Exception as e:
                st.error(f"DA analysis error: {e}")

    if wp.da_result:
        st.markdown("### DA Results")
        da = wp.da_result

        ds_str = st.text_area("Data Sources (one per line)", "\n".join(da.data_sources), height=80, key=f"da_ds_{wp.id}")
        da.data_sources = [s.strip() for s in ds_str.split("\n") if s.strip()]

        da.analytics_performed = st.text_area("Analytics Performed", da.analytics_performed, height=100, key=f"da_ap_{wp.id}")
        da.population_size = st.text_input("Population Size", da.population_size, key=f"da_pop_{wp.id}")
        da.exceptions_identified = st.number_input("Exceptions Identified", min_value=0, value=da.exceptions_identified, key=f"da_exc_{wp.id}")

        exc_str = st.text_area("Exception Details (one per line)", "\n".join(da.exception_details), height=80, key=f"da_excd_{wp.id}")
        da.exception_details = [e.strip() for e in exc_str.split("\n") if e.strip()]

        da.visualizations_notes = st.text_area("Visualization Notes", da.visualizations_notes, height=80, key=f"da_viz_{wp.id}")
        da.conclusion = st.text_area("DA Conclusion", da.conclusion, height=150, key=f"da_conc_{wp.id}")
        da.manually_edited = True

    st.markdown("---")
    render_workpaper_preview(wp)


# ─────────────────────────────────────────────
# PHASE: Exceptions
# ─────────────────────────────────────────────

def render_exceptions_phase(wp: ControlWorkpaper):
    st.markdown("## ⚠️ Exception Reporting")

    additional = st.text_area("Additional exception context", placeholder="Any specific exceptions observed during testing...", key=f"exc_notes_{wp.id}")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("🤖 AI: Identify Exceptions from Testing", type="primary", use_container_width=True):
            with st.spinner("AI is reviewing all test results for exceptions..."):
                try:
                    exceptions = identify_exceptions(wp, additional)
                    wp.exceptions = exceptions
                    wp.mark_phase_complete(TestingPhase.EXCEPTIONS)
                    wp.last_updated = datetime.now()
                    st.rerun()
                except Exception as e:
                    st.error(f"Exception identification error: {e}")
    with col2:
        if st.button("➕ Add Exception Manually", use_container_width=True):
            wp.exceptions.append(ExceptionRecord())
            st.rerun()

    # ── Editable exceptions ──
    if wp.exceptions:
        st.markdown("### Exceptions")
        for i, exc in enumerate(wp.exceptions):
            with st.expander(f"Exception {i+1}: {exc.description[:60] if exc.description else 'New Exception'}", expanded=True):
                exc.description = st.text_area("Description", exc.description, key=f"exc_desc_{wp.id}_{i}")
                col1, col2 = st.columns(2)
                with col1:
                    exc.severity = st.selectbox(
                        "Severity",
                        [s for s in ExceptionSeverity],
                        index=list(ExceptionSeverity).index(exc.severity),
                        format_func=lambda x: x.value,
                        key=f"exc_sev_{wp.id}_{i}"
                    )
                    exc.source_phase = st.selectbox(
                        "Source Phase",
                        [TestingPhase.CDE, TestingPhase.COE, TestingPhase.DA],
                        format_func=lambda x: x.value,
                        key=f"exc_src_{wp.id}_{i}"
                    )
                with col2:
                    exc.root_cause = st.text_area("Root Cause", exc.root_cause, height=80, key=f"exc_rc_{wp.id}_{i}")
                    exc.remediation_plan = st.text_area("Remediation Plan", exc.remediation_plan, height=80, key=f"exc_rem_{wp.id}_{i}")

                exc.management_response = st.text_area("Management Response", exc.management_response, height=80, key=f"exc_mgmt_{wp.id}_{i}")
                exc.target_date = st.text_input("Target Date", exc.target_date, key=f"exc_td_{wp.id}_{i}")

                if st.button(f"🗑️ Remove Exception {i+1}", key=f"exc_del_{wp.id}_{i}"):
                    wp.exceptions.pop(i)
                    st.rerun()

        if TestingPhase.EXCEPTIONS not in wp.completed_phases:
            wp.mark_phase_complete(TestingPhase.EXCEPTIONS)
    elif not wp.exceptions:
        st.info("No exceptions identified yet. Run AI analysis or add manually.")

    st.markdown("---")
    render_workpaper_preview(wp)


# ─────────────────────────────────────────────
# LIVE WORKPAPER PREVIEW
# ─────────────────────────────────────────────

def render_workpaper_preview(wp: ControlWorkpaper):
    st.markdown("## 📄 Live Workpaper Preview")
    st.caption("This updates after every phase. What you see here is what gets exported to .docx.")

    # ── Header ──
    st.markdown(f"**Audit:** {wp.audit_name}")
    st.markdown(f"**Control:** {wp.control_name}")
    st.markdown(f"**Status:** {effectiveness_badge(wp.effectiveness)}", unsafe_allow_html=True)
    st.markdown(f"**Progress:** {wp.progress_pct()}% — Phases completed: {', '.join([p.value for p in wp.completed_phases]) or 'None'}")

    # ── RCM Preview ──
    if wp.rcm:
        st.markdown("### Risk Control Matrix")
        for row in wp.rcm:
            st.markdown(f"""
| Field | Value |
|-------|-------|
| Risk | {row.risk_id}: {row.risk_description} |
| Control | {row.control_id}: {row.control_objective} |
| Owner | {row.control_owner} |
| Frequency / Type / Nature | {row.control_frequency} / {row.control_type} / {row.control_nature} |
| Testing Approach | {row.testing_approach} |
""")

    # ── CDE Preview ──
    if wp.cde_result:
        st.markdown("### CDE Result")
        st.markdown(f"**Assessment:** {wp.cde_result.design_assessment}")
        st.markdown(f"**Conclusion:** {wp.cde_result.conclusion}")
        if wp.cde_result.manually_edited:
            st.caption("✏️ Manually edited by auditor")

    # ── COE Preview ──
    if wp.coe_result:
        st.markdown("### COE Result")
        st.markdown(f"**Samples:** {wp.coe_result.sample_size} | **Deviations:** {wp.coe_result.deviations_found}")
        st.markdown(f"**Conclusion:** {wp.coe_result.conclusion}")
        if wp.coe_result.manually_edited:
            st.caption("✏️ Manually edited by auditor")

    # ── DA Preview ──
    if wp.da_result:
        st.markdown("### DA Result")
        st.markdown(f"**Population:** {wp.da_result.population_size} | **Exceptions:** {wp.da_result.exceptions_identified}")
        st.markdown(f"**Conclusion:** {wp.da_result.conclusion}")
        if wp.da_result.manually_edited:
            st.caption("✏️ Manually edited by auditor")

    # ── Exceptions Preview ──
    if wp.exceptions:
        st.markdown("### Exceptions")
        for i, exc in enumerate(wp.exceptions):
            st.markdown(f"**{i+1}.** [{exc.severity.value}] {exc.description}")

    # ── Conclusion Preview ──
    if wp.ai_conclusion_rationale:
        st.markdown("### AI Conclusion")
        st.markdown(f"**Effectiveness:** {wp.effectiveness.value}")
        st.markdown(wp.ai_conclusion_rationale)

    if wp.auditor_override_rationale:
        st.markdown("### Auditor Override")
        st.markdown(wp.auditor_override_rationale)

    # ── Auditor override section ──
    st.markdown("---")
    st.markdown("### ✏️ Auditor Override")
    override_eff = st.selectbox(
        "Override Effectiveness",
        [e for e in ControlEffectiveness],
        index=list(ControlEffectiveness).index(wp.effectiveness),
        format_func=lambda x: x.value,
        key=f"override_eff_{wp.id}"
    )
    override_rationale = st.text_area(
        "Override Rationale",
        wp.auditor_override_rationale,
        placeholder="Explain why you disagree with the AI conclusion...",
        key=f"override_rat_{wp.id}"
    )
    if st.button("Save Override", key=f"save_override_{wp.id}"):
        wp.effectiveness = override_eff
        wp.auditor_override_rationale = override_rationale
        wp.last_updated = datetime.now()
        st.success("Override saved.")
        st.rerun()


# ─────────────────────────────────────────────
# MAIN ROUTER
# ─────────────────────────────────────────────

def main():
    render_sidebar()

    if st.session_state.project is None:
        render_welcome()
        return

    wp = get_active_workpaper()
    if wp is None:
        render_welcome()
        st.info("👈 Select or add a control from the sidebar.")
        return

    render_control_dashboard(wp)


if __name__ == "__main__":
    main()
