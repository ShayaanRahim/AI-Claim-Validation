"""
Lightweight deterministic hallucination detection for AI validation outputs.

Checks for indicators that the AI may have fabricated references, invented
fields, or produced rationales unsupported by the input data.

This is NOT semantic analysis — it is pattern-based and explicit.
Every flag is auditable and logged.
"""
import logging
import re
from typing import Dict, Any, List

from app.models.ai_validation_models import AIValidationResult


logger = logging.getLogger(__name__)


KNOWN_CLAIM_FIELDS = frozenset({
    "patient.id",
    "patient.date_of_birth",
    "coverage.policy_id",
    "coverage.start_date",
    "coverage.end_date",
    "care_event.service_date",
    "care_event.location",
    "billing.codes",
})

FABRICATED_REFERENCE_PATTERNS = [
    re.compile(r"Section\s+\d+[A-Z]?\b", re.IGNORECASE),
    re.compile(r"\bNCD-\d{3}\.\d+\b", re.IGNORECASE),
    re.compile(r"\bCMS\s+Medicare\s+Part\s+[A-Z]\b", re.IGNORECASE),
    re.compile(r"\bFederal\s+\w+\s+Benefits?\s+Act\b", re.IGNORECASE),
    re.compile(r"\bCFR\s+\d+\.\d+\b", re.IGNORECASE),
    re.compile(r"\b42\s*U\.?S\.?C\.?\s*§?\s*\d+", re.IGNORECASE),
]


class HallucinationCheckResult:
    """Container for hallucination check findings."""

    def __init__(self) -> None:
        self.flags: List[str] = []

    @property
    def hallucination_risk_detected(self) -> bool:
        return len(self.flags) > 0

    def add(self, flag: str) -> None:
        self.flags.append(flag)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "hallucination_risk_detected": self.hallucination_risk_detected,
            "flags": list(self.flags),
        }


def check_for_hallucinations(
    ai_result: AIValidationResult,
    claim_data: Dict[str, Any],
) -> HallucinationCheckResult:
    """
    Run all hallucination checks against an AI validation result.

    Returns a HallucinationCheckResult with any flags raised.
    """
    result = HallucinationCheckResult()

    _check_unsupported_references(ai_result, result)
    _check_invented_fields(ai_result, result)
    _check_approval_without_evidence(ai_result, claim_data, result)
    _check_confidence_rationale_mismatch(ai_result, result)

    if result.hallucination_risk_detected:
        logger.warning(
            "Hallucination risk detected in AI output: %s", result.flags
        )

    return result


def _check_unsupported_references(
    ai_result: AIValidationResult,
    check: HallucinationCheckResult,
) -> None:
    """Flag rationales that cite specific regulations, statutes, or NCDs."""
    text = ai_result.rationale or ""
    for pattern in FABRICATED_REFERENCE_PATTERNS:
        match = pattern.search(text)
        if match:
            check.add(f"unsupported_reference: '{match.group()}' in rationale")


def _check_invented_fields(
    ai_result: AIValidationResult,
    check: HallucinationCheckResult,
) -> None:
    """Flag issues that reference fields not in the claim schema."""
    for issue in ai_result.issues:
        base_field = issue.field.split("[")[0]
        if base_field not in KNOWN_CLAIM_FIELDS:
            check.add(f"invented_field: issue references '{issue.field}' which is not in claim schema")


def _check_approval_without_evidence(
    ai_result: AIValidationResult,
    claim_data: Dict[str, Any],
    check: HallucinationCheckResult,
) -> None:
    """Flag high-confidence approval when the input claim has clearly empty required fields."""
    if ai_result.status != "approved" or ai_result.confidence < 0.8:
        return

    coverage = claim_data.get("coverage", {})
    billing = claim_data.get("billing", {})

    policy_id = coverage.get("policy_id", "")
    codes = billing.get("codes", [])

    if not policy_id or (isinstance(policy_id, str) and policy_id.strip() == ""):
        check.add("approval_without_evidence: approved with high confidence but policy_id is empty")

    if not codes or (isinstance(codes, list) and len(codes) == 0):
        check.add("approval_without_evidence: approved with high confidence but billing codes are empty")


def _check_confidence_rationale_mismatch(
    ai_result: AIValidationResult,
    check: HallucinationCheckResult,
) -> None:
    """Flag when a very high confidence score accompanies hedging language."""
    if ai_result.confidence < 0.90:
        return

    hedging_patterns = [
        re.compile(r"\bunsure\b", re.IGNORECASE),
        re.compile(r"\buncertain\b", re.IGNORECASE),
        re.compile(r"\bcannot determine\b", re.IGNORECASE),
        re.compile(r"\binsufficient\b", re.IGNORECASE),
        re.compile(r"\bmight\s+not\b", re.IGNORECASE),
        re.compile(r"\bpossibly\s+invalid\b", re.IGNORECASE),
    ]

    text = ai_result.rationale or ""
    for pattern in hedging_patterns:
        match = pattern.search(text)
        if match:
            check.add(
                f"confidence_rationale_mismatch: confidence={ai_result.confidence} "
                f"but rationale contains hedging language '{match.group()}'"
            )
            break


def apply_hallucination_escalation(
    ai_result: AIValidationResult,
    hallucination_check: HallucinationCheckResult,
) -> AIValidationResult:
    """
    If hallucination risk is detected, force escalation.

    Modifies the result in-place:
    - Sets needs_human_review = True
    - If status was 'approved', downgrades to 'needs_review'
    - Prepends guardrail notice to rationale
    """
    if not hallucination_check.hallucination_risk_detected:
        return ai_result

    logger.warning(
        "Escalating AI result due to hallucination risk: %s",
        hallucination_check.flags,
    )

    ai_result.needs_human_review = True

    if ai_result.status == "approved":
        ai_result.status = "needs_review"

    flag_summary = "; ".join(hallucination_check.flags)
    ai_result.rationale = (
        f"[HALLUCINATION GUARDRAIL] {flag_summary}. "
        f"Original rationale: {ai_result.rationale}"
    )

    return ai_result
