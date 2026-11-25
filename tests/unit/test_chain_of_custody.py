"""
Unit Tests for Cryptographic Chain-of-Custody Ledger (Phase 10 - F-023).
"""

import os
import json
import tempfile
import pytest
from pathlib import Path

from engines.forensic_engine.evidence_locker import ChainOfCustodyLedger, CustodyEvent


@pytest.fixture
def ledger() -> ChainOfCustodyLedger:
    with tempfile.TemporaryDirectory() as tmpdir:
        ledger_path = Path(tmpdir) / "chain_of_custody.jsonl"
        yield ChainOfCustodyLedger(ledger_path)


def test_genesis_block_and_event_appending(ledger: ChainOfCustodyLedger) -> None:
    """Verifies events are chained starting from GENESIS_HASH."""
    assert ledger.get_latest_hash() == ChainOfCustodyLedger.GENESIS_HASH

    ev1 = ledger.append_event(
        evidence_id="EVID-001",
        operator_username="officer_doe",
        operator_role="INVESTIGATOR",
        action="INGEST",
        details={"case": "CASE-101"},
    )

    assert ev1.prev_hash == ChainOfCustodyLedger.GENESIS_HASH
    assert len(ev1.record_hash) == 64
    assert ledger.get_latest_hash() == ev1.record_hash

    ev2 = ledger.append_event(
        evidence_id="EVID-001",
        operator_username="supervisor_jones",
        operator_role="SUPERVISOR",
        action="VIEW",
        details={"reason": "Auditing evidence"},
    )

    assert ev2.prev_hash == ev1.record_hash
    assert len(ev2.record_hash) == 64

    is_valid, count, err = ledger.verify_chain()
    assert is_valid is True
    assert count == 2
    assert err is None


def test_tamper_detection_on_line_modification(ledger: ChainOfCustodyLedger) -> None:
    """Verifies that editing any field in a past custody event breaks hash verification."""
    ledger.append_event("EVID-002", "op1", "ADMIN", "INGEST", {"note": "Initial"})
    ledger.append_event("EVID-002", "op2", "INVESTIGATOR", "VIEW", {"note": "Second"})
    ledger.append_event("EVID-002", "op3", "INVESTIGATOR", "EXPORT", {"note": "Third"})

    # Modify record 1 in the ledger file
    with open(ledger.ledger_file, "r", encoding="utf-8") as f:
        lines = f.readlines()

    tampered_record = json.loads(lines[1])
    tampered_record["operator_username"] = "malicious_hacker"
    lines[1] = json.dumps(tampered_record) + "\n"

    with open(ledger.ledger_file, "w", encoding="utf-8") as f:
        f.writelines(lines)

    # Verification must detect content alteration
    is_valid, count, err = ledger.verify_chain()
    assert is_valid is False
    assert "Content alteration" in err or "Hash break" in err


def test_tamper_detection_on_line_deletion(ledger: ChainOfCustodyLedger) -> None:
    """Verifies that deleting an intermediate event breaks hash chaining."""
    ledger.append_event("EVID-003", "op1", "ADMIN", "INGEST")
    ledger.append_event("EVID-003", "op2", "INVESTIGATOR", "VIEW")
    ledger.append_event("EVID-003", "op3", "INVESTIGATOR", "EXPORT")

    with open(ledger.ledger_file, "r", encoding="utf-8") as f:
        lines = f.readlines()

    # Delete the middle record
    del lines[1]

    with open(ledger.ledger_file, "w", encoding="utf-8") as f:
        f.writelines(lines)

    is_valid, count, err = ledger.verify_chain()
    assert is_valid is False
    assert "Hash break" in err
