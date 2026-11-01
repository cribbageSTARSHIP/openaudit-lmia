# Contributing to OpenAudit-LMIA

Thank you for your interest in contributing to OpenAudit-LMIA! We are building an open-source cryptographic verification and audit framework to bring transparency and accountability to Canada's Temporary Foreign Worker Program (TFWP).

Whether you are a data engineer, backend developer, browser extension author, or policy researcher, your contributions are welcome.

---

## Core Ethical & Legal Boundaries

Because this project interacts with live employment data and regulatory compliance, all contributors must adhere to strict ethical guidelines:

1. **Zero Synthetic Spam:** The platform relies on real, verifiable application receipts from Canadian citizens and permanent residents. **Never** write scripts or bots that flood employers with fake, automated, or AI-generated junk resumes. Doing so compromises the integrity of the audit data and invalidates legal evidence.
2. **Privacy & PIPEDA Compliance:** Do not store, log, or commit unredacted Personally Identifiable Information (PII) or candidate resumes to public branches or central databases. All candidate data must be hashed or encrypted at rest.
3. **Respectful Crawling:** Scrapers targeting public job boards must use polite rate limits, respect robots.txt where applicable, and avoid degrading public infrastructure.

---

## Getting Started

1. **Fork and Clone the Repository**
   ```bash
   git clone https://github.com/cribbageSTARSHIP/openaudit-lmia.git
   cd openaudit-lmia
   ```
2. **Find an Issue:** Check the [GitHub Issues](https://github.com/cribbageSTARSHIP/openaudit-lmia/issues) tab. Look for issues labeled `good first issue` or comment on an existing issue to claim it.
3. **Join the Coordination Hub:** Hop into our Discord server to discuss architecture, ask questions, and coordinate with other developers.

---

## Submitting Pull Requests

1. Create a feature branch from `main`:
   ```bash
   git checkout -b feat/your-feature-name
   ```
2. Write clean, documented code with relevant unit tests where applicable.
3. Open a Pull Request against `main` with a clear description of the problem solved and how it was tested.

