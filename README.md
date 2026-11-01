# OpenAudit-LMIA

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Docker Compose](https://img.shields.io/badge/Orchestration-Docker%20Compose-2496ED?logo=docker&logoColor=white)](docker-compose.yml)
[![PostgreSQL](https://img.shields.io/badge/Database-PostgreSQL%2016-336791?logo=postgresql&logoColor=white)](db/init.sql)
[![Python 3.12](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)](services/)
[![Local AI](https://img.shields.io/badge/AI-Ollama%20(Local%20Inference)-FB8C00)](services/matcher/)

> **Verifiable Accountability for Canada’s Temporary Foreign Worker Program (TFWP) via Cryptographic Audit Trails and Distributed Compute.**

---

## 1. The Vision

OpenAudit-LMIA is an open-source, civic-tech public watchdog platform designed to replace the government's self-reported "honour system" with verifiable data.

Under federal rules, Canada’s Temporary Foreign Worker Program (TFWP) is strictly an avenue of last resort when qualified domestic workers cannot be found. In practice, thousands of qualified Canadian citizens and permanent residents report submitting applications to Job Bank postings only to be met with complete silence. Meanwhile, employers self-report to Employment and Social Development Canada (ESDC) that *"no qualified Canadians applied"* and are granted Positive Labour Market Impact Assessments (LMIAs) to hire abroad.

Because the federal oversight model lacks closed-loop verification, lawmakers, journalists, and citizens only see self-reported compliance. **OpenAudit-LMIA fixes this by pairing ephemeral citizen application receipts with automated federal data reconciliation.**

---

## 2. End-to-End Operational Lifecycle

The system operates across five coordinated stages to verify applications, evaluate qualifications, link federal datasets, and surface non-compliance in real time:

```
[ Canadian Job Seeker ]
          │ (Resume + Job Bank URL)
          ▼
┌────────────────────────────────────────────────────────┐
│ Stage 1: Web Frontend & Zero-Knowledge Hashing         │
│  - Generates cryptographic SHA-256 receipt for user    │
│  - Raw resume text buffered strictly in ephemeral RAM  │
└─────────────────────────┬──────────────────────────────┘
                          │ Encrypted In-Memory Task Queue
                          ▼
┌────────────────────────────────────────────────────────┐
│ Stage 2: Scraper Service (services/scraper)            │
│  - Asynchronous Playwright captures Job Bank ad specs  │
│  - Extracts NOC code, employer, wage, location         │
│  - Upserts to central PostgreSQL (job_listings)        │
└─────────────────────────┬──────────────────────────────┘
                          │ Matches active Job ID
                          ▼
┌────────────────────────────────────────────────────────┐
│ Stage 3: Distributed Volunteer Compute (services/matcher)
│  - Volunteer nodes pull task from ephemeral RAM queue  │
│  - Local Ollama (qwen2.5:7b) evaluates qualification   │
│  - Deterministic JSON score generated (0–100%)         │
│  - Raw resume text instantly purged from memory        │
│  - Only SHA-256 hash & score saved to database         │
└─────────────────────────┬──────────────────────────────┘
                          │ Cross-referenced quarterly
                          ▼
┌────────────────────────────────────────────────────────┐
│ Stage 4: ESDC Reconciler Service (services/reconciler) │
│  - Ingests quarterly ESDC Positive LMIA approvals      │
│  - Entity resolution: RapidFuzz + 5-digit NOC match    │
│  - Links federal approval rows to Job Bank job_id      │
└─────────────────────────┬──────────────────────────────┘
                          │ Database trigger / VIEW
                          ▼
┌────────────────────────────────────────────────────────┐
│ Stage 5: Real-Time Audit Dashboard (view_lmia_audit_trail)
│  - Approved Positions > 0  AND  Verified Applicants > 0│
│  - Status flips: FLAGGED: Domestic Applicants Ignored  │
│  - Live public dashboard, data dossiers for MPs/Media  │
└────────────────────────────────────────────────────────┘
```

### Stage 1: Applicant Intake & Zero-Knowledge Privacy (Web Frontend)
* A job seeker visits the portal, inputs the Job Bank Posting ID/URL, and provides their resume text.
* The system computes a **cryptographic SHA-256 hash** of the resume, returning it to the user as an immutable proof-of-application receipt.
* **PIPEDA-Compliant Ephemeral Pipeline:** The raw resume is held strictly in volatile RAM. It is **never** written to disk or stored in the database.

### Stage 2: Job Bank Ingestion (`services/scraper`)
* Headless Chromium controlled via **Playwright** navigates to the listing.
* Extracts the `job_id`, `noc_code` (5-digit NOC 2021), `employer`, `location`, `wage`, and contact metadata before the employer can take the ad down.
* Data is stored in the PostgreSQL `job_listings` table.

### Stage 3: Distributed Volunteer Compute (`services/matcher`)
* **Preempting the "Unqualified" Excuse:** When employers defend bypassing domestic applicants, they standardly claim domestic applicants were unqualified. Local AI evaluates qualifications objectively.
* **Volunteer Compute Nodes:** Community volunteers run local worker containers connected to their own **Ollama** instances (`qwen2.5:7b` / `llama3.2:3b`).
* The worker pulls an ephemeral job from the RAM queue, feeds the resume and official NOC duties to Ollama, and receives structured JSON:
  ```json
  {
    "qualification_score": 92.5,
    "meets_minimum_requirements": true,
    "matching_skills": ["Crew Supervision", "Crop Harvesting", "Equipment Maintenance"],
    "missing_skills": [],
    "audit_summary": "Candidate possesses 7 years direct agricultural operations experience matching NOC 82030."
  }
  ```
* **Immediate Purge:** The raw resume text is wiped from RAM. Only `job_id`, `resume_hash`, `qualification_score`, and status are recorded.

### Stage 4: Federal Open-Data Reconciliation (`services/reconciler`)
* ESDC publishes quarterly CSVs of positive LMIA approvals, containing employer names, locations, and NOC codes—**but omitting Job Bank IDs**.
* `reconciler.py` reads the federal dataset, narrows candidates by 5-digit NOC, and performs fuzzy string matching using `rapidfuzz` (`fuzz.token_sort_ratio` with `utils.default_process` for casing/punctuation invariance).
* High-confidence matches ($\ge 85\%$) link the ESDC approval record directly to the scraped Job Bank record.

### Stage 5: Real-Time Public Flagging (`view_lmia_audit_trail`)
* PostgreSQL's relational engine joins approvals, postings, and applicant proofs:
  ```sql
  SELECT esdc_employer, approved_positions, domestic_applicants_recorded, audit_status 
  FROM view_lmia_audit_trail;
  ```
* If an employer obtained positive TFW approvals (`approved_positions > 0`) while verified, qualified domestic applicants logged applications (`domestic_applicants_recorded > 0`), the audit status automatically updates to:
  $$\mathbf{FLAGGED:\ Domestic\ Applicants\ Ignored}$$
* These results are pushed in real-time to the public-facing dashboard.

---

## 3. Technology Stack

| Layer | Technologies | Role in Pipeline |
| :--- | :--- | :--- |
| **Orchestration** | Docker, Docker Compose | Multi-container microservice runtime across host and volunteer nodes |
| **Database** | PostgreSQL 16 | Relational storage, indexing, and automated SQL audit views (`view_lmia_audit_trail`) |
| **Ingestion Engine** | Python 3.12, Playwright, Structlog | Asynchronous DOM extraction of LMIA-flagged Job Bank postings |
| **Entity Resolution** | Pandas, RapidFuzz 3.x | Cross-dataset fuzzy matching and 5-digit NOC normalization |
| **Local Inference** | Ollama (`qwen2.5:7b`), HTTPX, Pydantic | Distributed, local LLM evaluation of applicant skills against NOC standards |
| **Privacy Layer** | SHA-256, In-Memory Streams | Zero-knowledge receipts and volatile-RAM-only resume evaluation (PIPEDA compliant) |

---

## 4. Repository Structure

```
openaudit-lmia/
├── db/
│   └── init.sql                  # PostgreSQL schemas, foreign keys, and view_lmia_audit_trail
├── docker-compose.yml            # Multi-service container orchestration
├── docs/
│   └── RFC-001-Architecture.md  # Detailed technical RFC & architectural specifications
├── services/
│   ├── scraper/                  # Playwright Job Bank scraper service
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   └── scraper.py
│   ├── reconciler/               # RapidFuzz ESDC CSV reconciliation service
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   └── reconciler.py
│   ├── matcher/                  # Ollama-based resume qualification scoring service
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   └── matcher.py
│   └── verifier/                 # Cryptographic verification & hash generation
├── packages/
│   └── browser-extension/        # Future client-side 1-click application logging extension
├── CONTRIBUTING.md
├── LICENSE
└── README.md
```

---

## 5. Quickstart & Deployment

### Prerequisites
* Linux environment (tested on Arch Linux / CachyOS & Ubuntu 22.04+) or WSL2.
* Docker Engine 24+ and Docker Compose v2.
* Optional: NVIDIA GPU with CUDA drivers (for local Ollama acceleration).

### Setup & Execution
1. **Clone the repository:**
   ```bash
   git clone https://github.com/cribbageSTARSHIP/openaudit-lmia.git
   cd openaudit-lmia
   ```

2. **Configure Environment:**
   ```bash
   cp .env.example .env
   # Ensure DATABASE_URL and OLLAMA_HOST are configured
   ```

3. **Start the Database and Ollama Services:**
   ```bash
   docker compose up -d db ollama
   ```

4. **Pull the Inference Model into Ollama:**
   ```bash
   docker compose exec ollama ollama pull qwen2.5:7b
   ```

5. **Run the Job Bank Scraper:**
   ```bash
   docker compose run --rm scraper
   ```

6. **Reconcile ESDC Datasets:**
   ```bash
   docker compose run --rm reconciler data/esdc_sample.csv
   ```

7. **Inspect the Audit View in PostgreSQL:**
   ```bash
   docker compose exec db psql -U openaudit_user -d openaudit -c \
     "SELECT * FROM view_lmia_audit_trail;"
   ```

---

## 6. How You Can Help (Call for Contributors & Hardware)

OpenAudit-LMIA is transitioning from a bare-metal prototype to a scalable public platform. We are actively seeking:

### 1. Compute & Hardware Support (Urgent)
* **Workstation GPU Hardware:** We urgently need a donated or loaned high-VRAM workstation GPU (e.g., **NVIDIA RTX 3090, 4090, A5000, or A6000 with 24GB+ VRAM**) for our primary node to run continuous, un-quantized 14B/32B models.
* **Distributed Volunteer Node Operators:** Volunteers willing to run worker containers on their personal GPU-equipped machines to process ephemeral inference batches.

### 2. Software Contributors
* **FastAPI Backend Engineers:** Build the async REST API and Redis/Celery queue to handle ephemeral client uploads in volatile memory.
* **Frontend Engineers (React / Next.js / Tailwind):** Develop the public transparency dashboard where users can query employers, inspect audit statuses, and view flagged listings.
* **Data Engineers:** Assist with expanding scrapers across provincial nomination portals and automating federal open-data ETL pipelines.

### 3. Policy & Community Advocates
* Help share audit dossiers with parliamentary offices, labour unions, investigative journalists, and policy researchers to demand closed-loop accountability.

To contribute, see [CONTRIBUTING.md](CONTRIBUTING.md), browse open issues, or join our community discussions.

---

## License

This project is licensed under the [MIT License](LICENSE).