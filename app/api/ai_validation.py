"""AI validation API endpoint"""
import json
import os
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from app.db.session import get_session
from app.db.models import Claim, Validation, ValidationSource
from app.models.ai_validation_models import AIValidationResult
from app.services.ai_validator import AIValidationService, compute_input_hash
from app.services.validation.guardrails import apply_guardrails, validate_against_deterministic
from app.services.hallucination_detector import (
    check_for_hallucinations, apply_hallucination_escalation,
)


router = APIRouter(prefix="/claims", tags=["ai-validation"])


@router.post("/{claim_id}/validate/ai", response_model=AIValidationResult)
def validate_claim_ai(
    claim_id: UUID,
    session: Session = Depends(get_session)
):
    """
    Run AI validation on a claim.
    
    Flow:
    1. Fetch claim
    2. Fetch deterministic validation results
    3. Short-circuit if deterministic validation doesn't exist or failed critically
    4. Call AI validation service
    5. Apply post-processing guardrails
    6. Persist result to database
    7. Return structured response
    
    The AI is advisory only and runs AFTER deterministic rules.
    If AI fails, a safe fallback response is returned.
    """
    # Log AI validation started
    print(json.dumps({
        "event": "ai_validation_started",
        "claim_id": str(claim_id),
        "source": "llm"
    }))
    
    try:
        # Step 1: Load claim
        statement = select(Claim).where(Claim.id == claim_id)
        claim = session.exec(statement).first()
        
        if not claim:
            raise HTTPException(status_code=404, detail="Claim not found")
        
        # Step 2: Load deterministic validation results
        # We need the most recent deterministic validation
        deterministic_statement = (
            select(Validation)
            .where(Validation.claim_id == claim_id)
            .where(Validation.source == ValidationSource.deterministic)
            .order_by(Validation.created_at.desc())
        )
        deterministic_validation = session.exec(deterministic_statement).first()
        
        if not deterministic_validation:
            raise HTTPException(
                status_code=400,
                detail="Deterministic validation must be run before AI validation"
            )
        
        deterministic_result = deterministic_validation.result_json
        
        # Step 3: Check if we should short-circuit
        # If deterministic validation found critical errors, we might want to skip AI
        # For now, we'll let AI analyze even failed claims (it can add context)
        # But this is a business decision that could be changed
        
        # Step 4: Call AI validation service
        # Get OpenAI API key from environment
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise HTTPException(
                status_code=500,
                detail="OPENAI_API_KEY environment variable not set"
            )
        
        ai_service = AIValidationService(api_key=api_key)
        ai_result = ai_service.validate_claim(
            claim_data=claim.raw_claim_json,
            deterministic_result=deterministic_result
        )
        
        # Step 5: Apply guardrails
        ai_result = validate_against_deterministic(ai_result, deterministic_result)
        ai_result = apply_guardrails(ai_result)

        # Step 5b: Hallucination detection
        hallucination_check = check_for_hallucinations(ai_result, claim.raw_claim_json)
        ai_result = apply_hallucination_escalation(ai_result, hallucination_check)

        # Step 6: Compute input hash for deduplication
        input_hash = compute_input_hash(claim.raw_claim_json, deterministic_result)
        
        # Step 7: Persist to database
        validation = Validation(
            claim_id=claim_id,
            source=ValidationSource.llm,
            result_json=ai_result.model_dump(mode="json"),
            model_name=ai_service.get_model_name(),
            prompt_version=ai_service.get_prompt_version(),
            input_hash=input_hash,
            confidence_score=ai_result.confidence,
            needs_human_review=ai_result.needs_human_review
        )
        session.add(validation)
        session.commit()
        session.refresh(validation)
        
        # Log AI validation completed
        print(json.dumps({
            "event": "ai_validation_completed",
            "claim_id": str(claim_id),
            "validation_id": str(validation.id),
            "validation_source": "llm",
            "model_name": ai_service.get_model_name(),
            "prompt_version": ai_service.get_prompt_version(),
            "status": ai_result.status,
            "confidence": ai_result.confidence,
            "needs_human_review": ai_result.needs_human_review,
            "num_issues": len(ai_result.issues),
            "hallucination_risk": hallucination_check.hallucination_risk_detected,
            "hallucination_flags": hallucination_check.flags,
        }))
        
        return ai_result
        
    except HTTPException:
        raise
    except Exception as e:
        # Log AI validation failed
        print(json.dumps({
            "event": "ai_validation_failed",
            "claim_id": str(claim_id),
            "error": str(e)
        }))
        raise HTTPException(status_code=500, detail=str(e))
