# AI-Assisted Claim Validation System

A production-grade backend for healthcare insurance claim validation with deterministic rules, AI-powered advisory analysis, human review workflows, and anti-hallucination safeguards.

## Project Status

- **Day 3 Complete**: Deterministic validation engine
- **Day 4 Complete**: AI validation layer
- **Day 5 Complete**: Human review workflow
- **Day 6 Complete**: Evaluation, reliability, and anti-hallucination layer

**Tests**: 174/174 passing
**Code Quality**: No linter errors
**Production Ready**: Yes

---

## Core Features

### Deterministic Validation (Day 3)
- **Rule-based validation** with 7 explicit rules
- **100% confidence** — no uncertainty
- **Instant results** — no API calls
- **Complete audit trail** — every decision traceable
- **Status transitions**: DRAFT -> READY_FOR_AI / NEEDS_FIXES

### AI Validation (Day 4)
- **Advisory analysis** powered by GPT-4o-mini
- **Confidence scoring** (0.0-1.0)
- **Can say "unknown"** when uncertain
- **Safe fallback** if AI fails
- **6 guardrails** override unsafe decisions
- **Complete metadata** tracking

### Human Review Workflow (Day 5)
- **Review queue** — claims awaiting human decision, oldest first
- **Three decisions** — APPROVED, REJECTED, ESCALATED
- **Override protection** — rationale required when contradicting AI
- **Immutable audit trail** — every review recorded with before/after status
- **Full claim history** — validations + reviews in chronological order
- **Status lifecycle**: DRAFT -> READY_FOR_AI -> IN_REVIEW -> APPROVED / REJECTED

### Evaluation and Reliability Layer (Day 6)
- **Golden evaluation dataset** — 5 synthetic claim fixtures in `eval/`
- **Hallucination detection** — fabricated references, invented fields, approval-without-evidence, confidence/rationale mismatches
- **Auto-escalation** — hallucination risk automatically forces human review
- **Configurable thresholds** — `AI_CONFIDENCE_THRESHOLD` and `AI_AUTO_APPROVE_THRESHOLD`
- **Regression fixtures** — 9 stored AI output fixtures for schema compatibility testing
- **Audit logging assertions** — structured log output verified by tests
- **Deterministic stability** — same input verified to produce same output 100x

---

## Architecture

```
POST /claims
    |
Validate with Pydantic
    |
Store in PostgreSQL (status: DRAFT)
    |
[User triggers validation]
    |
1. Deterministic Validation
    |-- 7 rules (completeness, format, logic)
    |-- Confidence: 1.0
    +-- Status: PASS -> READY_FOR_AI / FAIL -> NEEDS_FIXES
    |
2. AI Validation (optional)
    |-- Call OpenAI with structured output
    |-- Apply 6 guardrails
    |-- Run hallucination detection
    |-- Confidence: 0.0-1.0
    +-- Status: approved/needs_review/rejected/unknown
    |
3. Human Review
    |-- Review queue (GET /review/queue)
    |-- Submit decision (APPROVED/REJECTED/ESCALATED)
    |-- Override rationale when contradicting AI
    +-- Immutable audit trail
    |
Final claim status: APPROVED / REJECTED / IN_REVIEW
```

---

## API Endpoints

### Claims
- `POST /claims` — Create a new claim
- `GET /claims/{claim_id}` — Retrieve claim with full history

### Validation
- `POST /claims/{claim_id}/validate/deterministic` — Run rule-based validation
- `POST /claims/{claim_id}/validate/ai` — Run AI-powered analysis (requires deterministic first)

### Human Review
- `GET /review/queue` — List claims awaiting human review (paginated)
- `POST /claims/{claim_id}/review` — Submit a human review decision
- `GET /claims/{claim_id}/history` — Full audit trail (validations + reviews)

### Example Flow

```bash
# 1. Create claim
curl -X POST http://localhost:8000/claims -H "Content-Type: application/json" -d '{...}'

# 2. Run deterministic validation
curl -X POST http://localhost:8000/claims/{id}/validate/deterministic

# 3. Run AI validation (optional, advisory only)
curl -X POST http://localhost:8000/claims/{id}/validate/ai

# 4. View review queue
curl http://localhost:8000/review/queue

# 5. Submit human review
curl -X POST http://localhost:8000/claims/{id}/review \
  -H "Content-Type: application/json" \
  -d '{"reviewer_id": "rev-1", "decision": "APPROVED", "notes": "Verified."}'

# 6. View complete audit history
curl http://localhost:8000/claims/{id}/history
```

---

## Guardrails (AI Safety)

7 deterministic rules that override AI:

1. Low confidence (< 0.75) -> force human review
2. Status "unknown" -> force human review
3. Status "rejected" -> force human review
4. Status "approved" + low confidence -> change to "needs_review"
5. High severity issues -> force human review
6. Deterministic FAIL + AI "approved" -> override to "needs_review"
7. Approved but below auto-approve threshold (0.95) -> force human review

**These cannot be bypassed by AI.**

---

## Hallucination Safeguards (Day 6)

4 deterministic checks that flag AI hallucination risk:

| Check | Description |
|---|---|
| Unsupported references | Flags citations to fabricated regulations, NCDs, statutes |
| Invented fields | Flags issues referencing fields not in the claim schema |
| Approval without evidence | Flags high-confidence approval when required data is missing |
| Confidence/rationale mismatch | Flags high confidence paired with hedging language |

When hallucination risk is detected:
- `needs_human_review` is forced to `true`
- Status "approved" is downgraded to "needs_review"
- Rationale is prefixed with `[HALLUCINATION GUARDRAIL]`
- Flags are logged for audit

---

## Test Coverage

| Suite | Count | Description |
|---|---|---|
| Deterministic rules (Day 3) | 9 | All validation rules |
| API endpoints (Day 3) | 7 | Claims CRUD, validation |
| AI guardrails (Day 4) | 10 | Safety rules |
| AI models (Day 4) | 10 | Schema validation |
| AI prompt (Day 4) | 10 | Prompt structure |
| Pydantic schemas (Day 3) | 1 | Schema test |
| Review models (Day 5) | 9 | Review request/response schemas |
| Review service (Day 5) | 20 | Queue, submit, history, edge cases |
| Review API (Day 5) | 13 | HTTP endpoints, error codes |
| Validation service (Day 6) | 16 | Golden-set, stability, edge cases |
| AI schema validation (Day 6) | 19 | Strict enforcement, regression fixtures |
| Hallucination safeguards (Day 6) | 20 | Detection + escalation |
| Confidence escalation (Day 6) | 19 | Thresholds, boundaries, overrides |
| Audit logging (Day 6) | 11 | Structured log assertions |
| **Total** | **174** | **100% passing** |

---

## Configuration

### Required
```bash
export OPENAI_API_KEY="your-api-key"   # For AI validation
```

### Optional (environment variables)
- `DATABASE_URL` — PostgreSQL connection string
- `AI_CONFIDENCE_THRESHOLD` — Default `0.75`, below this forces human review
- `AI_AUTO_APPROVE_THRESHOLD` — Default `0.95`, below this approved claims still need human sign-off

---

## Project Structure

```
app/
├── main.py                          # FastAPI app
├── core/
│   └── config.py                    # Settings (thresholds, DB URL)
├── api/                             # API endpoints
│   ├── claims.py                    # Claims CRUD
│   ├── validation.py                # Deterministic validation
│   ├── ai_validation.py             # AI validation + hallucination check
│   └── review.py                    # Human review workflow
├── models/                          # Pydantic schemas
│   ├── claim_models.py
│   ├── validation_models.py
│   ├── ai_validation_models.py
│   └── review_models.py
├── services/                        # Business logic
│   ├── ai_validator.py              # AI service
│   ├── review_service.py            # Review queue, decisions, history
│   ├── hallucination_detector.py    # Anti-hallucination checks
│   └── validation/
│       ├── rules.py                 # Deterministic rules
│       ├── engine.py                # Rule orchestration
│       ├── prompt.py                # LLM prompt template
│       └── guardrails.py            # Post-processing safety
└── db/                              # Database
    ├── models.py                    # SQLModel tables
    └── session.py                   # DB session

eval/                                # Golden evaluation dataset
├── clean_claim.json
├── missing_required_fields.json
├── conflicting_coverage.json
├── ambiguous_claim.json
└── malformed_claim.json

tests/                               # Test suite (174 tests)
├── fixtures/                        # Regression AI output fixtures
│   ├── valid_ai_output_*.json
│   ├── invalid_ai_output_*.json
│   └── hallucinated_ai_output.json
├── test_validation.py
├── test_validation_service.py
├── test_ai_guardrails.py
├── test_ai_models.py
├── test_ai_prompt.py
├── test_ai_schema_validation.py
├── test_confidence_escalation.py
├── test_hallucination_safeguards.py
├── test_logging.py
├── test_review_api.py
├── test_review_models.py
├── test_review_service.py
└── test_api.py

alembic/                             # Database migrations
```

---

## Quick Start

### Prerequisites
- Python 3.12+
- PostgreSQL

### Installation

```bash
pip install -r requirements.txt
createdb claim_validation
alembic upgrade head
export OPENAI_API_KEY="your-key"
uvicorn app.main:app --reload
```

### Run Tests

```bash
pytest tests/ -v
# Expected: 174 passed
```

---

## Key Design Principles

1. **Safety Over Speed** — AI can say "unknown" rather than guess
2. **Deterministic First** — Hard rules before AI analysis
3. **Advisory AI** — Never auto-approves without human review (below 0.95 threshold)
4. **Fail Gracefully** — Safe fallback if AI unavailable
5. **Complete Audit** — Every decision is traceable
6. **Schema Enforced** — No free-text, JSON only
7. **Anti-Hallucination** — Fabricated references, invented fields, and unsupported approvals are caught and escalated

---

## Technology Stack

- **Framework**: FastAPI
- **Database**: PostgreSQL + SQLModel
- **Validation**: Pydantic
- **AI**: OpenAI API (gpt-4o-mini)
- **Migrations**: Alembic
- **Testing**: Pytest

---

## License

See [LICENSE](LICENSE) file.

---

**Built with a focus on safety, auditability, reliability, and production readiness.**
