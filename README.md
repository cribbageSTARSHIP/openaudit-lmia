# OpenAudit-LMIA

An open-source cryptographic verification and civic-audit framework for Canada's Temporary Foreign Worker Program (TFWP).

OpenAudit-LMIA connects job seekers to LMIA-pending vacancies on Canada's Job Bank, timestamps verifiable application receipts, models candidate qualification matches against NOC 2021 standards, and reconciles application volumes against ESDC's quarterly Open Data releases.

## Repository Layout
- `docs/RFC-001-Architecture.md`: Complete system specification and threat model.
- `services/scraper/`: Playwright / Python crawler for Job Bank LMIA postings.
- `services/verifier/`: SMTP transaction witness and cryptographic application proxy.
- `services/matcher/`: Local LLM / embedding pipeline for NOC rubric scoring.
- `services/reconciler/`: Open-data ingestion and ESDC Positive LMIA cross-referencing.
- `packages/browser-extension/`: Client witness for Job Bank "Direct Apply" submissions.

## Getting Started
See [CONTRIBUTING.md](CONTRIBUTING.md) and the [Architecture RFC](docs/RFC-001-Architecture.md) to set up your environment.
