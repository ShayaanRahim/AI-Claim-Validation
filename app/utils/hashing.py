"""Stable SHA-256 hashing utilities for audit-grade traceability."""
import hashlib
import json
from typing import Any


def stable_json_dumps(payload: Any) -> str:
    """Serialize payload to a deterministic JSON string."""
    return json.dumps(payload, sort_keys=True, default=str)


def sha256_hex(data: str) -> str:
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def hash_payload(payload: Any) -> str:
    """Hash any JSON-serializable payload."""
    return sha256_hex(stable_json_dumps(payload))


def hash_ai_validation_input(claim_data: dict, deterministic_result: dict) -> str:
    """Hash the combined input sent to AI validation."""
    return hash_payload({"claim": claim_data, "deterministic": deterministic_result})


def hash_ai_validation_output(result: dict) -> str:
    """Hash the structured AI validation output."""
    return hash_payload(result)
