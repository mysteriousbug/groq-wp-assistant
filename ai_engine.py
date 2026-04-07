"""
UC-01 v2: AI Engine (Groq API)
Handles all LLM calls:
  - Walkthrough + supporting docs → RCM extraction
  - AI-suggested CDE/COE/DA test procedures
  - CDE/COE/DA analysis
  - Exception identification
  - Overall conclusion

RCM columns match GIA standard:
  Process Ref, Process Title, Process Description,
  Risk Ref, Risk Title, Risk Description,
  Control Ref, Control Title, Control Description,
  Related Key Questions, CDE Required, COE Required,
  CDE or COE DA Required,
  CDE Test Procedures, COE Test Procedures, DA Test Procedure,
  Audit Team Member

Author: Ananya Aithal
"""

import json
import os
import re
from groq import Groq


def get_client() -> Groq:
    api_key = os.environ.get("GROQ_API_KEY", "")
    if not api_key:
        raise ValueError("GROQ_API_KEY environment variable not set.")
    return Groq(api_key=api_key)


def _call_llm(system_prompt: str, user_prompt: str, temperature: float = 0.2) -> str:
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
    """Extract JSON from LLM response with robust error handling."""
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        cleaned = "\n".join(lines)

    # Try direct parse with strict=False
    try:
        return json.loads(cleaned, strict=False)
    except json.JSONDecodeError:
        pass

    # Extract JSON object
    start = cleaned.find("{")
    end = cleaned.rfind("}") + 1
    if start != -1 and end > start:
        json_str = cleaned[start:end]
        try:
            return json.loads(json_str, strict=False)
        except json.JSONDecodeError:
            pass
        # Sanitize control chars
        sanitized = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', json_str)
        try:
            return json.loads(sanitized, strict=False)
        except json.JSONDecodeError:
            pass
        # Collapse newlines
        oneline = re.sub(r'\s+', ' ', sanitized)
        try:
            return json.loads(oneline, strict=False)
        except json.JSONDecodeError:
            pass

    raise ValueError(f"Could not parse JSON from LLM response:\n{raw[:500]}")


def _parse_json_array(raw: str) -> list:
    """Extract JSON array from LLM response."""
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        cleaned = "\n".join(lines)

    try:
        data = json.loads(cleaned, strict=False)
        if isinstance(data, list):
            return data
        return [data]
    except json.JSONDecodeError:
        pass

    # Find array
    start = cleaned.find("[")
    end = cleaned.rfind("]") + 1
    if start != -1 and end > start:
        try:
            return json.loads(cleaned[start:end], strict=False)
        except json.JSONDecodeError:
            pass

    # Fall back to object
    try:
        return [_parse_json_response(cleaned)]
    except ValueError:
        return []


# ─────────────────────────────────────────────
# 1. WALKTHROUGH + DOCS → RCM
# ─────────────────────────────────────────────

RCM_SYSTEM_PROMPT = """You are an expert internal auditor building a Risk Control Matrix (RCM).
Based on walkthrough transcripts and supporting documents (process docs, access matrices,
technical implementation docs, risk ratings, etc.), build the RCM.

Respond ONLY with a JSON array. Each object MUST have exactly these fields:

[
  {
    "process_ref": "PR-001",
    "process_title": "Title of the process",
    "process_description": "Description of the process",
    "risk_ref": "R-001",
    "risk_title": "Short risk title",
    "risk_description": "Detailed risk description",
    "control_ref": "C-001",
    "control_title": "Short control title",
    "control_description": "Detailed control description",
    "related_key_questions": "Key questions for testing",
    "cde_required": "Yes",
    "coe_required": "Yes",
    "cde_or_coe_da_required": "Yes/No",
    "cde_test_procedures": "Suggested CDE test procedures",
    "coe_test_procedures": "Suggested COE test procedures",
    "da_test_procedure": "Suggested DA test procedure",
    "audit_team_member": ""
  }
]

Be thorough. Create separate rows for distinct risk-control pairs.
For test procedures, suggest specific, actionable steps the auditor should take."""


def build_rcm(
    control_name: str,
    audit_name: str,
    transcript_texts: list[dict],
    supporting_doc_texts: list[dict],
) -> list[dict]:
    """
    Build RCM from walkthrough transcripts and supporting documents.

    Args:
        transcript_texts: list of {"filename": str, "content": str}
        supporting_doc_texts: list of {"filename": str, "doc_type": str, "content": str}
    """
    # Build context
    parts = [f"Audit: {audit_name}", f"Control: {control_name}", ""]

    if transcript_texts:
        parts.append("=== WALKTHROUGH TRANSCRIPTS ===")
        for t in transcript_texts:
            parts.append(f"\n--- {t['filename']} ---")
            parts.append(t["content"][:6000])  # Cap per transcript
        parts.append("")

    if supporting_doc_texts:
        parts.append("=== SUPPORTING DOCUMENTS ===")
        for d in supporting_doc_texts:
            parts.append(f"\n--- {d['filename']} (Type: {d['doc_type']}) ---")
            parts.append(d["content"][:4000])  # Cap per doc
        parts.append("")

    user_prompt = "\n".join(parts)
    raw = _call_llm(RCM_SYSTEM_PROMPT, user_prompt)
    return _parse_json_array(raw)


# ─────────────────────────────────────────────
# 2. AI-SUGGESTED TEST PROCEDURES
# ─────────────────────────────────────────────

def suggest_test_procedures(
    control_name: str,
    rcm_rows: list[dict],
    supporting_doc_summaries: list[str],
) -> dict:
    """
    Based on RCM and supporting docs, suggest detailed CDE, COE, and DA procedures.
    Returns a dict the auditor can review and override.
    """
    system_prompt = """You are an expert internal auditor suggesting test procedures.
Based on the RCM and supporting documents, suggest detailed test procedures for:
1. CDE (Control Design Evaluation) — how to assess if the control is well designed
2. COE (Control Operating Effectiveness) — how to test if it's operating as intended
3. DA (Data Analytics) — what data analytics could be performed

Respond ONLY with a JSON object:
{
  "cde_procedures": {
    "recommended": true,
    "rationale": "Why CDE is needed",
    "test_steps": [
      "Step 1: ...",
      "Step 2: ..."
    ],
    "evidence_to_request": ["Evidence 1", "Evidence 2"],
    "key_questions": ["Question 1", "Question 2"]
  },
  "coe_procedures": {
    "recommended": true,
    "rationale": "Why COE is needed",
    "test_steps": ["Step 1: ...", "Step 2: ..."],
    "suggested_sample_size": "25 samples",
    "suggested_sample_period": "Q1-Q2 2026",
    "evidence_to_request": ["Evidence 1"],
    "key_questions": ["Question 1"]
  },
  "da_procedures": {
    "recommended": true,
    "rationale": "Why DA is needed",
    "data_sources": ["Source 1", "Source 2"],
    "analytics_to_perform": ["Analytics 1", "Analytics 2"],
    "expected_population": "Description of population"
  }
}"""

    rcm_text = json.dumps(rcm_rows, indent=2)
    docs_text = "\n".join(supporting_doc_summaries) if supporting_doc_summaries else "No supporting documents."

    user_prompt = f"""Control: {control_name}

RCM:
{rcm_text}

Supporting Document Summaries:
{docs_text}

Suggest detailed test procedures."""

    raw = _call_llm(system_prompt, user_prompt)
    return _parse_json_response(raw)


# ─────────────────────────────────────────────
# 3. CDE ANALYSIS
# ─────────────────────────────────────────────

def analyze_cde(
    control_name: str,
    audit_name: str,
    rcm_rows: list[dict],
    transcript_texts: list[dict],
    supporting_doc_texts: list[dict],
    additional_context: str = ""
) -> dict:
    system_prompt = """You are an expert internal auditor performing Control Design Evaluation (CDE).
Respond ONLY with a JSON object:
{
  "design_assessment": "Well Designed / Needs Improvement / Poorly Designed",
  "design_gaps": ["gap 1", "gap 2"],
  "design_strengths": ["strength 1", "strength 2"],
  "compensating_controls": ["compensating control if any"],
  "conclusion": "CDE conclusion paragraph"
}"""

    parts = [f"Control: {control_name}", f"Audit: {audit_name}"]
    parts.append(f"RCM:\n{json.dumps(rcm_rows, indent=2)}")

    if transcript_texts:
        parts.append("CDE Transcripts:")
        for t in transcript_texts:
            parts.append(f"--- {t['filename']} ---\n{t['content'][:4000]}")

    if supporting_doc_texts:
        parts.append("Supporting Documents:")
        for d in supporting_doc_texts:
            parts.append(f"--- {d['filename']} ({d['doc_type']}) ---\n{d['content'][:3000]}")

    if additional_context:
        parts.append(f"Auditor notes: {additional_context}")

    raw = _call_llm(system_prompt, "\n\n".join(parts))
    result = _parse_json_response(raw)
    result["ai_generated"] = True
    result["manually_edited"] = False
    return result


# ─────────────────────────────────────────────
# 4. COE ANALYSIS
# ─────────────────────────────────────────────

def analyze_coe(
    control_name: str,
    audit_name: str,
    rcm_rows: list[dict],
    transcript_texts: list[dict],
    supporting_doc_texts: list[dict],
    additional_context: str = ""
) -> dict:
    system_prompt = """You are an expert internal auditor assessing Control Operating Effectiveness (COE).
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

    parts = [f"Control: {control_name}", f"Audit: {audit_name}"]
    parts.append(f"RCM:\n{json.dumps(rcm_rows, indent=2)}")

    if transcript_texts:
        parts.append("COE Transcripts:")
        for t in transcript_texts:
            parts.append(f"--- {t['filename']} ---\n{t['content'][:4000]}")

    if supporting_doc_texts:
        parts.append("Supporting Documents:")
        for d in supporting_doc_texts:
            parts.append(f"--- {d['filename']} ({d['doc_type']}) ---\n{d['content'][:3000]}")

    if additional_context:
        parts.append(f"Auditor notes: {additional_context}")

    raw = _call_llm(system_prompt, "\n\n".join(parts))
    result = _parse_json_response(raw)
    result["ai_generated"] = True
    result["manually_edited"] = False
    return result


# ─────────────────────────────────────────────
# 5. DA ANALYSIS
# ─────────────────────────────────────────────

def analyze_da(
    control_name: str,
    audit_name: str,
    rcm_rows: list[dict],
    transcript_texts: list[dict],
    supporting_doc_texts: list[dict],
    additional_context: str = ""
) -> dict:
    system_prompt = """You are an expert internal auditor analyzing Data Analytics (DA) results.
Respond ONLY with a JSON object:
{
  "data_sources": ["source 1", "source 2"],
  "analytics_performed": "Description of analytics procedures",
  "population_size": "e.g., 15,000 records",
  "exceptions_identified": 0,
  "exception_details": ["detail if any"],
  "visualizations_notes": "Notes on visualizations",
  "conclusion": "DA conclusion paragraph"
}"""

    parts = [f"Control: {control_name}", f"Audit: {audit_name}"]
    parts.append(f"RCM:\n{json.dumps(rcm_rows, indent=2)}")

    if transcript_texts:
        parts.append("DA Transcripts:")
        for t in transcript_texts:
            parts.append(f"--- {t['filename']} ---\n{t['content'][:4000]}")

    if supporting_doc_texts:
        parts.append("Supporting Documents:")
        for d in supporting_doc_texts:
            parts.append(f"--- {d['filename']} ({d['doc_type']}) ---\n{d['content'][:3000]}")

    if additional_context:
        parts.append(f"Auditor notes: {additional_context}")

    raw = _call_llm(system_prompt, "\n\n".join(parts))
    result = _parse_json_response(raw)
    result["ai_generated"] = True
    result["manually_edited"] = False
    return result


# ─────────────────────────────────────────────
# 6. EXCEPTION IDENTIFICATION
# ─────────────────────────────────────────────

def identify_exceptions(
    control_name: str,
    cde_result: dict = None,
    coe_result: dict = None,
    da_result: dict = None,
    additional_context: str = ""
) -> list[dict]:
    system_prompt = """You are an expert internal auditor identifying exceptions/findings.
Respond ONLY with a JSON array:
[
  {
    "source_phase": "CDE Testing / COE Testing / Data Analytics",
    "description": "What the exception is",
    "severity": "Low / Medium / High / Critical",
    "root_cause": "Why it happened",
    "management_response": "",
    "remediation_plan": "What should be done",
    "target_date": ""
  }
]
If no exceptions found, return: []"""

    parts = [f"Control: {control_name}"]
    if cde_result:
        parts.append(f"CDE Result:\n{json.dumps(cde_result, indent=2)}")
    if coe_result:
        parts.append(f"COE Result:\n{json.dumps(coe_result, indent=2)}")
    if da_result:
        parts.append(f"DA Result:\n{json.dumps(da_result, indent=2)}")
    if additional_context:
        parts.append(f"Auditor notes: {additional_context}")

    raw = _call_llm(system_prompt, "\n\n".join(parts))
    return _parse_json_array(raw)


# ─────────────────────────────────────────────
# 7. OVERALL CONCLUSION
# ─────────────────────────────────────────────

def generate_conclusion(
    control_name: str,
    rcm_rows: list[dict],
    cde_result: dict = None,
    coe_result: dict = None,
    da_result: dict = None,
    exceptions: list[dict] = None,
    completed_phases: list[str] = None,
) -> tuple[str, str]:
    """Returns (effectiveness_str, rationale_str)."""
    system_prompt = """You are an expert internal auditor making a final control effectiveness determination.
Respond ONLY with a JSON object:
{
  "effectiveness": "Effective / Partially Effective / Ineffective",
  "rationale": "Detailed rationale (2-3 paragraphs)"
}"""

    parts = [f"Control: {control_name}"]
    parts.append(f"Completed phases: {completed_phases or []}")
    if rcm_rows:
        parts.append(f"RCM:\n{json.dumps(rcm_rows, indent=2)}")
    if cde_result:
        parts.append(f"CDE:\n{json.dumps(cde_result, indent=2)}")
    if coe_result:
        parts.append(f"COE:\n{json.dumps(coe_result, indent=2)}")
    if da_result:
        parts.append(f"DA:\n{json.dumps(da_result, indent=2)}")
    if exceptions:
        parts.append(f"Exceptions:\n{json.dumps(exceptions, indent=2)}")

    raw = _call_llm(system_prompt, "\n\n".join(parts))
    data = _parse_json_response(raw)
    return data.get("effectiveness", "Not Assessed"), data.get("rationale", "")


# ─────────────────────────────────────────────
# 8. DOCUMENT SUMMARIZER
# ─────────────────────────────────────────────

def summarize_document(text: str, doc_type: str = "transcript") -> str:
    system_prompt = f"Summarize this {doc_type} in 3-5 bullet points. Focus on key decisions, findings, controls, and action items. Respond with plain text."
    return _call_llm(system_prompt, text[:8000], temperature=0.1)
