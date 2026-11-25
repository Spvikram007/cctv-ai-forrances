"""
External Tamper-Evident Alarm History Checkpoint Service.
Phase 12.2 Final Validation (F-046, Change ID: CHG-20261125-011).

Anchors cryptographic hash-chain checkpoints in an independent filesystem ledger
outside the ordinary relational database, protecting against complete chain
reconstruction and database replacement attacks.
"""

import os
import json
import hmac
import hashlib
import uuid
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from pathlib import Path

from core.logging.logger import get_logger

logger = get_logger("alarm_checkpoints")

DEFAULT_CHECKPOINT_DIR = Path("storage/alarms/checkpoints")
DEFAULT_CHECKPOINT_FILE = DEFAULT_CHECKPOINT_DIR / "alarm_history_checkpoints.jsonl"
HMAC_SECRET = b"cctv_ai_tamper_evident_alarm_checkpoint_key_2026"


def _get_checkpoint_path(custom_path: Optional[str] = None) -> Path:
    if custom_path:
        p = Path(custom_path)
    else:
        p = DEFAULT_CHECKPOINT_FILE
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def compute_checkpoint_signature(
    checkpoint_id: str,
    alarm_id: str,
    timestamp: str,
    entry_index: int,
    entry_hash: str,
    total_entries: int,
) -> str:
    """Computes an authoritative HMAC-SHA256 signature over checkpoint data."""
    canonical_str = f"{checkpoint_id}|{alarm_id}|{timestamp}|{entry_index}|{entry_hash}|{total_entries}"
    return hmac.new(HMAC_SECRET, canonical_str.encode("utf-8"), hashlib.sha256).hexdigest()


def create_alarm_checkpoint(
    alarm_id: str,
    entry_index: int,
    entry_hash: str,
    total_entries: int,
    custom_path: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Anchors a signed checkpoint record to the external append-only ledger.
    """
    checkpoint_id = str(uuid.uuid4())
    ts = datetime.now(timezone.utc).isoformat()
    sig = compute_checkpoint_signature(checkpoint_id, alarm_id, ts, entry_index, entry_hash, total_entries)

    record = {
        "checkpoint_id": checkpoint_id,
        "alarm_id": alarm_id,
        "timestamp": ts,
        "entry_index": entry_index,
        "entry_hash": entry_hash,
        "total_entries": total_entries,
        "signature": sig,
    }

    path = _get_checkpoint_path(custom_path)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")

    logger.info("Created external checkpoint %s for alarm %s at index %d", checkpoint_id, alarm_id, entry_index)
    return record


def get_alarm_checkpoints(alarm_id: str, custom_path: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Reads all external checkpoints for an alarm and validates cryptographic signatures.
    """
    path = _get_checkpoint_path(custom_path)
    if not path.exists():
        return []

    valid_checkpoints = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                if rec.get("alarm_id") != alarm_id:
                    continue

                # Verify checkpoint signature
                expected_sig = compute_checkpoint_signature(
                    rec["checkpoint_id"],
                    rec["alarm_id"],
                    rec["timestamp"],
                    rec["entry_index"],
                    rec["entry_hash"],
                    rec["total_entries"],
                )
                if rec.get("signature") == expected_sig:
                    valid_checkpoints.append(rec)
                else:
                    logger.error("Corrupted/forged checkpoint signature detected: %s", rec.get("checkpoint_id"))
            except Exception as e:
                logger.warning("Error reading checkpoint line: %s", e)

    return valid_checkpoints


def verify_checkpoint_integrity(
    alarm_id: str,
    db_entries: List[Any],
    custom_path: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Validates in-database history entries against authoritative external checkpoints.
    Detects record deletion, tail truncation, and complete chain reconstruction/forgery.
    """
    checkpoints = get_alarm_checkpoints(alarm_id, custom_path)
    if not checkpoints:
        return {
            "checkpoint_verified": True,
            "has_checkpoints": False,
            "details": "No external checkpoints anchored for this alarm.",
        }

    total_db_entries = len(db_entries)

    for cp in checkpoints:
        cp_idx = cp["entry_index"]
        cp_hash = cp["entry_hash"]
        cp_total = cp["total_entries"]

        # Check 1: Record truncation / deletion (DB has fewer entries than checkpointed)
        if total_db_entries < cp_total:
            return {
                "checkpoint_verified": False,
                "has_checkpoints": True,
                "details": (
                    f"External checkpoint truncation violation: database contains {total_db_entries} entries, "
                    f"but external checkpoint '{cp['checkpoint_id']}' recorded {cp_total} entries (deletion detected)."
                ),
                "violated_checkpoint": cp,
            }

        # Check 2: Index exists in DB
        matching_entry = None
        for entry in db_entries:
            idx = getattr(entry, "entry_index", None)
            if idx is None and isinstance(entry, dict):
                idx = entry.get("entry_index")
            if idx == cp_idx:
                matching_entry = entry
                break

        if not matching_entry:
            return {
                "checkpoint_verified": False,
                "has_checkpoints": True,
                "details": f"External checkpoint entry at index {cp_idx} missing from database (omission detected).",
                "violated_checkpoint": cp,
            }

        # Check 3: Hash matches external anchor (detects complete chain reconstruction)
        entry_hash = getattr(matching_entry, "entry_hash", None)
        if entry_hash is None and isinstance(matching_entry, dict):
            entry_hash = matching_entry.get("entry_hash")

        if entry_hash != cp_hash:
            return {
                "checkpoint_verified": False,
                "has_checkpoints": True,
                "details": (
                    f"External checkpoint digest mismatch at index {cp_idx}: database hash is '{entry_hash}', "
                    f"which does not match external anchor '{cp_hash}' (chain reconstruction/forgery detected)."
                ),
                "violated_checkpoint": cp,
            }

    return {
        "checkpoint_verified": True,
        "has_checkpoints": True,
        "checkpoint_count": len(checkpoints),
        "details": f"Successfully verified against {len(checkpoints)} authoritative external checkpoints.",
    }
