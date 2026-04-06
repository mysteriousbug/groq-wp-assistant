# UC-01 v2: Agentic AI Audit Workpaper Assistant

## Re-imagined Architecture — Multi-Control, Principle-Based Workflow

### What Changed from v1

| Aspect | v1 | v2 |
|--------|----|----|
| Controls | Single transcript → single workpaper | Multi-control project, each with its own workpaper |
| Transcripts | One per run | Multiple per control (multiple walkthroughs) |
| Workflow | Linear (walkthrough → CDE → COE → export) | **Non-linear** — any phase in any order |
| Live Preview | Only at end | After every single step |
| Editing | AI output only | Full manual editing of every field |
| RCM | Basic extraction | Multi-transcript merge into comprehensive RCM |
| Conclusion | Manual | AI-generated with auditor override |
| Backend | FastAPI + Streamlit (2 servers) | Streamlit only (simpler, single process) |
| LLM | Claude API | **Groq API** (Llama 3.3 70B) |

---

### Architecture

```
┌──────────────────────────────────────────────────────────┐
│                    Streamlit App (app.py)                 │
│                                                          │
│  ┌─────────────┐   ┌─────────────┐   ┌──────────────┐   │
│  │  Sidebar     │   │  Phase View  │   │  Live Preview│   │
│  │  - Project   │   │  - Upload    │   │  - RCM       │   │
│  │  - Controls  │   │  - AI Run    │   │  - CDE/COE   │   │
│  │  - Settings  │   │  - Edit      │   │  - DA/Exc    │   │
│  └─────────────┘   └──────┬───────┘   │  - Conclusion│   │
│                           │           └──────────────┘   │
└───────────────────────────┼──────────────────────────────┘
                            │
                    ┌───────▼────────┐
                    │  ai_engine.py  │
                    │  (Groq API)    │
                    │                │
                    │  - Extract WT  │
                    │  - Build RCM   │
                    │  - CDE/COE/DA  │
                    │  - Exceptions  │
                    │  - Conclusion  │
                    └───────┬────────┘
                            │
                    ┌───────▼────────┐
                    │  models.py     │
                    │  (Pydantic)    │
                    │                │
                    │  AuditProject  │
                    │  └─ Control    │
                    │     Workpaper  │
                    │     ├─ RCM     │
                    │     ├─ CDE     │
                    │     ├─ COE     │
                    │     ├─ DA      │
                    │     └─ Exc     │
                    └───────┬────────┘
                            │
                    ┌───────▼────────┐
                    │  exporter.py   │
                    │  (python-docx) │
                    │                │
                    │  → .docx       │
                    └────────────────┘
```

### Data Flow (Non-Linear)

```
                    ┌──────────────┐
                    │ Create Audit │
                    │   Project    │
                    └──────┬───────┘
                           │
                    ┌──────▼───────┐
                    │ Add Control  │ ← Repeat for each control
                    └──────┬───────┘
                           │
                    ┌──────▼───────┐
                    │  Upload WT   │ ← Multiple transcripts
                    │  Transcripts │
                    └──────┬───────┘
                           │
                    ┌──────▼───────┐
                    │  AI Extract  │
                    │  → Build RCM │
                    └──────┬───────┘
                           │
              ┌────────────┼────────────┐
              │            │            │
        ┌─────▼─────┐ ┌───▼───┐ ┌──────▼──────┐
        │    CDE    │ │  COE  │ │     DA      │  ← ANY ORDER
        └─────┬─────┘ └───┬───┘ └──────┬──────┘
              │            │            │
              └────────────┼────────────┘
                           │
                    ┌──────▼───────┐
                    │  Exceptions  │ ← AI identifies from all results
                    └──────┬───────┘
                           │
                    ┌──────▼───────┐
                    │ AI Conclude  │ ← Effective / Partially / Ineffective
                    │ + Override   │
                    └──────┬───────┘
                           │
                    ┌──────▼───────┐
                    │ Export .docx  │
                    └──────────────┘

     ★ Live workpaper preview available after EVERY step
     ★ Full manual editing at EVERY stage
```

---

### Setup

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Set Groq API key (or enter in the app sidebar)
export GROQ_API_KEY="gsk_your_key_here"

# 3. Run
streamlit run app.py
```

---

### File Structure

```
uc01-v2/
├── app.py              # Streamlit UI (main application)
├── models.py           # Pydantic data models
├── ai_engine.py        # Groq API integration (all LLM calls)
├── exporter.py         # .docx workpaper generator
├── requirements.txt    # Python dependencies
└── README.md           # This file
```

---

### Key Design Decisions

1. **Streamlit-only** — No separate FastAPI backend. For a single-user tool, Streamlit's
   session state handles everything. Simpler to deploy, debug, and iterate.

2. **Groq + Llama 3.3 70B** — Fast inference, free tier available for testing.
   Swap to Claude/GPT by changing `ai_engine.py` only.

3. **Principle-based workflow** — No hardcoded phase ordering. The `completed_phases`
   list tracks what's done, but doesn't enforce sequence.

4. **Everything editable** — Every AI-generated field is rendered as an editable
   `st.text_input` / `st.text_area`. The `manually_edited` flag tracks auditor changes.

5. **Live preview** — `render_workpaper_preview()` is called at the bottom of every
   phase view, so the auditor always sees the current state of the workpaper.

---

### Future Enhancements (v3)

- Persistent storage (SQLite or PostgreSQL)
- Multi-user with authentication
- Jira integration (auto-create RFI tickets from exceptions)
- Evidence attachment support (PDFs, screenshots)
- Audit trail / version history
- Batch processing across controls
- Dashboard view across all controls in an audit
