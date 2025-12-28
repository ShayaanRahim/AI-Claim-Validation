from app.models.validation import ValidationResult

def test_validation_schema():
    data = {
        "status" : "needs_review",
        "confidence" : 0.7,
        "issues" : [],
        "needs_human_review" : True,
        "rationale" : "Missing coverage info",
        "source" : "rules_engine"
    }
    result = ValidationResult(**data)
    assert result.confidence <= 1.0
