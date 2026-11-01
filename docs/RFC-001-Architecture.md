# Project OpenAudit-LMIA: An Open-Source Cryptographic Verification & Audit Framework for Canada’s Temporary Foreign Worker Program

**Status:** Draft RFC / Call for Contributors  
**License:** MIT / GPLv3  
**Coordination:** [GitHub Repository](https://github.com/cribbageSTARSHIP/openaudit-lmia) | [Discord Community]

---

## 1. Abstract
Canada’s Temporary Foreign Worker Program (TFWP) requires employers to obtain a Labour Market Impact Assessment (LMIA) proving that no qualified Canadian citizens or permanent residents are available to fill a vacancy. While Employment and Social Development Canada (ESDC) mandates public job advertisements on the Government of Canada's Job Bank—including the mandatory use of Job Bank's "Direct Apply" feature alongside at least one secondary application method—compliance verification remains heavily reliant on self-reported employer records and post-hoc inspections. 

**OpenAudit-LMIA** is an open-source civic-tech framework designed to establish an independent, cryptographically verifiable audit trail of qualified domestic job applications. By scraping LMIA-flagged postings, routing and logging applicant submissions with verifiable delivery proofs, scoring candidate qualifications against National Occupational Classification (NOC) standards, and cross-referencing applicant volume against ESDC’s quarterly Positive LMIA Open Data releases, the platform creates empirical, machine-verifiable evidence of recruitment non-compliance.

---

## 2. The Regulatory Vulnerability (Problem Statement)
Under current ESDC regulations, employers applying for an LMIA must:
1. Advertise on the Government of Canada’s **Job Bank** for a minimum of **4 consecutive weeks** (High-Wage stream) or **8 consecutive weeks** (Low-Wage stream), keeping at least one ad live until an LMIA decision is issued.
2. Enable **Direct Apply** on Job Bank (and review submitted resumes within 21 days), invite matched candidates via **Job Match**, and provide at least one additional application channel (e.g., email or external portal).
3. Retain all recruitment records, resumes, and interview notes for **6 years** for potential ESDC compliance inspections.

### Where the Loop Fails:
* **Information Asymmetry:** Domestic job seekers rarely filter specifically for LMIA-pending postings, allowing questionable listings to run out their 4-to-8-week clock with minimal domestic visibility.
* **Unverifiable Secondary Channels & Black-Box Portals:** When applicants apply via listed emails or external Applicant Tracking Systems (ATS), they receive no cryptographic proof of receipt. Even within Job Bank's Direct Apply, individual applicants have no visibility into how many *other* qualified Canadians applied for the same role and were ignored.
* **Audit Bottlenecks:** ESDC compliance inspectors cannot manually audit every application. Without an external system aggregating applicant counts per Job Bank ID and comparing them against issued Positive LMIAs, bad-faith actors can claim "zero qualified domestic applicants" with low probability of immediate detection.

---

## 3. System Architecture & Core Modules

OpenAudit-LMIA is divided into four decoupled microservices/modules so contributors can work independently across Python, TypeScript/Rust, data engineering, and LLM tooling.

```text
+-----------------------------------------------------------------------+
|                        MODULE 1: INGESTION ENGINE                     |
|  Job Bank Scraper (Playwright/Python) -> Extracts LMIA-Flagged Jobs   |
|  Parses: Job Bank ID, NOC 2021/TEER, Wage, Operating Name, Location   |
+-----------------------------------+-----------------------------------+
                                    |
                                    v
+-----------------------------------------------------------------------+
|                   MODULE 2: COMPENDIUM & VERIFICATION                 |
|  Public Job Board + Verifiable Application Proxy                      |
|  - SMTP Relay (Message-ID + DSN Receipt + SHA-256 Resume Hash)        |
|  - Browser Extension (Logs Direct Apply & 3rd-Party ATS Submissions)  |
+-----------------------------------+-----------------------------------+
                                    |
                                    v
+-----------------------------------------------------------------------+
|                  MODULE 3: QUALIFICATION MATCHING (NLP)               |
|  Local LLM / Embedding Pipeline (Ollama / Local Inference)            |
|  Scores applicant skills against NOC 2021 duties & ad requirements    |
|  to preemptively refute "unqualified applicant" claims.               |
+-----------------------------------+-----------------------------------+
                                    |
                                    v
+-----------------------------------------------------------------------+
|                MODULE 4: RECONCILIATION & AUDIT DOSSIER               |
|  Cross-references Applicant DB with ESDC Quarterly Positive LMIA XLSX |
|  Generates automated Evidence Packages for ESDC Integrity / MPs       |
+-----------------------------------+-----------------------------------+
```

### Module 1: Ingestion & Normalization Engine (`/services/scraper`)
* **Target:** Government of Canada Job Bank (`jobbank.gc.ca`) listings carrying the TFWP/LMIA recruitment indicator.
* **Captured Schema:** Job Bank Reference ID, Business Legal & Operating Name, Street Address, NOC 2021 Code & TEER Category, Wage Rate, Posting Date, Expiry Date, and all listed Contact Vectors.
* **Tracking:** Polls active listings daily to measure exact advertising duration and detect premature takedowns prior to LMIA issuance.

### Module 2: The Verifiable Application Proxy (`/services/verifier`)
To prove a Canadian citizen or Permanent Resident applied, the system records immutable evidence across both application channels:
* **Channel A — Verifiable SMTP Relay:** When a candidate applies to an employer's listed email address through the platform, the outbound server captures the full SMTP transaction log (`250 OK` code from the receiving mail server), Delivery Status Notification (DSN), timestamp, and a `SHA-256` hash of the transmitted resume PDF.
* **Channel B — Direct Apply & Portal Witness (Browser Extension):** Because ESDC mandates Job Bank "Direct Apply" (and rules require employers to download and review Direct Apply resumes within 21 days), a lightweight Chromium/Firefox extension captures a signed DOM snapshot and confirmation receipt when a user clicks "Direct Apply" on Job Bank, logging the submission count against the Job Bank ID without storing raw PII on central servers.

### Module 3: NOC Qualification Verification (`/services/matcher`)
Employers frequently justify rejecting domestic applicants by claiming candidates did not meet specific education or experience requirements.
* Using local, privacy-preserving inference (via containerized local LLMs/embeddings), the system parses the applicant's resume against the 11 mandatory content elements of the job ad and the official **NOC 2021 TEER description**.
* Generates an anonymized **Qualification Attestation Checklist** confirming the candidate meets the stated wage, location, language, education, and experience thresholds.

### Module 4: Open-Data Reconciliation & Dossier Generator (`/services/reconciler`)
* **Automated Follow-Up:** At `T+14` and `T+21` days post-application (matching ESDC’s 21-day Direct Apply review rule), the system polls applicants to log whether the employer viewed the resume, requested an interview, or ghosted the candidate.
* **ESDC Dataset Joining:** Ingests ESDC’s quarterly *Positive LMIA Employers List* (`open.canada.ca` XLSX releases) and performs entity resolution (matching Operating Name, Census Subdivision/Location, NOC Code, and Approved Positions) against the historical scraped Job Bank dataset.
* **Evidence Output:** When an employer with $N$ verified, qualified domestic applicants (who received zero interview requests) appears on the Positive LMIA list—or while their 4-to-8-week window is still active—the system compiles a standardized PDF/JSON **Audit Dossier** for submission to Service Canada National Investigative Services and the local Member of Parliament.

---

## 4. Privacy, Legal & Security Architecture (PIPEDA Compliance)
1. **Zero-Knowledge / Minimal PII Retention:** Central servers do not need to store raw resumes permanently. A candidate's resume can be hashed (`SHA-256`) locally or in memory during transit; the candidate holds the original file and their cryptographic receipt key. If an ESDC investigator opens a file, verified applicants can opt in to release their unredacted records directly to Service Canada.
2. **Sybil & Bot Resistance:** To prevent bad actors from flooding employers with fake applications (which would discredit the platform's data), applicant accounts require verification confirming Canadian work authorization and real human identity before their application is counted in official audit metrics.
3. **Rate-Limiting & Ethical Scraping:** The ingestion engine respects polite crawling intervals and caches static job data to avoid degrading public infrastructure.

---

## 5. Call for Contributors (Open Roles)
We are recruiting technologists across the following domains:
* **Data & Scraping Engineers (Python / Playwright / PostgreSQL):** Maintaining resilient scrapers for Job Bank and entity-resolution pipelines for ESDC quarterly XLSX datasets.
* **Backend & Cryptography Engineers (Rust / Go / TypeScript):** Building the SMTP verification relay, cryptographic timestamping, and zero-PII receipt architecture.
* **Browser Extension Developers (TypeScript / WebExtensions API):** Building the client-side witness tool for Job Bank "Direct Apply" verification.
* **AI / NLP Engineers (Ollama / Local Embeddings / Python):** Designing deterministic rubric prompts to evaluate resume-to-NOC alignment without cloud API data leakage.
* **Civic Researchers & Legal/Policy Analysts:** Mapping ESDC compliance manuals, ATIP requests, and whistleblower reporting workflows.

