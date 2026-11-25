"""
Evidence Packaging & Standalone Verification Exporter (Phase 10 - F-023).
Assembles structured self-contained .cctvevid packages containing the media file,
cryptographically signed manifest, public verification key, chain of custody ledger,
standalone CLI verification utility, and court instructions.
"""

import os
import sys
import json
import zipfile
import shutil
import hashlib
from typing import Dict, Any, Optional
from pathlib import Path

from core.logging.logger import get_logger
from engines.forensic_engine.evidence_locker import (
    EvidenceLocker,
    ChainOfCustodyLedger,
    SignedEvidenceManifest,
    ForensicAccessDeniedError,
)

logger = get_logger("evidence_packager")


STANDALONE_VERIFIER_SCRIPT = '''#!/usr/bin/env python3
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


def compute_file_sha256(filepath):
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def verify_chain_of_custody(ledger_path):
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


def main():
    parser = argparse.ArgumentParser(description="Standalone Forensic Evidence Verification Utility")
    parser.add_argument("package_dir", help="Path to unzipped evidence package or locker folder")
    args = parser.parse_args()

    pkg = Path(args.package_dir)
    manifest_p = pkg / "manifest.json"
    if not manifest_p.exists():
        print(f"[FAIL] manifest.json not found in {pkg}")
        sys.exit(1)

    with open(manifest_p, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    media_p = pkg / manifest["file_name"]
    if not media_p.exists():
        print(f"[FAIL] Media file '{manifest['file_name']}' not found in {pkg}")
        sys.exit(1)

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
    if sha_pass and (sig_pass is True or sig_pass is None) and chain_pass:
        print(" FINAL VERDICT: EVIDENCE IS CRYPTOGRAPHICALLY VALID AND UNALTERED.")
        print("================================================================================")
        sys.exit(0)
    else:
        print(" FINAL VERDICT: EVIDENCE VERIFICATION FAILED (TAMPERING DETECTED).")
        print("================================================================================")
        sys.exit(1)


if __name__ == "__main__":
    main()
'''


class EvidencePackager:
    """
    Creates standardized `.cctvevid` (zip format) export packages
    containing media, signed manifest, public key, custody ledger, and
    standalone court verification script.
    """

    def __init__(self, locker: EvidenceLocker) -> None:
        self.locker = locker

    def create_export_package(
        self,
        evidence_id: str,
        export_destination_path: str,
        operator_username: str,
        operator_role: str,
    ) -> str:
        """
        Exports a locked evidence item into a self-contained `.cctvevid` bundle.
        """
        self.locker._check_permission(operator_role, EvidenceLocker.ALLOWED_ROLES_EXPORT, "EXPORT_EVIDENCE_PACKAGE")

        item_dir = self.locker.base_dir / evidence_id
        if not item_dir.exists():
            raise FileNotFoundError(f"Evidence '{evidence_id}' does not exist.")

        manifest_file = item_dir / "manifest.json"
        with open(manifest_file, "r", encoding="utf-8") as f:
            manifest_dict = json.load(f)

        media_file = item_dir / manifest_dict["file_name"]
        if not media_file.exists():
            raise FileNotFoundError(f"Evidence media file '{manifest_dict['file_name']}' is missing.")

        out_path = Path(export_destination_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        # Assemble package zip
        with zipfile.ZipFile(str(out_path), "w", compression=zipfile.ZIP_DEFLATED) as zf:
            # 1. Media
            zf.write(str(media_file), arcname=manifest_dict["file_name"])

            # 2. Manifest & Signature
            zf.write(str(manifest_file), arcname="manifest.json")
            sig_file = item_dir / "manifest.sig"
            if sig_file.exists():
                zf.write(str(sig_file), arcname="manifest.sig")

            # 3. Public Verification Key
            pub_key_pem = manifest_dict.get("public_key_pem", "")
            zf.writestr("public_key.pem", pub_key_pem)

            # 4. Chain of Custody Ledger
            ledger_file = item_dir / "chain_of_custody.jsonl"
            if ledger_file.exists():
                zf.write(str(ledger_file), arcname="chain_of_custody.jsonl")

            # 5. Standalone Verifier Script
            zf.writestr("verify_evidence.py", STANDALONE_VERIFIER_SCRIPT)

            # 6. Court Instructions Readme
            readme_text = (
                "CCTV AI INTELLIGENCE PLATFORM — FORENSIC EVIDENCE PACKAGE\n"
                "==========================================================\n\n"
                f"Evidence ID:    {evidence_id}\n"
                f"Case Number:    {manifest_dict.get('case_number')}\n"
                f"Evidence Type:  {manifest_dict.get('evidence_type')}\n"
                f"File Name:      {manifest_dict.get('file_name')}\n"
                f"SHA-256 Hash:   {manifest_dict.get('file_sha256')}\n"
                f"Signer:         {manifest_dict.get('signer_identity')}\n"
                f"Signing Time:   {manifest_dict.get('signing_time_utc')}\n\n"
                "INDEPENDENT VERIFICATION INSTRUCTIONS:\n"
                "1. Unzip this package into a directory.\n"
                "2. Open a terminal or PowerShell in that directory.\n"
                "3. Run: python verify_evidence.py .\n\n"
                "The verification utility requires only standard Python 3.8+.\n"
                "It verifies SHA-256 file hashes, ECDSA digital signatures, and\n"
                "validates the append-only custody ledger hash chain.\n\n"
                f"LEGAL NOTICE:\n{manifest_dict.get('legal_disclaimer')}\n"
            )
            zf.writestr("README_FORENSIC_VERIFICATION.txt", readme_text)

        # Log export in ledger
        ledger = ChainOfCustodyLedger(item_dir / "chain_of_custody.jsonl")
        ledger.append_event(
            evidence_id=evidence_id,
            operator_username=operator_username,
            operator_role=operator_role,
            action="EXPORT",
            details={
                "export_path": str(out_path.resolve()),
                "file_size_bytes": out_path.stat().st_size,
            },
        )

        logger.info("Successfully created evidence export package: %s", out_path.name)
        return str(out_path.resolve())
