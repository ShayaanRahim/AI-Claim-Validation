"""
Post-processing guardrails for AI validation results.

These rules enforce safety constraints on AI output to ensure:
- Low confidence claims aren't auto-approved
- Uncertain outcomes require human review
- AI recommendations follow business rules

This logic is separate from the AI itself to make rules explicit and auditable.
"""
import logging
from app.models.ai_validation_models import AIValidationResult
from app.core.config import settings


logger = logging.getLogger(__name__)


CONFIDENCE_THRESHOLD = settings.AI_CONFIDENCE_THRESHOLD
AUTO_APPROVE_THRESHOLD = settings.AI_AUTO_APPROVE_THRESHOLD


def apply_guardrails(result: AIValidationResult) -> AIValidationResult:
    """
    Apply post-processing guardrails to AI validation result.

    Rules enforced:
    1. Low confidence (< threshold) forces needs_human_review = true
    2. Status "unknown" forces needs_human_review = true
    3. Status "rejected" forces needs_human_review = true (human must confirm)
    4. Status "approved" with confidence < 0.75 is changed to "needs_review"
    5. Any "high" severity issue forces needs_human_review = true
    6. Status "approved" with confidence below auto-approve threshold forces human review
    """
    logger.info(f"Applying guardrails to AI result: status={result.status}, confidence={result.confidence}")

    modified = False

    # Rule 1: Low confidence forces human review
    if result.confidence < CONFIDENCE_THRESHOLD:
        if not result.needs_human_review:
            logger.info(f"Forcing human review due to low confidence: {result.confidence}")
            result.needs_human_review = True
            modified = True

    # Rule 2: "unknown" status forces human review
    if result.status == "unknown":
        if not result.needs_human_review:
            logger.info("Forcing human review due to 'unknown' status")
            result.needs_human_review = True
            modified = True

    # Rule 3: "rejected" status forces human review
    if result.status == "rejected":
        if not result.needs_human_review:
            logger.info("Forcing human review due to 'rejected' status")
            result.needs_human_review = True
            modified = True

    # Rule 4: Can't approve with low confidence
    if result.status == "approved" and result.confidence < CONFIDENCE_THRESHOLD:
        logger.warning(
            f"AI attempted to approve with low confidence ({result.confidence}). "
            f"Changing status to 'needs_review'"
        )
        result.status = "needs_review"
        result.needs_human_review = True
        result.rationale = f"[GUARDRAIL APPLIED] {result.rationale} However, confidence is below threshold for approval."
        modified = True

    # Rule 5: High severity issues require human review
    has_high_severity = any(issue.severity == "high" for issue in result.issues)
    if has_high_severity and not result.needs_human_review:
        logger.info("Forcing human review due to high severity issue(s)")
        result.needs_human_review = True
        modified = True

    # Rule 6: Approved but below auto-approve threshold — still needs human sign-off
    if (
        result.status == "approved"
        and result.confidence < AUTO_APPROVE_THRESHOLD
        and not result.needs_human_review
    ):
        logger.info(
            f"Forcing human review: confidence {result.confidence} below auto-approve threshold {AUTO_APPROVE_THRESHOLD}"
        )
        result.needs_human_review = True
        modified = True

    if modified:
        logger.info(f"Guardrails modified result: final status={result.status}, needs_human_review={result.needs_human_review}")
    else:
        logger.info("No guardrail modifications needed")

    return result


def validate_against_deterministic(
    ai_result: AIValidationResult,
    deterministic_result: dict
) -> AIValidationResult:
    """
    Ensure AI result doesn't contradict deterministic validation.
    
    If deterministic validation found errors, AI should not approve.
    This is a safety check to prevent AI from overriding hard rules.
    
    Args:
        ai_result: The AI validation result
        deterministic_result: The deterministic validation result
        
    Returns:
        Potentially modified AI result
    """
    # If deterministic validation failed, AI cannot approve
    deterministic_status = deterministic_result.get("status")
    
    if deterministic_status == "FAIL" and ai_result.status == "approved":
        logger.warning(
            "AI attempted to approve a claim that failed deterministic validation. "
            "Overriding to 'needs_review'"
        )
        ai_result.status = "needs_review"
        ai_result.needs_human_review = True
        ai_result.rationale = (
            f"[GUARDRAIL APPLIED] Deterministic validation found errors. "
            f"Original AI rationale: {ai_result.rationale}"
        )
    
    return ai_result


def get_confidence_threshold() -> float:
    """Return the confidence threshold for auditing"""
    return CONFIDENCE_THRESHOLD
