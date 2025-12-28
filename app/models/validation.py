from pydantic import BaseModel, Field
from typing import List, Optional, Literal

Severity = Literal["low", "medium", "high"]
Status = Literal["approved", "rejected", "needs_review"]
Source = Literal["rules_engine", "ai_model", "human_review"]

class Issue(BaseModel):
    field: str
    severity: Severity
    message: str

class ModelMetadata(BaseModel):
    model: str
    prompt_version: str

class ValidationResult(BaseModel):
    status: Status
    confidence: float = Field(ge=0.0, le=1.0)
    issues: List[Issue] = Field(default_factory=list)
    needs_human_review: bool
    rationale: Optional[str] = None
    source: Source
    model_metadata: Optional[ModelMetadata] = None
