
## Claim Input ## 
{
  "claim_id": "string", 
  "patient": {
    "id": "string",
    "age": 32,
    "state": "CA"
  },
  "care_event": {
    "type": "doula_visit",
    "date": "2025-01-10",
    "duration_minutes": 90
  },
  "insurance": {
    "payer": "Example Health",
    "policy_id": "ABC123",
    "plan_type": "PPO"
  },
  "billing": {
    "procedure_code": "S9123",
    "units": 1,
    "amount": 150.00
  }
}

## Validation Output ##
{
  "status": "approved | rejected | needs_review",
  "confidence": 0.82,
  "issues": [
    {
      "field": "billing.procedure_code",
      "severity": "high",
      "message": "Procedure code not typically covered for plan type"
    }
  ],
  "needs_human_review": true,
  "rationale": "Coverage unclear for doula services under PPO plan",
  "source": "rules_engine | ai_model",
  "model_metadata": {
    "model": "gpt-5.2-mini",
    "prompt_version": "v1"
  }
}

