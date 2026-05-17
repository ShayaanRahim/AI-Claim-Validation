# AI-Assisted Claim Validation

A backend system for healthcare insurance claim validation that combines deterministic rules, structured AI analysis, and human review. Built for environments where decisions must be traceable, failures must be safe, and automation must not outrun accountability.

This project uses **synthetic data only**. It is not HIPAA-certified and is not intended for production use with real protected health information.

---

## 1. Project Overview

### What it does

The system accepts structured healthcare claims, validates them through a fixed pipeline, and records every step for audit:

1. **Ingest** — Claims arrive as structured JSON (patient, coverage, care event, billing).
2. **Deterministic validation** — Hard rules check completeness, format, and logical consistency.
3. **AI validation** — An LLM provides advisory analysis with schema-enforced output.
4. **Safety layers** — Guardrails and hallucination checks constrain AI behavior.
5. **Human review** — Reviewers approve, reject, or escalate claims the system flags.

### Why it exists

Manual claim review is slow and expensive. Fully automated adjudication is risky in regulated healthcare workflows. This architecture explores a middle path: **automate what is certain, advise where judgment helps, and require humans where risk remains**.

### Healthcare workflow relevance

The pipeline mirrors how many payers and TPAs structure pre-adjudication:

- Eligibility and field completeness (deterministic)
- Policy and coding interpretation (AI advisory)
- Exception handling (human review queue)

---

## 2. System Architecture

```
                    ┌─────────────────┐
                    │  POST /claims   │
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │ Schema validation │
                    │   (Pydantic)      │
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │   PostgreSQL    │
                    │  status: DRAFT  │
                    └────────┬────────┘
                             │
              ┌──────────────▼──────────────┐
              │  Deterministic validation   │
              │  7 rules, confidence = 1.0  │
              └──────────────┬──────────────┘
                             │
                    PASS ────┴──── FAIL
                     │              │
              READY_FOR_AI    NEEDS_FIXES
                     │
              ┌──────▼──────┐
              │ AI validation│
              │ (structured) │
              └──────┬──────┘
                     │
         ┌───────────┼───────────┐
         │           │           │
    Guardrails  Hallucination  Hashing
         │           │           │
         └───────────┼───────────┘
                     │
              ┌──────▼──────┐
              │ Review queue │
              │  (human)     │
              └──────┬──────┘
                     │
              APPROVED / REJECTED / IN_REVIEW
```

### Layers

| Layer | Responsibility | Authority |
|-------|----------------|-----------|
| Deterministic | Field completeness, dates, coverage window | Hard fail — cannot be overridden by AI |
| AI | Discrepancy detection, coverage risk, rationale | Advisory only |
| Guardrails | Confidence thresholds, status overrides | Deterministic post-processing |
| Hallucination detector | Fabricated references, invented fields | Escalates to human review |
| Human review | Final approve/reject/escalate | Binding decision |

---

## 3. Guardrails and Safety Design

### Confidence thresholds

Configured via environment variables:

| Setting | Default | Behavior |
|---------|---------|----------|
| `AI_CONFIDENCE_THRESHOLD` | 0.75 | Below this → force human review |
| `AI_AUTO_APPROVE_THRESHOLD` | 0.95 | Approved below this → still requires human sign-off |

### Hallucination detection

Four deterministic checks run after AI validation:

1. **Unsupported references** — Citations to regulations, NCDs, or statutes not present in input
2. **Invented fields** — Issues referencing fields outside the claim schema
3. **Approval without evidence** — High-confidence approval when required data is empty
4. **Confidence/rationale mismatch** — High confidence paired with hedging language

When triggered: status downgraded to `needs_review`, human review forced, flags logged.

### Deterministic overrides

AI cannot approve a claim that failed deterministic validation. This is enforced in `validate_against_deterministic` and cannot be bypassed.

### Audit logging

Every significant event emits structured JSON logs via `app.audit` logger:

- `claim_id`, `validation_type`, `model_name`, `prompt_version`
- `confidence_score`, `input_hash`, `output_hash`
- `hallucination_risk`, `hallucination_flags`
- `request_id` (correlation), UTC `timestamp`

Secrets are scrubbed before logging.

---

## 4. Security Considerations

### Synthetic data only

All evaluation fixtures and examples use fabricated patient and policy identifiers. Do not load real PHI into this system.

### Role-based access

Authentication uses API keys via the `X-API-Key` header:

| Role | Key env var | Capabilities |
|------|-------------|--------------|
| `system` | `SYSTEM_API_KEY` | Create claims, run deterministic and AI validation |
| `reviewer` | `REVIEWER_API_KEY` | Review queue, submit decisions, view history |

Reviewers cannot create claims or trigger validation. System actors cannot submit reviews.

Set `AUTH_DISABLED=true` only for isolated test runs — never in production.

### Request tracing

Every request receives an `X-Request-ID` (client-supplied or auto-generated). This ID appears in logs and error responses for end-to-end trace reconstruction.

### Operational logging

- No API keys or secrets in logs
- Request timing logged (`method`, `path`, `status_code`, `duration_ms`)
- Standardized error bodies include `request_id`

---

## 5. Failure Modes

| Scenario | System behavior |
|----------|-----------------|
| OpenAI unavailable / timeout | Safe fallback: `needs_review`, confidence 0.0 |
| Malformed AI JSON | Retry (2 attempts), then fallback |
| Invalid AI schema | Rejected by Pydantic, fallback returned |
| Hallucination detected | Downgrade to `needs_review`, force human review |
| Low confidence approval | Guardrail changes status to `needs_review` |
| Deterministic FAIL + AI approved | Override to `needs_review` |
| Missing API key (caller) | HTTP 401 with structured error |
| Wrong role for endpoint | HTTP 403 |
| Database unavailable | `/health/ready` returns 500 |

The system **fails toward human review**, not toward silent approval.

---

## 6. Local Development

### Prerequisites

- Python 3.12+
- Docker and Docker Compose (recommended)
- OpenAI API key (for AI validation only)

### Quick start with Docker

```bash
cp .env.example .env
# Edit .env: set OPENAI_API_KEY and rotate API keys

docker compose up --build
```

API available at `http://localhost:8000`. Migrations run automatically on startup.

### Manual setup

```bash
pip install -r requirements-app.txt
createdb claim_validation
cp .env.example .env
# Configure DATABASE_URL and keys in .env

alembic upgrade head
uvicorn app.main:app --reload
```

### Run tests

```bash
# Auth disabled by default in test environment
pytest tests/ -v
# Expected: 192 passed
```

### API examples

```bash
# System role
export API_KEY="your-system-key"

curl -X POST http://localhost:8000/claims \
  -H "X-API-Key: $API_KEY" -H "Content-Type: application/json" \
  -d @eval/clean_claim.json

# Reviewer role
export REVIEW_KEY="your-reviewer-key"

curl http://localhost:8000/review/queue \
  -H "X-API-Key: $REVIEW_KEY"
```

### Health checks

| Endpoint | Purpose |
|----------|---------|
| `GET /health/live` | Process alive |
| `GET /health/ready` | Database connectivity |

---

## 7. API Reference

### Claims (system role)

- `POST /claims` — Create claim
- `GET /claims/{id}` — Retrieve claim (system or reviewer)

### Validation (system role)

- `POST /claims/{id}/validate/deterministic`
- `POST /claims/{id}/validate/ai`

### Review (reviewer role)

- `GET /review/queue`
- `POST /claims/{id}/review`
- `GET /claims/{id}/history`

---

## 8. Configuration

See `.env.example` for all variables:

```bash
ENVIRONMENT=development          # development | test | production
DEBUG=false
DATABASE_URL=postgresql://...
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4o-mini
AI_CONFIDENCE_THRESHOLD=0.75
AI_AUTO_APPROVE_THRESHOLD=0.95
AUTH_DISABLED=false
SYSTEM_API_KEY=...
REVIEWER_API_KEY=...
```

---

## 9. Project Structure

```
app/
├── api/              # Thin route handlers
├── core/             # Config, auth, audit logging, errors
├── dependencies/     # Role-based authorization
├── middleware/       # Request ID, timing
├── models/           # Pydantic schemas
├── services/         # Business logic
├── utils/            # Hashing utilities
└── db/               # SQLModel tables

eval/                 # Golden evaluation dataset (5 fixtures)
tests/
├── fixtures/         # AI output regression fixtures
└── test_*.py         # 192 tests

alembic/              # Database migrations
```

---

## 10. Test Coverage

| Area | Tests |
|------|-------|
| Deterministic validation | 25 |
| AI guardrails, models, prompt | 30 |
| AI schema enforcement | 19 |
| Hallucination safeguards | 20 |
| Confidence escalation | 19 |
| Human review | 42 |
| Authentication | 8 |
| Health, tracing, config, hashing | 18 |
| Audit logging | 7 |
| API integration | 7 |
| **Total** | **192** |

---

## 11. Future Improvements

- FHIR R4 ingestion adapter for claim payloads
- Payer-specific rule packs (configurable rule sets per plan)
- Clearinghouse integration (X12 837/835)
- Prior authorization workflow linkage
- Operational analytics (reviewer throughput, AI override rates)
- Embedding-based claim similarity for fraud patterns
- Policy document RAG for grounded AI reasoning (reducing hallucination risk at source)

---

## License

See [LICENSE](LICENSE).
