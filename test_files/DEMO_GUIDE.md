# UC-01 v2 — Demo Guide & Test Data

## Test Data Files

All test files simulate a **Database Services Audit** with realistic SCB-style content.

### Control 1: Database Privileged Access Management
| File | Phase | Upload To |
|------|-------|-----------|
| `WT1_DB_Privileged_Access_Mgmt.txt` | Walkthrough | Walkthrough & RCM phase |
| `WT2_DB_Privileged_Access_Monitoring.txt` | Walkthrough | Walkthrough & RCM phase (same control, 2nd transcript) |
| `CDE_DB_Privileged_Access.txt` | CDE | CDE Testing phase |
| `COE_DB_Privileged_Access.txt` | COE | COE Testing phase |
| `DA_DB_Privileged_Access.txt` | DA | Data Analytics phase |

### Control 2: Database Backup & Restoration
| File | Phase | Upload To |
|------|-------|-----------|
| `WT1_DB_Backup_Restoration.txt` | Walkthrough | Walkthrough & RCM phase |
| `CDE_DB_Backup_Restoration.txt` | CDE | CDE Testing phase |
| `COE_DB_Backup_Restoration.txt` | COE | COE Testing phase |

### Control 3: Database Configuration Management
| File | Phase | Upload To |
|------|-------|-----------|
| `WT1_DB_Configuration_Mgmt.txt` | Walkthrough | Walkthrough & RCM phase |

---

## Demo Script (15 minutes)

### Step 1: Create Project (30 seconds)
1. Enter Groq API key in sidebar
2. Create project: "Database Services Audit Q2 2026"

### Step 2: DB Privileged Access — Full Workflow (8 minutes)
1. Add control: "Database Privileged Access Management"
2. Click **Walkthrough & RCM** phase
3. Upload BOTH walkthrough files (WT1 + WT2)
4. Click "Extract from Transcripts & Build RCM"
5. **Show**: AI merged two transcripts into comprehensive RCM
6. **Show**: Edit an RCM field (e.g., change frequency)
7. **Show**: Live preview at bottom

8. Click **CDE Testing** phase (out of order is fine!)
9. Upload `CDE_DB_Privileged_Access.txt`
10. Click "Run CDE Analysis"
11. **Show**: AI identified design strengths and gaps
12. **Show**: Edit the conclusion text
13. **Show**: Live preview now shows RCM + CDE

14. Click **DA** phase (skipping COE — non-linear!)
15. Upload `DA_DB_Privileged_Access.txt`
16. Click "Run DA Analysis"
17. **Show**: Live preview shows RCM + CDE + DA

18. Click **COE Testing** phase
19. Upload `COE_DB_Privileged_Access.txt`
20. Click "Run COE Analysis"

21. Click **Exceptions** phase
22. Click "AI: Identify Exceptions from Testing"
23. **Show**: AI found exceptions from COE (SoD gap, late revocation) and DA (MongoDB gap, credential sharing)
24. **Show**: Edit exception severity, add management response

25. Click "Generate AI Conclusion"
26. **Show**: AI recommends "Partially Effective" with rationale
27. **Show**: Auditor override — change to "Effective" with rationale
28. Click "Download Workpaper (.docx)"

### Step 3: DB Backup — Partial Workflow (4 minutes)
1. Add control: "Database Backup & Restoration"
2. Upload walkthrough → Extract RCM
3. Upload CDE transcript → Run CDE
4. Upload COE transcript → Run COE
5. **Show**: No DA needed for this control
6. Generate conclusion
7. **Show**: AI says "Effective"
8. Download workpaper

### Step 4: DB Config Mgmt — Walkthrough Only (2 minutes)
1. Add control: "Database Configuration Management"
2. Upload walkthrough → Extract RCM
3. **Show**: Workpaper preview with just RCM populated
4. **Key message**: "Work in progress — I can come back and add testing later"

---

## Key Demo Points to Highlight

1. **Non-linear workflow**: Did DA before COE for Privileged Access — no issues
2. **Multi-transcript merge**: Two walkthroughs merged into one comprehensive RCM
3. **Full editability**: Changed RCM fields, edited CDE conclusion, modified exception severity
4. **Live preview**: Workpaper updates visible after every single step
5. **Auditor override**: AI suggested "Partially Effective" but auditor overrode to "Effective"
6. **Per-control workpapers**: Each control has its own independent workpaper
7. **Incremental progress**: Config Mgmt control shows partial work is fine

---

## Expected AI Outputs

### Privileged Access RCM (from 2 transcripts)
- Should identify 2-3 risk-control pairs covering:
  - Unauthorized privileged access risk → CyberArk PAM control
  - Undetected misuse risk → Monitoring & alerting control
  - Stale/excessive access risk → Recertification control

### Privileged Access Exceptions (from all testing)
- SoD gap in DBA approval workflow (from COE)
- Delayed contractor access revocation (from COE)
- MongoDB accounts not covered by CyberArk (from DA)
- Potential credential sharing (from DA)
- Unjustified after-hours session (from DA)

### Privileged Access Conclusion
- AI should recommend "Partially Effective" due to multiple exceptions
- This gives a good demo of the auditor override feature

### Backup & Restoration
- Clean COE, well-designed CDE → AI should conclude "Effective"
