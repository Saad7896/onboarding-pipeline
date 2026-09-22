# Customer Data Onboarding & Integration Pipeline

An onboarding portal and data pipeline that takes messy customer data from
CRM, billing, and support systems and maps it safely into a canonical schema.

> Work in progress — built as a Forward Deployed Engineering portfolio project.

## The problem
Enterprise customers rarely send clean data. Schemas don't match, customer IDs
are inconsistent across systems, dates arrive in multiple formats, and the
documentation is incomplete. Onboarding a new customer often means weeks of
manual mapping and cleanup.

## What this system does
- **Ingests** data from file uploads (CSV/JSON) or a mock API
- **Profiles** the data: types, null rates, formats, sample values
- **Proposes a mapping** into a canonical schema using heuristics + an LLM,
  with confidence scores and explanations for uncertain fields
- **Requires human approval** — the model never silently rewrites customer data;
  every mapping is reviewable and versioned
- **Validates** records deterministically: types, required fields,
  referential integrity, duplicates, business rules
- **Routes failures** to an exception queue with a clear reason and suggested fix
- **Detects schema drift** and shows exactly which mappings broke
- **Idempotent API** — retries never create duplicate records

## Tech stack
Python · FastAPI · PostgreSQL · Docker · Next.js · Claude API

## Status
- [x] Project setup
- [ ] Ingestion + profiling
- [ ] Mapping proposer
- [ ] Review portal + mapping versioning
- [ ] Validation engine + exception queue
- [ ] Drift detection + idempotency
- [ ] Observability + deployment
- [ ] Evaluation report

## Author
Saad — [GitHub](https://github.com/Saad7896)