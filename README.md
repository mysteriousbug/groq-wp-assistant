# UC-01 v2: Agentic AI Audit Workpaper Assistant (DB-Backed)

## What's New in This Version

| Feature | Before | Now |
|---------|--------|-----|
| Storage | Streamlit session (lost on reload) | **SQLite / Azure PostgreSQL / Azure SQL** |
| Documents | Transcripts only | **Transcripts + process docs, access matrices, tech impl docs, risk ratings, policies, evidence** |
| RCM | Basic extraction | **Full GIA RCM columns** (17 fields including suggested test procedures) |
| Test Procedures | Manual | **AI-suggested CDE/COE/DA procedures** from RCM + supporting docs |
| Workflow | Upload → AI runs → done | **Upload → AI suggests → Auditor reviews/overrides → Upload phase docs → AI analyzes → Auditor edits** |

## Architecture

```
Streamlit App (app.py)
    ├── Sidebar: Project/Control nav + Groq key
    ├── Phase Views: Walkthrough, CDE, COE, DA, Exceptions
    ├── Document Upload: Transcripts + Supporting docs
    ├── AI Suggestions: Test procedures from RCM
    └── Live Preview + Export
        │
        ├── ai_engine.py  ←→  Groq API (Llama 3.3 70B)
        ├── db_models.py  ←→  SQLAlchemy → SQLite / PostgreSQL / Azure SQL
        ├── exporter.py   ←→  templates/workpaper_template.docx
        └── uploads/      ←→  Local disk / Azure Blob (future)
```

## RCM Structure (17 columns)

```
Process Ref | Process Title | Process Description
Risk Ref | Risk Title | Risk Description
Control Ref | Control Title | Control Description
Related Key Questions
CDE Required | COE Required | CDE or COE DA Required
CDE Test Procedures | COE Test Procedures | DA Test Procedure
Audit Team Member
```

## Workflow

```
1. Create Project → Add Control
2. Walkthrough Phase:
   ├── Upload transcripts (MS Teams .txt/.vtt)
   ├── Upload supporting docs (process docs, access matrices, etc.)
   ├── AI builds RCM (17-column structure)
   ├── AI suggests CDE/COE/DA test procedures
   └── Auditor reviews & overrides RCM + suggestions
3. CDE Phase (or any order):
   ├── Upload CDE transcripts + docs
   ├── AI analyzes control design
   └── Auditor edits results
4. COE Phase:
   ├── Upload COE transcripts + docs
   ├── AI evaluates operating effectiveness
   └── Auditor edits results
5. DA Phase:
   ├── Upload DA transcripts + results
   ├── AI analyzes data analytics
   └── Auditor edits results
6. Exceptions:
   ├── AI identifies from all testing
   └── Auditor adds/edits/removes
7. Conclusion:
   ├── AI recommends effectiveness
   ├── Auditor can override
   └── Download .docx (template-driven)
```

## Setup

```bash
# 1. Install
pip install -r requirements.txt

# 2. Configure
cp .env.template .env
# Edit .env: set GROQ_API_KEY and DATABASE_URL

# 3. Run
streamlit run app.py
```

## Database Options

### SQLite (default — local dev)
```env
DATABASE_URL=sqlite:///uc01.db
```

### Azure PostgreSQL
```env
DATABASE_URL=postgresql://user:pass@server.postgres.database.azure.com:5432/uc01?sslmode=require
```
Uncomment `psycopg2-binary` in requirements.txt.

### Azure SQL
```env
DATABASE_URL=mssql+pyodbc://user:pass@server.database.windows.net:1433/uc01?driver=ODBC+Driver+18+for+SQL+Server
```
Uncomment `pyodbc` in requirements.txt.

## File Structure

```
uc01-v2-db/
├── app.py                 # Streamlit UI
├── db_models.py           # SQLAlchemy models (3 tables)
├── ai_engine.py           # Groq API (all LLM calls)
├── exporter.py            # Template-driven .docx export
├── requirements.txt
├── .env.template
├── templates/
│   └── workpaper_template.docx
├── uploads/               # Document storage (auto-created)
└── test_data/             # Demo transcripts
```
