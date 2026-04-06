"""
UC-01 v2: AI Engine
Handles all LLM calls via Groq API for:
  - Walkthrough transcript extraction → RCM
  - CDE/COE/DA analysis from transcripts
  - Exception identification
  - Control effectiveness conclusion

Author: Ananya Aithal
"""

import json
import os
from groq import Groq
from models import (
    WalkthroughExtraction, RCMRow, CDEResult, COEResult,
    DAResult, ExceptionRecord, ControlWorkpaper, TestingPhase,
    ExceptionSeverity, ControlEffectiveness
)


def get_client() -> Groq:
    api_key = os.environ.get("GROQ_API_KEY", "")
    if not api_key:
        raise ValueError("GROQ_API_KEY environment variable not set.")
    return Groq(api_key=api_key)


def _call_llm(system_prompt: str, user_prompt: str, temperature: float = 0.2) -> str:
    """Core LLM call wrapper."""
    client = get_client()
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=temperature,
        max_tokens=4096,
    )
    return response.choices[0].message.content.strip()


def _parse_json_response(raw: str) -> dict:
    """Extract JSON from LLM response, handling markdown fences and control chars."""
    import re

    cleaned = raw.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        cleaned = "\n".join(lines)

    # First attempt: direct parse
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # Second attempt: extract JSON object/array from surrounding text
    start = cleaned.find("{")
    end = cleaned.rfind("}") + 1
    if start != -1 and end > start:
        json_str = cleaned[start:end]
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            pass

        # Third attempt: sanitize control characters inside string values
        # Replace literal newlines/tabs inside JSON strings with escaped versions
        sanitized = json_str
        # Remove control chars (0x00-0x1F) except \n, \r, \t
        sanitized = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', sanitized)

        # Fix unescaped newlines inside JSON string values
        # Strategy: replace actual newlines with \\n within quoted strings
        try:
            return json.loads(sanitized)
        except json.JSONDecodeError:
            pass

        # Fourth attempt: aggressive cleanup — replace all real newlines with spaces
        # then restore the JSON structure newlines
        oneline = sanitized.replace("\r\n", " ").replace("\n", " ").replace("\r", " ")
        # Collapse multiple spaces
        oneline = re.sub(r' {2,}', ' ', oneline)
        try:
            return json.loads(oneline)
        except json.JSONDecodeError:
            pass

        # Fifth attempt: use strict=False
        try:
            return json.loads(json_str, strict=False)
        except json.JSONDecodeError:
            pass

        try:
            return json.loads(sanitized, strict=False)
        except json.JSONDecodeError:
            pass

    raise ValueError(f"Could not parse JSON from LLM response:\n{raw[:500]}")


# ─────────────────────────────────────────────
# 1. WALKTHROUGH → RCM EXTRACTION
# ─────────────────────────────────────────────

WALKTHROUGH_SYSTEM_PROMPT = """You are an expert internal auditor at a global bank. 
You are analyzing a control walkthrough transcript from a Microsoft Teams meeting.

Extract structured audit information from the transcript. Be thorough and precise.
Respond ONLY with a JSON object (no markdown, no preamble) with these fields:

{
  "control_objective": "What the control aims to achieve",
  "control_description": "Detailed description of how the control operates",
  "control_owner": "Name/role of the control owner",
  "control_frequency": "Daily/Weekly/Monthly/Quarterly/Ad-hoc",
  "control_type": "Preventive/Detective/Corrective",
  "control_nature": "Manual/Automated/IT-Dependent Manual",
  "risk_description": "What risk this control mitigates",
  "risk_category": "Operational/Financial/Compliance/Technology/Regulatory",
  "key_mitigating_activities": ["activity 1", "activity 2"],
  "systems_applications": ["system 1", "system 2"],
  "evidence_expected": ["evidence 1", "evidence 2"],
  "walkthrough_notes": "Key observations from the walkthrough",
  "confidence_score": 0.85
}

If information is not available in the transcript, use empty string or empty list.
The confidence_score should reflect how much of the control information was clearly 
stated vs inferred (1.0 = everything explicit, 0.5 = heavily inferred)."""


def extract_walkthrough(transcript_text: str, control_name: str) -> WalkthroughExtraction:
    """Extract structured audit data from a walkthrough transcript."""
    user_prompt = f"""Control being reviewed: {control_name}

Transcript:
---
{transcript_text}
---

Extract all relevant audit information from this walkthrough transcript."""

    raw = _call_llm(WALKTHROUGH_SYSTEM_PROMPT, user_prompt)
    data = _parse_json_response(raw)
    return WalkthroughExtraction(**data)


def build_rcm_from_extractions(
    extractions: list[WalkthroughExtraction],
    control_name: str,
    audit_name: str
) -> list[RCMRow]:
    """Merge multiple walkthrough extractions into RCM rows."""
    system_prompt = """You are an expert internal auditor building a Risk Control Matrix (RCM).
Given multiple walkthrough extractions for the same control, synthesize them into
one or more RCM rows. Each row should represent a distinct risk-control pair.

Respond ONLY with a JSON array of objects, each with these fields:
{
  "risk_id": "R-001",
  "risk_description": "...",
  "risk_category": "...",
  "control_id": "C-001",
  "control_objective": "...",
  "control_description": "...",
  "control_owner": "...",
  "control_frequency": "...",
  "control_type": "...",
  "control_nature": "...",
  "key_mitigating_activities": "comma separated list",
  "systems_applications": "comma separated list",
  "testing_approach": "CDE, COE, DA or combination",
  "evidence_required": "comma separated list"
}"""

    extractions_text = "\n\n".join([
        f"--- Extraction {i+1} ---\n{e.model_dump_json(indent=2)}"
        for i, e in enumerate(extractions)
    ])

    user_prompt = f"""Audit: {audit_name}
Control: {control_name}

Walkthrough Extractions:
{extractions_text}

Build the RCM rows for this control."""

    raw = _call_llm(system_prompt, user_prompt)
    # Handle both array and object responses
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        cleaned = "\n".join(lines)

    try:
        data = json.loads(cleaned, strict=False)
    except json.JSONDecodeError:
        start = cleaned.find("[")
        end = cleaned.rfind("]") + 1
        if start != -1 and end > start:
            try:
                data = json.loads(cleaned[start:end], strict=False)
            except json.JSONDecodeError:
                data = [_parse_json_response(cleaned)]
        else:
            data = [_parse_json_response(cleaned)]

    if isinstance(data, dict):
        data = [data]

    return [RCMRow(**row) for row in data]


# ─────────────────────────────────────────────
# 2. CDE ANALYSIS
# ─────────────────────────────────────────────

def analyze_cde(workpaper: ControlWorkpaper, additional_context: str = "") -> CDEResult:
    """Analyze Control Design Evaluation based on RCM and any CDE transcripts."""
    system_prompt = """You are an expert internal auditor performing Control Design Evaluation (CDE).
Assess whether the control is well-designed to mitigate the identified risks.

Respond ONLY with a JSON object:
{
  "design_assessment": "Well Designed / Needs Improvement / Poorly Designed",
  "design_gaps": ["gap 1", "gap 2"],
  "design_strengths": ["strength 1", "strength 2"],
  "compensating_controls": ["compensating control if any"],
  "conclusion": "CDE conclusion paragraph"
}"""

    rcm_text = "\n".join([r.model_dump_json(indent=2) for r in workpaper.rcm])
    cde_transcripts = "\n\n".join([
        t.content for t in workpaper.transcripts
        if t.phase == TestingPhase.CDE
    ])

    user_prompt = f"""Control: {workpaper.control_name}
Audit: {workpaper.audit_name}

RCM:
{rcm_text}

CDE-related transcripts/notes:
{cde_transcripts if cde_transcripts else 'No specific CDE transcripts uploaded.'}

Additional context from auditor:
{additional_context if additional_context else 'None provided.'}

Perform the CDE assessment."""

    raw = _call_llm(system_prompt, user_prompt)
    data = _parse_json_response(raw)
    return CDEResult(**data, ai_generated=True)


# ─────────────────────────────────────────────
# 3. COE ANALYSIS
# ─────────────────────────────────────────────

def analyze_coe(workpaper: ControlWorkpaper, additional_context: str = "") -> COEResult:
    """Analyze Control Operating Effectiveness."""
    system_prompt = """You are an expert internal auditor assessing Control Operating Effectiveness (COE).
Based on the RCM and any testing evidence, evaluate whether the control is operating effectively.

Respond ONLY with a JSON object:
{
  "sample_size": "e.g., 25 samples",
  "sample_period": "e.g., Q1 2026",
  "testing_procedure": "Description of testing steps",
  "results_summary": "Summary of testing results",
  "deviations_found": 0,
  "deviation_details": ["detail if any"],
  "conclusion": "COE conclusion paragraph"
}"""

    rcm_text = "\n".join([r.model_dump_json(indent=2) for r in workpaper.rcm])
    coe_transcripts = "\n\n".join([
        t.content for t in workpaper.transcripts
        if t.phase == TestingPhase.COE
    ])

    user_prompt = f"""Control: {workpaper.control_name}
Audit: {workpaper.audit_name}

RCM:
{rcm_text}

COE-related transcripts/notes:
{coe_transcripts if coe_transcripts else 'No specific COE transcripts uploaded.'}

Additional context from auditor:
{additional_context if additional_context else 'None provided.'}

Perform the COE assessment. If sample details are not provided, suggest appropriate 
sampling based on the control frequency and nature."""

    raw = _call_llm(system_prompt, user_prompt)
    data = _parse_json_response(raw)
    return COEResult(**data, ai_generated=True)


# ─────────────────────────────────────────────
# 4. DA ANALYSIS
# ─────────────────────────────────────────────

def analyze_da(workpaper: ControlWorkpaper, additional_context: str = "") -> DAResult:
    """Analyze Data Analytics results."""
    system_prompt = """You are an expert internal auditor analyzing Data Analytics (DA) results.
Based on the control context and any DA evidence, document the analytics performed.

Respond ONLY with a JSON object:
{
  "data_sources": ["source 1", "source 2"],
  "analytics_performed": "Description of analytics procedures",
  "population_size": "e.g., 15,000 records",
  "exceptions_identified": 0,
  "exception_details": ["detail if any"],
  "visualizations_notes": "Notes on visualizations or dashboards produced",
  "conclusion": "DA conclusion paragraph"
}"""

    rcm_text = "\n".join([r.model_dump_json(indent=2) for r in workpaper.rcm])
    da_transcripts = "\n\n".join([
        t.content for t in workpaper.transcripts
        if t.phase == TestingPhase.DA
    ])

    user_prompt = f"""Control: {workpaper.control_name}
Audit: {workpaper.audit_name}

RCM:
{rcm_text}

DA-related transcripts/notes:
{da_transcripts if da_transcripts else 'No specific DA transcripts uploaded.'}

Additional context from auditor:
{additional_context if additional_context else 'None provided.'}

Document the DA assessment. If specific data is not provided, suggest appropriate 
data analytics procedures based on the control type."""

    raw = _call_llm(system_prompt, user_prompt)
    data = _parse_json_response(raw)
    return DAResult(**data, ai_generated=True)


# ─────────────────────────────────────────────
# 5. EXCEPTION IDENTIFICATION
# ─────────────────────────────────────────────

def identify_exceptions(workpaper: ControlWorkpaper, additional_context: str = "") -> list[ExceptionRecord]:
    """Identify exceptions from all testing results."""
    system_prompt = """You are an expert internal auditor identifying exceptions/findings.
Based on all testing results (CDE, COE, DA), identify any exceptions or control failures.

Respond ONLY with a JSON array of exception objects:
[
  {
    "source_phase": "CDE Testing / COE Testing / Data Analytics",
    "description": "What the exception is",
    "severity": "Low / Medium / High / Critical",
    "root_cause": "Why it happened",
    "management_response": "Suggested management response",
    "remediation_plan": "What should be done",
    "target_date": "Suggested remediation timeline"
  }
]

If no exceptions are found, return an empty array: []"""

    context_parts = [f"Control: {workpaper.control_name}", f"Audit: {workpaper.audit_name}"]

    if workpaper.cde_result:
        context_parts.append(f"CDE Result:\n{workpaper.cde_result.model_dump_json(indent=2)}")
    if workpaper.coe_result:
        context_parts.append(f"COE Result:\n{workpaper.coe_result.model_dump_json(indent=2)}")
    if workpaper.da_result:
        context_parts.append(f"DA Result:\n{workpaper.da_result.model_dump_json(indent=2)}")

    if additional_context:
        context_parts.append(f"Additional auditor notes:\n{additional_context}")

    user_prompt = "\n\n".join(context_parts)

    raw = _call_llm(system_prompt, user_prompt)
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        cleaned = "\n".join(lines)

    try:
        data = json.loads(cleaned, strict=False)
    except json.JSONDecodeError:
        start = cleaned.find("[")
        end = cleaned.rfind("]") + 1
        if start != -1 and end > start:
            try:
                data = json.loads(cleaned[start:end], strict=False)
            except json.JSONDecodeError:
                data = []
        else:
            data = []

    if isinstance(data, dict):
        data = [data]

    exceptions = []
    for exc in data:
        # Map the source_phase string to enum
        phase_map = {
            "CDE Testing": TestingPhase.CDE,
            "COE Testing": TestingPhase.COE,
            "Data Analytics": TestingPhase.DA,
        }
        phase_str = exc.get("source_phase", "CDE Testing")
        exc["source_phase"] = phase_map.get(phase_str, TestingPhase.CDE)

        sev_str = exc.get("severity", "Medium")
        try:
            exc["severity"] = ExceptionSeverity(sev_str)
        except ValueError:
            exc["severity"] = ExceptionSeverity.MEDIUM

        exceptions.append(ExceptionRecord(**exc, ai_generated=True))

    return exceptions


# ─────────────────────────────────────────────
# 6. OVERALL CONCLUSION
# ─────────────────────────────────────────────

def generate_conclusion(workpaper: ControlWorkpaper) -> tuple[ControlEffectiveness, str]:
    """Generate overall control effectiveness conclusion."""
    system_prompt = """You are an expert internal auditor making a final control effectiveness determination.
Based on all available evidence (RCM, CDE, COE, DA, exceptions), conclude whether the 
control is Effective, Partially Effective, or Ineffective.

Respond ONLY with a JSON object:
{
  "effectiveness": "Effective / Partially Effective / Ineffective",
  "rationale": "Detailed rationale for the conclusion (2-3 paragraphs)"
}

Consider:
- CDE: Is the control well designed?
- COE: Is it operating as intended?
- DA: Do analytics support the control's effectiveness?
- Exceptions: How many, how severe?
- Overall: Does the control adequately mitigate the identified risks?"""

    context_parts = [
        f"Control: {workpaper.control_name}",
        f"Audit: {workpaper.audit_name}",
        f"Completed phases: {[p.value for p in workpaper.completed_phases]}",
    ]

    if workpaper.rcm:
        context_parts.append(f"RCM:\n{json.dumps([r.model_dump() for r in workpaper.rcm], indent=2)}")
    if workpaper.cde_result:
        context_parts.append(f"CDE Result:\n{workpaper.cde_result.model_dump_json(indent=2)}")
    if workpaper.coe_result:
        context_parts.append(f"COE Result:\n{workpaper.coe_result.model_dump_json(indent=2)}")
    if workpaper.da_result:
        context_parts.append(f"DA Result:\n{workpaper.da_result.model_dump_json(indent=2)}")
    if workpaper.exceptions:
        context_parts.append(f"Exceptions:\n{json.dumps([e.model_dump() for e in workpaper.exceptions], indent=2, default=str)}")

    user_prompt = "\n\n".join(context_parts)
    raw = _call_llm(system_prompt, user_prompt)
    data = _parse_json_response(raw)

    eff_str = data.get("effectiveness", "Not Assessed")
    eff_map = {
        "Effective": ControlEffectiveness.EFFECTIVE,
        "Partially Effective": ControlEffectiveness.PARTIALLY_EFFECTIVE,
        "Ineffective": ControlEffectiveness.INEFFECTIVE,
    }
    effectiveness = eff_map.get(eff_str, ControlEffectiveness.NOT_ASSESSED)
    rationale = data.get("rationale", "")

    return effectiveness, rationale


# ─────────────────────────────────────────────
# 7. TRANSCRIPT SUMMARIZER
# ─────────────────────────────────────────────

def summarize_transcript(transcript_text: str) -> str:
    """Generate a brief summary of a transcript."""
    system_prompt = "Summarize this audit meeting transcript in 3-5 bullet points. Be concise and focus on key decisions, findings, and action items. Respond with plain text, no JSON."
    return _call_llm(system_prompt, transcript_text[:8000], temperature=0.1)