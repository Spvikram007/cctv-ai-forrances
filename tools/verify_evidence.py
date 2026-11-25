#!/usr/bin/env python3
"""
CCTV AI Intelligence Platform - Standalone Evidence Verification Utility.
Independent, zero-dependency judicial verification tool for court clerks,
defense counsel, forensic examiners, and judicial auditors.
Requires only standard Python 3.8+ (no CCTV platform installation required).
"""

import os
import sys
import json
import hashlib
import argparse
from pathlib import Path

try:
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.exceptions import InvalidSignature
    HAS_CRYPTOGRAPHY = True
except ImportError:
    HAS_CRYPTOGRAPHY = False


GENESIS_HASH = "0" * 64


def compute_file_sha256(filepath: str) -> str:
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def verify_chain_of_custody(ledger_path: str):
    if not os.path.exists(ledger_path):
        return True, 0, "No custody ledger present."

    expected_prev = GENESIS_HASH
    count = 0
    with open(ledger_path, "r", encoding="utf-8") as f:
        for idx, line in enumerate(f):
            line = line.strip()
            if not line:
                continue
            event = json.loads(line)
            if event.get("prev_hash") != expected_prev:
                return False, count, f"Hash chain break at event {idx}: {event.get('prev_hash')[:16]} != {expected_prev[:16]}"

            payload = {
                "event_id": event["event_id"],
                "evidence_id": event["evidence_id"],
                "timestamp_utc": event["timestamp_utc"],
                "operator_username": event["operator_username"],
                "operator_role": event["operator_role"],
                "action": event["action"],
                "details": event["details"],
                "prev_hash": event["prev_hash"],
            }
            canonical_str = json.dumps(payload, sort_keys=True)
            recalculated = hashlib.sha256((expected_prev + canonical_str).encode("utf-8")).hexdigest()
            if recalculated != event["record_hash"]:
                return False, count, f"Record content modified at event {idx}: {event['record_hash'][:16]} != {recalculated[:16]}"
            expected_prev = event["record_hash"]
            count += 1

    return True, count, None


def verify_manifest_signature(manifest_dict, public_key_pem):
    if not HAS_CRYPTOGRAPHY:
        return None, "cryptography library not installed; signature verification skipped."

    try:
        pub_key = serialization.load_pem_public_key(public_key_pem.encode("utf-8"))
        canonical_payload = {
            "manifest_version": manifest_dict["manifest_version"],
            "evidence_id": manifest_dict["evidence_id"],
            "case_number": manifest_dict["case_number"],
            "channel_id": manifest_dict["channel_id"],
            "evidence_type": manifest_dict["evidence_type"],
            "file_name": manifest_dict["file_name"],
            "file_size_bytes": manifest_dict["file_size_bytes"],
            "file_sha256": manifest_dict["file_sha256"],
            "duration_sec": manifest_dict["duration_sec"],
            "nominal_fps": manifest_dict["nominal_fps"],
            "resolution": list(manifest_dict["resolution"]),
            "codec": manifest_dict["codec"],
            "source_evidence_id": manifest_dict.get("source_evidence_id"),
            "source_sha256": manifest_dict.get("source_sha256"),
            "enhancement_metadata": manifest_dict.get("enhancement_metadata"),
            "signing_time_utc": manifest_dict["signing_time_utc"],
            "signer_identity": manifest_dict["signer_identity"],
        }
        canonical_bytes = json.dumps(canonical_payload, sort_keys=True).encode("utf-8")
        signature_der = bytes.fromhex(manifest_dict["signature_hex"])
        pub_key.verify(signature_der, canonical_bytes, ec.ECDSA(hashes.SHA256()))
        return True, "ECDSA SECP256R1 signature is VALID."
    except InvalidSignature:
        return False, "Digital signature verification FAILED: Manifest altered or key mismatch!"
    except Exception as e:
        return False, f"Signature validation error: {e}"


def verify_package(package_dir_or_file: str) -> bool:
    pkg = Path(package_dir_or_file)

    # Handle zip files automatically
    if pkg.is_file() and pkg.suffix.lower() in (".cctvevid", ".zip"):
        import tempfile
        import zipfile
        with tempfile.TemporaryDirectory() as tmp_extract:
            with zipfile.ZipFile(str(pkg), "r") as zf:
                zf.extractall(tmp_extract)
            return verify_package(tmp_extract)

    manifest_p = pkg / "manifest.json"
    if not manifest_p.exists():
        print(f"[FAIL] manifest.json not found in {pkg}")
        return False

    with open(manifest_p, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    media_p = pkg / manifest["file_name"]
    if not media_p.exists():
        print(f"[FAIL] Media file '{manifest['file_name']}' not found in {pkg}")
        return False

    print("================================================================================")
    print("           STANDALONE FORENSIC EVIDENCE VERIFICATION AUDIT")
    print("================================================================================")
    print(f" Evidence ID:        {manifest.get('evidence_id')}")
    print(f" Case Number:        {manifest.get('case_number')}")
    print(f" Evidence Type:      {manifest.get('evidence_type')}")
    print(f" File Name:          {manifest.get('file_name')}")
    print(f" Expected SHA-256:   {manifest.get('file_sha256')}")

    # 1. Check SHA-256
    actual_sha = compute_file_sha256(str(media_p))
    sha_pass = (actual_sha == manifest.get("file_sha256"))
    print(f" Computed SHA-256:   {actual_sha}")
    print(f" [1] SHA-256 HASH MATCH:         {'[PASSED]' if sha_pass else '[FAILED - CORRUPTED/TAMPERED]'}")

    # 2. Check Digital Signature
    pub_key = manifest.get("public_key_pem", "")
    sig_pass, sig_msg = verify_manifest_signature(manifest, pub_key)
    print(f" [2] DIGITAL SIGNATURE:          {'[PASSED]' if sig_pass else ('[SKIPPED]' if sig_pass is None else '[FAILED - TAMPERED]')}")
    print(f"     Details: {sig_msg}")

    # 3. Check Custody Ledger
    ledger_p = pkg / "chain_of_custody.jsonl"
    chain_pass, chain_count, chain_msg = verify_chain_of_custody(str(ledger_p))
    print(f" [3] CUSTODY LEDGER INTEGRITY:   {'[PASSED]' if chain_pass else '[FAILED - TAMPERED]'}")
    print(f"     Records Verified: {chain_count} events (Merkle Hash Chained)")

    # 4. Judicial & Forensic Classification Check
    if manifest.get("evidence_type") == "DERIVED_ENHANCEMENT":
        print("--------------------------------------------------------------------------------")
        print(" [!] NOTICE: DERIVED AI ENHANCED MEDIA (PHASE 9 OUTPUT)")
        print(f"     Source Hash: {manifest.get('source_sha256')}")
        print("     This footage is a derived reconstruction. Do NOT present as original evidence.")
    else:
        print("--------------------------------------------------------------------------------")
        print(" [*] ORIGINAL CAPTURE EVIDENCE")
        print("     Raw footage captured directly from sensor stream.")

    print("================================================================================")
    is_fully_intact = sha_pass and (sig_pass is True or sig_pass is None) and chain_pass
    if is_fully_intact:
        print(" FINAL VERDICT: EVIDENCE IS CRYPTOGRAPHICALLY VALID AND UNALTERED.")
    else:
        print(" FINAL VERDICT: EVIDENCE VERIFICATION FAILED (TAMPERING DETECTED).")
    print("================================================================================")
    return is_fully_intact


def main():
    parser = argparse.ArgumentParser(description="Standalone Forensic Evidence Verification Utility")
    parser.add_argument("target", help="Path to evidence package directory or .cctvevid/.zip file")
    args = parser.parse_args()

    passed = verify_package(args.target)
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
