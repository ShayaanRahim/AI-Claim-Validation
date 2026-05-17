"""Pydantic models for human review workflow."""
from typing import Optional, Literal, List
from pydantic import BaseModel, Field


class ReviewRequest(BaseModel):
    """Input schema for submitting a human review decision."""
    reviewer_id: str = Field(min_length=1, description="Unique identifier for the reviewer")
    decision: Literal["APPROVED", "REJECTED", "ESCALATED"]
    notes: Optional[str] = Field(default=None, description="Free-text reviewer notes")
    override_rationale: Optional[str] = Field(
        default=None,
        description="Required when the decision overrides the AI recommendation"
    )


class ReviewResponse(BaseModel):
    """Response schema for a completed review."""
    review_id: str
    claim_id: str
    reviewer_id: str
    decision: str
    notes: Optional[str]
    override_rationale: Optional[str]
    claim_status_before: str
    claim_status_after: str
    created_at: str


class ReviewQueueItem(BaseModel):
    """A single claim in the review queue."""
    claim_id: str
    claim_status: str
    created_at: str
    updated_at: str
    ai_confidence: Optional[float] = None
    ai_status: Optional[str] = None
    ai_rationale: Optional[str] = None
    deterministic_status: Optional[str] = None
    issue_count: int = 0


class ReviewQueueResponse(BaseModel):
    """Response schema for the review queue listing."""
    total: int
    items: List[ReviewQueueItem]


class ClaimHistoryEntry(BaseModel):
    """A single entry in a claim's audit history."""
    entry_type: Literal["validation", "review"]
    source: Optional[str] = None
    timestamp: str
    details: dict


class ClaimHistoryResponse(BaseModel):
    """Full audit history for a claim."""
    claim_id: str
    current_status: str
    history: List[ClaimHistoryEntry]
