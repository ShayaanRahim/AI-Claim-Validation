"""Tests for hashing utilities."""
from app.utils.hashing import (
    hash_payload,
    hash_ai_validation_input,
    hash_ai_validation_output,
    stable_json_dumps,
)


def test_stable_json_dumps_order_independent():
    a = stable_json_dumps({"b": 2, "a": 1})
    b = stable_json_dumps({"a": 1, "b": 2})
    assert a == b


def test_hash_payload_deterministic():
    payload = {"status": "PASS", "issues": []}
    assert hash_payload(payload) == hash_payload(payload)


def test_hash_ai_input_deterministic():
    claim = {"patient": {"id": "p1"}}
    det = {"status": "PASS"}
    h1 = hash_ai_validation_input(claim, det)
    h2 = hash_ai_validation_input(claim, det)
    assert h1 == h2
    assert len(h1) == 64


def test_hash_ai_output_differs_from_input():
    claim = {"patient": {"id": "p1"}}
    det = {"status": "PASS"}
    inp = hash_ai_validation_input(claim, det)
    out = hash_ai_validation_output({"status": "approved", "confidence": 0.9})
    assert inp != out
