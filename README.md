# SkillBridge · SIH26044 — Academia–Industry Collaboration Portal

> **Smart India Hackathon (SIH26044) MVP** — Portal for Academia–Industry Collaboration for Skill Mapping, Internships & Placement.

---

## 🌟 Executive Overview & Outcome-Feedback Recalibration Mechanism

SkillBridge implements a closed-loop platform connecting Students, Institutions (TPOs), Industry, and Ministry/Admin evaluators. Rather than treating skill mapping and placements as static databases, SkillBridge features an **Outcome-Feedback Recalibration Loop**:

> **How Recalibration Works (for Evaluators):**
> When an industry partner logs a placement or internship outcome (with a 1–5 performance rating) for a student, SkillBridge automatically adjusts the system-wide demand weight for every skill required by that job. High ratings (4–5★) or successful hires increase demand weights by +2% to +5%, while poor performance (1–2★) or dropped candidates decrease demand weights by -7%. These recalibrated demand weights immediately feed into the pgvector semantic matching engine—affecting future student match scores—and automatically update institution curriculum-gap signals and Ministry heatmap dashboards in real time.

---

## 🏗️ Architecture & Monorepo Structure

- `/frontend`: **Next.js 14 (App Router) + Tailwind CSS + Radix/shadcn UI components**
- `/backend`: **Python FastAPI + PostgreSQL with `pgvector` + `fastembed` (MiniLM sentence-transformers)**
- `/backend/migrations`: Database schema SQL with `pgvector` indexing & dynamic RBAC
- `/backend/seed`: Parameterized synthetic data generator for streams (CSE, ECE, etc.)
- `/backend/scripts/walkthrough.py`: End-to-end automated verification script (44 assertions)

---

## 🔑 Key Features & Technical Highlights

1. **Closed-Loop Workflow Across 4 Views**:
   - **Student View (`/student`)**: DPDP consent flow, PDF/text resume skill extraction into shared taxonomy, target role skill-gap analysis, personalized learning paths, semantic match recommendations with side-by-side explainability (matched vs. missing skills), and 1-click application submission.
   - **Institution / TPO Console (`/tpo`)**: Verification queue for co-signing student-claimed skills (`claimed` → `institution_cosigned` → `verified`), real-time curriculum-gap alerts by severity, student roster, and placement funnel analytics.
   - **Industry Console (`/industry`)**: Post job/internship descriptions with automated skill extraction, review applicant rankings with side-by-side skill-diff payloads, verify co-signed skills, and log outcomes with performance ratings (triggering live recalibration).
   - **Admin / Ministry Dashboard (`/admin`)**: Cross-institution skill-gap heatmap grid (Institutions × Roles), curriculum-gap alert matrix, dynamic database-driven RBAC editor (no redeploy needed), taxonomy weight management, and live 1-click stream re-seeding.

2. **Semantic Matching & Explainability**:
   - Local embeddings using `sentence-transformers` / `fastembed` + `pgvector` cosine similarity combined with demand-weighted taxonomy overlap.
   - Fallback to TF-IDF cosine similarity if embedding models are unavailable.
   - **Zero Keyword Overlap Proof**: Validates that profiles sharing zero raw string keywords but matching underlying taxonomy skills produce strong semantic scores.

3. **Dynamic Database-Driven RBAC**:
   - Permissions stored in `roles_permissions` table (JSONB permission sets), verified per request via JWT claims.
   - Editable live from the Admin UI without code modifications or server redeployment.

4. **Synthetic Data Provenance & DPDP Compliance**:
   - Explicit on-screen badges (`Synthetic demo data`) on all seeded data.
   - DPDP Act compliant consent banner and explicit API enforcement (`consent_given` required before storing resume or running matching).

---

## 🚀 Quickstart & Setup Instructions

### Prerequisites
- Python 3.10+
- Node.js 18+ & npm
- PostgreSQL 15+ with `pgvector` extension enabled (or run via Podman Compose)
- [Podman](https://podman.io/getting-started/installation) >= 4.x + `pip install podman-compose`

### 1. Database Setup
Launch PostgreSQL with `pgvector` via Podman:
```bash
podman-compose up -d
```
Alternatively, set your PostgreSQL connection string directly in `backend/.env`.

### 2. Backend Setup
```bash
cd backend
python -m venv .venv
# On Windows PowerShell:
.\.venv\Scripts\Activate.ps1
# On Linux/macOS:
source .venv/bin/activate

pip install -r requirements.txt

# Run migrations
python -m app.db.migrate

# Seed synthetic data (CSE & ECE streams)
python -m seed

# Start FastAPI server
uvicorn app.main:app --port 8000 --reload
```
The backend API will run at `http://localhost:8000`. API docs are available at `http://localhost:8000/docs`.

### 3. Frontend Setup
```bash
cd frontend
npm install
npm run dev
```
The frontend application will run at `http://localhost:3000`.

---

## 🧪 Automated Verification & Walkthrough Script

To execute the 44-step end-to-end automated test suite verifying auth, resume extraction, role-gap computation, semantic matching (with 0-overlap proof), verification state transitions, outcome logging recalibration, curriculum signal updates, and dynamic RBAC:

```bash
cd backend
python -m scripts.walkthrough
```

---

## ⚙️ Environment Variables

### Backend (`backend/.env`)
| Variable | Default Value | Description |
|---|---|---|
| `DATABASE_URL` | `postgresql://sih:sih@localhost:5433/sih26044` | PostgreSQL database connection string |
| `JWT_SECRET` | `sih26044-demo-secret-change-in-prod` | Secret key for signing auth JWTs |
| `JWT_EXPIRES_MINUTES` | `720` | Token expiration time in minutes |
| `CORS_ORIGINS` | `http://localhost:3000` | Allowed CORS origins for frontend |
| `EMBEDDING_PROVIDER` | `auto` | Embedding provider (`fastembed` or `tfidf` fallback) |

### Frontend (`frontend/.env.local`)
| Variable | Default Value | Description |
|---|---|---|
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | Base URL of the FastAPI backend |

---

## 👤 Demo Login Credentials

All demo accounts use password: `demo1234`

| Role | Email | Purpose |
|---|---|---|
| **Student** | `student.demo@sih.gov.in` | Standard student profile for resume upload & matching |
| **Student (Literal Twin)** | `student.demo2@sih.gov.in` | Proves semantic matching with 0 literal keyword overlap |
| **Institution (TPO)** | `tpo.cse.demo@sih.gov.in` | TPO dashboard for co-signing skills & viewing gaps |
| **Industry** | `industry.cse.demo@sih.gov.in` | Employer posting JDs, viewing applicants & logging outcomes |
| **Admin / Ministry** | `admin.demo@sih.gov.in` | Ministry heatmap, curriculum signals, RBAC & re-seed |

---

## 📜 License & SIH 2024 Context
Built for Smart India Hackathon Problem Statement SIH26044 (Portal for Academia–Industry Collaboration).
