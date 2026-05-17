from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any
from uuid import UUID, uuid4

from sqlmodel import SQLModel, Field, Column
from sqlalchemy import DateTime, func, JSON


class ClaimStatus(str, Enum):
    DRAFT = "DRAFT"
    READY_FOR_AI = "READY_FOR_AI"
    NEEDS_FIXES = "NEEDS_FIXES"
    IN_REVIEW = "IN_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class ValidationSource(str, Enum):
    deterministic = "deterministic"
    llm = "llm"


class ReviewDecision(str, Enum):
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    ESCALATED = "ESCALATED"


class Claim(SQLModel, table=True):
    __tablename__ = "claims"

    id: UUID = Field(default_factory=uuid4, primary_key=True, index=True)

    raw_claim_json: Dict[str, Any] = Field(sa_column=Column(JSON, nullable=False))

    status: str = Field(default=ClaimStatus.DRAFT, nullable=False)

    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    )
    updated_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    )


class Validation(SQLModel, table=True):
    __tablename__ = "validations"

    id: UUID = Field(default_factory=uuid4, primary_key=True, index=True)

    claim_id: UUID = Field(foreign_key="claims.id", index=True, nullable=False)

    source: str = Field(nullable=False)

    result_json: Dict[str, Any] = Field(sa_column=Column(JSON, nullable=False))

    # AI-specific fields (optional, only populated for AI validations)
    model_name: Optional[str] = Field(default=None)
    prompt_version: Optional[str] = Field(default=None)
    input_hash: Optional[str] = Field(default=None, index=True)
    confidence_score: Optional[float] = Field(default=None)
    needs_human_review: bool = Field(default=False, nullable=False)

    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    )


class Review(SQLModel, table=True):
    __tablename__ = "reviews"

    id: UUID = Field(default_factory=uuid4, primary_key=True, index=True)

    claim_id: UUID = Field(foreign_key="claims.id", index=True, nullable=False)
    validation_id: Optional[UUID] = Field(default=None, foreign_key="validations.id")

    reviewer_id: str = Field(nullable=False, index=True)
    decision: str = Field(nullable=False)
    notes: Optional[str] = Field(default=None)
    override_rationale: Optional[str] = Field(default=None)

    # Snapshot of claim state at review time for auditability
    claim_status_before: str = Field(nullable=False)
    claim_status_after: str = Field(nullable=False)

    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    )

