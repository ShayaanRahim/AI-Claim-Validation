# AI-Assisted Claim Validation Engine

A prototype backend system exploring how **deterministic validation, AI reasoning, and safety guardrails** can reduce manual review load in healthcare claim processing workflows.

This project implements a **safe AI-assisted validation pipeline** where deterministic rules enforce hard constraints and AI acts only as **decision support**, never as the final adjudicator.

---

## Overview

Healthcare claim validation involves semi-structured reasoning such as:

- eligibility verification
- policy interpretation
- billing code validation
- discrepancy detection

Because these tasks are difficult to fully automate with deterministic software, many claims require **manual review**, slowing processing and increasing operational costs.

This system explores a **hybrid architecture** where:

1. Deterministic rules catch obvious issues
2. AI highlights potential discrepancies
3. Guardrails enforce safety constraints
4. Humans review uncertain cases

---

## Architecture

```
Claim Submission
      │
      ▼
Structured Ingestion
(schema validation)
      │
      ▼
Deterministic Validation
(rule-based checks)
      │
      ▼
AI Validation Layer
(policy reasoning + discrepancy detection)
      │
      ▼
Guardrail System
(confidence thresholds + safety rules)
      │
      ▼
Human Review Queue
(approval / override)
```

Key principle:

> **AI assists decisions but never makes final decisions.**

---

## Features

### Deterministic Validation Engine

Rule-based validation ensures baseline correctness.

Current checks include:

- required field validation
- format validation
- logical consistency checks
- coverage period validation

Deterministic failures **cannot be overridden by AI**.

---

### AI Advisory Validation Layer

An LLM analyzes claims to identify:

- potential discrepancies
- policy reasoning context
- coverage likelihood
- explanations for flagged issues

Outputs are strictly enforced using **structured schemas** to prevent hallucinated responses.

---

### Safety Guardrails

The system includes multiple layers of safety:

- structured AI outputs
- retry logic
- timeout protection
- deterministic override rules
- confidence threshold escalation
- safe fallback responses

Low-confidence or ambiguous results automatically require **human review**.

---

### Full Audit Logging

Every validation event records:

- model name
- prompt version
- input hash
- confidence score
- full result payload

This ensures **traceability and reproducibility**.

---

## Current Prototype

Implemented components:

- FastAPI backend
- claim ingestion API
- deterministic validation engine (7 rules)
- AI advisory validation endpoint
- guardrail safety system
- PostgreSQL persistence
- full validation audit trail
- 47 automated tests

The system currently exposes the following endpoints:

```
POST /claims
GET /claims/{claim_id}
POST /claims/{claim_id}/validate/deterministic
POST /claims/{claim_id}/validate/ai
```

---

## Example Workflow

1. Claim submitted → stored as `DRAFT`
2. Deterministic validation runs
3. If rules pass → claim marked `READY_FOR_AI`
4. AI validation analyzes claim context
5. Guardrails enforce safety checks
6. Claims requiring review are escalated to humans

---

## Tech Stack

Backend
- FastAPI
- Python

Database
- PostgreSQL
- JSONB structured payloads

ORM / Schema
- SQLModel
- Pydantic

Testing
- Pytest

Infrastructure
- Docker
- Docker Compose

---

## Design Principles

**Deterministic First**

Hard validation rules run before any AI reasoning.

**AI is Advisory**

AI can recommend decisions but cannot finalize them.

**Fail Safely**

AI failures return safe fallback responses.

**Human in the Loop**

Low confidence results require human review.

**Full Auditability**

All validation decisions are logged.

---

## Possible Future Extensions

Potential directions for further development:

- policy retrieval system (RAG) over insurance documents
- claim similarity search using embeddings
- prior authorization prediction
- anomaly detection for fraud
- provider-facing explanations for claim issues

---

## Project Goal

This project explores how **AI-assisted validation architectures** could reduce manual claim review workload while preserving safety, traceability, and human oversight.

It is intended as a **technical exploration of a safe validation pipeline**, not a full claims adjudication system.

---

## License

MIT License
