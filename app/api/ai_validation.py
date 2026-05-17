"""AI validation API endpoint"""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from app.core.audit_log import log_audit_event
from app.core.auth import Principal
from app.core.config import settings
from app.db.session import get_session
from app.db.models import Claim, Validation, ValidationSource
from app.dependencies.auth import require_system
from app.models.ai_validation_models import AIValidationResult
from app.services.ai_validator import AIValidationService
from app.services.validation.guardrails import apply_guardrails, validate_against_deterministic
from app.services.hallucination_detector import (
    check_for_hallucinations,
    apply_hallucination_escalation,
)
from app.utils.hashing import hash_ai_validation_input, hash_ai_validation_output

router = APIRouter(prefix="/claims", tags=["ai-validation"])


@router.post("/{claim_id}/validate/ai", response_model=AIValidationResult)
def validate_claim_ai(
    claim_id: UUID,
    session: Session = Depends(get_session),
    _principal: Principal = Depends(require_system),
):
    """Run AI validation on a claim (system role only)."""
    log_audit_event(
        "ai_validation_started",
        claim_id=str(claim_id),
        validation_type="llm",
    )

    try:
        claim = session.exec(select(Claim).where(Claim.id == claim_id)).first()
        if not claim:
            raise HTTPException(
                status_code=404,
                detail={"error": "not_found", "message": "Claim not found"},
            )

        deterministic_validation = session.exec(
            select(Validation)
            .where(Validation.claim_id == claim_id)
            .where(Validation.source == ValidationSource.deterministic)
            .order_by(Validation.created_at.desc())
        ).first()

        if not deterministic_validation:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "prerequisite_missing",
                    "message": "Deterministic validation must be run before AI validation",
                },
            )

        deterministic_result = deterministic_validation.result_json

        if not settings.OPENAI_API_KEY:
            raise HTTPException(
                status_code=500,
                detail={
                    "error": "configuration_error",
                    "message": "OPENAI_API_KEY is not configured",
                },
            )

        ai_service = AIValidationService(
            api_key=settings.OPENAI_API_KEY,
            model_name=settings.OPENAI_MODEL,
        )
        ai_result = ai_service.validate_claim(
            claim_data=claim.raw_claim_json,
            deterministic_result=deterministic_result,
        )

        ai_result = validate_against_deterministic(ai_result, deterministic_result)
        ai_result = apply_guardrails(ai_result)

        hallucination_check = check_for_hallucinations(ai_result, claim.raw_claim_json)
        ai_result = apply_hallucination_escalation(ai_result, hallucination_check)

        result_dict = ai_result.model_dump(mode="json")
        input_hash = hash_ai_validation_input(claim.raw_claim_json, deterministic_result)
        output_hash = hash_ai_validation_output(result_dict)

        validation = Validation(
            claim_id=claim_id,
            source=ValidationSource.llm,
            result_json=result_dict,
            model_name=ai_service.get_model_name(),
            prompt_version=ai_service.get_prompt_version(),
            input_hash=input_hash,
            output_hash=output_hash,
            confidence_score=ai_result.confidence,
            needs_human_review=ai_result.needs_human_review,
        )
        session.add(validation)
        session.commit()
        session.refresh(validation)

        log_audit_event(
            "ai_validation_completed",
            claim_id=str(claim_id),
            validation_id=str(validation.id),
            validation_type="llm",
            model_name=ai_service.get_model_name(),
            prompt_version=ai_service.get_prompt_version(),
            confidence_score=ai_result.confidence,
            hallucination_risk=hallucination_check.hallucination_risk_detected,
            hallucination_flags=hallucination_check.flags,
            input_hash=input_hash,
            output_hash=output_hash,
            needs_human_review=ai_result.needs_human_review,
            final_status=ai_result.status,
            num_issues=len(ai_result.issues),
        )

        return ai_result

    except HTTPException:
        raise
    except Exception as e:
        log_audit_event(
            "ai_validation_failed",
            claim_id=str(claim_id),
            validation_type="llm",
            error=str(e),
        )
        raise HTTPException(
            status_code=500,
            detail={"error": "internal_error", "message": str(e)},
        )
