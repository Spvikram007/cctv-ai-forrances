#!/usr/bin/env python3
"""
CCTV AI Intelligence Platform - Standalone Evidence Verification Utility.
Independent judicial verification tool for court clerks, defense counsel,
forensic examiners, and judicial auditors.
Requires standard Python 3.8+ with 'cryptography' package for authoritative verification.

Exit Codes:
  0: VERIFIED - Media hash matches, signature valid with trusted key, custody chain and checkpoints intact.
  1: FAILED - Tampering detected (hash mismatch, signature invalid, broken hash chain, or rewritten ledger).
  2: UNTRUSTED SIGNING IDENTITY - Public key is self-supplied by package and not present in trusted keystore.
  3: VERIFICATION INCOMPLETE - Missing required cryptographic dependencies or unreadable package files.
"""

import os
import sys
import json
import hashlib
import argparse
from pathlib import Path
from enum import Enum
from typing import Tuple, Optional, Dict, Any, List

try:
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.exceptions import InvalidSignature
    HAS_CRYPTOGRAPHY = True
except ImportError:
    HAS_CRYPTOGRAPHY = False


GENESIS_HASH = "0" * 64


class VerificationStatus(str, Enum):
    VERIFIED = "VERIFIED"
    FAILED = "FAILED"
    UNTRUSTED_SIGNING_IDENTITY = "UNTRUSTED SIGNING IDENTITY"
    VERIFICATION_INCOMPLETE = "VERIFICATION INCOMPLETE"

    def __bool__(self) -> bool:
        return self == VerificationStatus.VERIFIED


def compute_file_sha256(filepath: str) -> str:
    """Computes chunked SHA-256 hash of binary media file."""
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def compute_key_fingerprint(public_key_pem: str) -> Optional[str]:
    """Computes SHA-256 fingerprint of public key DER SubjectPublicKeyInfo."""
    if not HAS_CRYPTOGRAPHY:
        return None
    try:
        pub_key = serialization.load_pem_public_key(public_key_pem.encode("utf-8"))
        der_bytes = pub_key.public_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        return f"SHA256:{hashlib.sha256(der_bytes).hexdigest()}"
    except Exception:
        return None


def verify_chain_of_custody(ledger_path: str) -> Tuple[bool, int, Optional[str], List[Dict[str, Any]]]:
    """Verifies Merkle hash chaining of all events in the ledger."""
    if not os.path.exists(ledger_path):
        return True, 0, "No custody ledger present.", []

    expected_prev = GENESIS_HASH
    events = []
    with open(ledger_path, "r", encoding="utf-8") as f:
        for idx, line in enumerate(f):
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError as e:
                return False, len(events), f"Malformed JSON record at line {idx + 1}: {e}", events

            if event.get("prev_hash") != expected_prev:
                return False, len(events), f"Hash chain break at event {idx}: {event.get('prev_hash')[:16]} != {expected_prev[:16]}", events

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
            if recalculated != event.get("record_hash"):
                return False, len(events), f"Record content modified at event {idx}: {event.get('record_hash')[:16]} != {recalculated[:16]}", events

            expected_prev = event["record_hash"]
            events.append(event)

    return True, len(events), None, events


def verify_manifest_signature(manifest_dict: Dict[str, Any], public_key_pem: str) -> Tuple[Optional[bool], str]:
    """Cryptographically verifies the detached signature on the manifest."""
    if not HAS_CRYPTOGRAPHY:
        return None, "Mandatory 'cryptography' library not installed; asymmetric signature verification cannot proceed."

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
            "signer_identity": manifest_dict["signer_identity"],
            "key_id": manifest_dict.get("key_id", ""),
            "key_fingerprint": manifest_dict.get("key_fingerprint", ""),
            "signing_time_utc": manifest_dict["signing_time_utc"],
        }
        canonical_bytes = json.dumps(canonical_payload, sort_keys=True).encode("utf-8")
        signature_der = bytes.fromhex(manifest_dict["signature_hex"])
        pub_key.verify(signature_der, canonical_bytes, ec.ECDSA(hashes.SHA256()))
        return True, "ECDSA SECP256R1 signature is cryptographically VALID."
    except InvalidSignature:
        return False, "Digital signature verification FAILED: Manifest payload altered or key mismatch."
    except Exception as e:
        return False, f"Signature validation error: {e}"


def verify_checkpoints(
    checkpoints_path: str,
    events: List[Dict[str, Any]],
    trusted_keys: Optional[Dict[str, Dict[str, Any]]] = None,
    fallback_public_pem: Optional[str] = None,
) -> Tuple[bool, int, List[str]]:
    """Verifies that signed periodic checkpoints match ledger events."""
    if not os.path.exists(checkpoints_path):
        return True, 0, []

    try:
        with open(checkpoints_path, "r", encoding="utf-8") as f:
            cps = json.load(f)
    except Exception as e:
        return False, 0, [f"Could not read checkpoints file: {e}"]

    errors = []
    verified_count = 0
    for cp in cps:
        cp_fp = cp.get("key_fingerprint")
        signing_key_pem = None
        if trusted_keys and cp_fp in trusted_keys:
            signing_key_pem = trusted_keys[cp_fp].get("public_key_pem")
        elif fallback_public_pem:
            signing_key_pem = fallback_public_pem

        if HAS_CRYPTOGRAPHY and signing_key_pem and cp.get("signature_hex"):
            try:
                pub_key = serialization.load_pem_public_key(signing_key_pem.encode("utf-8"))
                d = {
                    "checkpoint_id": cp["checkpoint_id"],
                    "evidence_id": cp["evidence_id"],
                    "record_index": cp["record_index"],
                    "record_hash": cp["record_hash"],
                    "timestamp_utc": cp["timestamp_utc"],
                    "signer_identity": cp["signer_identity"],
                    "key_id": cp["key_id"],
                    "key_fingerprint": cp["key_fingerprint"],
                }
                c_bytes = json.dumps(d, sort_keys=True).encode("utf-8")
                sig_der = bytes.fromhex(cp["signature_hex"])
                pub_key.verify(sig_der, c_bytes, ec.ECDSA(hashes.SHA256()))
            except Exception as e:
                errors.append(f"Checkpoint '{cp.get('checkpoint_id')}' signature check failed: {e}")
                continue

        idx = cp.get("record_index", 0)
        if idx >= len(events):
            errors.append(f"Ledger truncated! Checkpoint requires index {idx}, but ledger has {len(events)} records.")
            continue

        if events[idx].get("record_hash") != cp.get("record_hash"):
            errors.append(
                f"Ledger history rewritten! Record {idx} hash '{events[idx].get('record_hash')[:16]}' "
                f"does not match signed checkpoint hash '{cp.get('record_hash')[:16]}'."
            )
            continue

        verified_count += 1

    return (len(errors) == 0), verified_count, errors


def load_trusted_keys(trust_store_path: Optional[str], trust_key_path: Optional[str]) -> Dict[str, Dict[str, Any]]:
    """Loads authoritative trusted keys and fingerprints from external files."""
    trusted: Dict[str, Dict[str, Any]] = {}

    if trust_key_path and os.path.exists(trust_key_path):
        try:
            with open(trust_key_path, "r", encoding="utf-8") as f:
                pem = f.read().strip()
            fp = compute_key_fingerprint(pem)
            if fp:
                trusted[fp] = {
                    "key_id": Path(trust_key_path).stem,
                    "fingerprint": fp,
                    "public_key_pem": pem,
                    "identity": "EXPLICIT_TRUSTED_FILE",
                    "status": "ACTIVE",
                }
        except Exception as e:
            print(f"[WARN] Failed to load trusted key file '{trust_key_path}': {e}")

    paths_to_try = []
    if trust_store_path:
        paths_to_try.append(Path(trust_store_path))
    else:
        default_local = Path("storage/evidence/trust_store/trusted_keys.json")
        if default_local.exists():
            paths_to_try.append(default_local)

    for p in paths_to_try:
        if p.exists():
            try:
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                keys_dict = data.get("keys", {})
                for fp, entry in keys_dict.items():
                    trusted[fp] = entry
            except Exception as e:
                print(f"[WARN] Failed to load trust store '{p}': {e}")

    return trusted


def verify_package(
    package_dir_or_file: str,
    trust_store_path: Optional[str] = None,
    trust_key_path: Optional[str] = None,
    external_checkpoints_path: Optional[str] = None,
    allow_untrusted_key: bool = False,
) -> VerificationStatus:
    """
    Main verification pipeline for .cctvevid packages and locker directories.
    Returns: VerificationStatus.
    """
    pkg = Path(package_dir_or_file)

    if pkg.is_file() and pkg.suffix.lower() in (".cctvevid", ".zip"):
        import tempfile
        import zipfile
        with tempfile.TemporaryDirectory() as tmp_extract:
            with zipfile.ZipFile(str(pkg), "r") as zf:
                zf.extractall(tmp_extract)
            return verify_package(
                tmp_extract,
                trust_store_path=trust_store_path,
                trust_key_path=trust_key_path,
                external_checkpoints_path=external_checkpoints_path,
                allow_untrusted_key=allow_untrusted_key,
            )

    manifest_p = pkg / "manifest.json"
    if not manifest_p.exists():
        print(f"[FAIL] manifest.json not found in {pkg}")
        return VerificationStatus.VERIFICATION_INCOMPLETE

    try:
        with open(manifest_p, "r", encoding="utf-8") as f:
            manifest = json.load(f)
    except Exception as e:
        print(f"[FAIL] Could not parse manifest.json: {e}")
        return VerificationStatus.VERIFICATION_INCOMPLETE

    media_name = manifest.get("file_name", "")
    media_p = pkg / media_name
    if not media_p.exists():
        print(f"[FAIL] Media file '{media_name}' not found in {pkg}")
        return VerificationStatus.FAILED

    print("================================================================================")
    print("           STANDALONE FORENSIC EVIDENCE VERIFICATION AUDIT")
    print("================================================================================")
    print(f" Evidence ID:        {manifest.get('evidence_id')}")
    print(f" Case Number:        {manifest.get('case_number')}")
    print(f" Evidence Type:      {manifest.get('evidence_type')}")
    print(f" File Name:          {manifest.get('file_name')}")
    print(f" Key ID:             {manifest.get('key_id', 'UNKNOWN')}")
    print(f" Expected SHA-256:   {manifest.get('file_sha256')}")

    # 1. SHA-256 Media Hashing
    actual_sha = compute_file_sha256(str(media_p))
    sha_pass = (actual_sha == manifest.get("file_sha256"))
    print(f" Computed SHA-256:   {actual_sha}")
    print(f" [1] SHA-256 HASH MATCH:         {'[PASSED]' if sha_pass else '[FAILED - CORRUPTED/TAMPERED]'}")

    # 2. Cryptographic Library Check
    if not HAS_CRYPTOGRAPHY:
        print(" [2] DIGITAL SIGNATURE:          [VERIFICATION INCOMPLETE]")
        print("     Details: Mandatory 'cryptography' library is not installed.")
        print("     Judicial verification cannot report PASSED without cryptographic signature validation.")
        print("================================================================================")
        print(" FINAL VERDICT: VERIFICATION INCOMPLETE (MISSING CRYPTOGRAPHY DEPENDENCIES).")
        print("================================================================================")
        return VerificationStatus.VERIFICATION_INCOMPLETE

    # 3. Public Key Trust & Fingerprint Validation
    package_pub_key = manifest.get("public_key_pem", "")
    if not package_pub_key and (pkg / "public_key.pem").exists():
        with open(pkg / "public_key.pem", "r", encoding="utf-8") as f:
            package_pub_key = f.read().strip()

    pkg_fingerprint = compute_key_fingerprint(package_pub_key)
    print(f" Key Fingerprint:    {pkg_fingerprint}")

    trusted_keys = load_trusted_keys(trust_store_path, trust_key_path)
    is_trusted_key = False
    trust_reason = "No authoritative trust store configured or key not found."

    if pkg_fingerprint in trusted_keys:
        t_entry = trusted_keys[pkg_fingerprint]
        if t_entry.get("status") == "ACTIVE":
            is_trusted_key = True
            trust_reason = f"Key trusted (ID: {t_entry.get('key_id')}, Identity: {t_entry.get('identity')})"
        else:
            trust_reason = f"Key was REVOKED/EXPIRED ({t_entry.get('status')})"

    print(f" [2] SIGNING IDENTITY TRUST:     {'[PASSED - TRUSTED]' if is_trusted_key else '[UNTRUSTED SIGNING IDENTITY]'}")
    print(f"     Details: {trust_reason}")

    # 4. Digital Signature Verification
    sig_pass, sig_msg = verify_manifest_signature(manifest, package_pub_key)
    print(f" [3] DIGITAL SIGNATURE INTEGRITY:{'[PASSED]' if sig_pass else '[FAILED - TAMPERED]'}")
    print(f"     Details: {sig_msg}")

    # 5. Chain of Custody Ledger Verification
    ledger_p = pkg / "chain_of_custody.jsonl"
    chain_pass, chain_count, chain_msg, events = verify_chain_of_custody(str(ledger_p))
    print(f" [4] CUSTODY LEDGER INTEGRITY:   {'[PASSED]' if chain_pass else '[FAILED - TAMPERED]'}")
    print(f"     Records Verified: {chain_count} events (Merkle Hash Chained)")
    if chain_msg:
        print(f"     Details: {chain_msg}")

    # 6. Periodic Signed Checkpoints Verification
    cp_p = external_checkpoints_path or (str(pkg / "checkpoints.json") if (pkg / "checkpoints.json").exists() else None)
    if cp_p and os.path.exists(cp_p):
        cp_pass, cp_count, cp_errors = verify_checkpoints(
            cp_p, events, trusted_keys=trusted_keys, fallback_public_pem=package_pub_key
        )
        print(f" [5] SIGNED CHECKPOINTS INTEGRITY:{'[PASSED]' if cp_pass else '[FAILED - REWRITTEN/TRUNCATED]'}")
        print(f"     Checkpoints Verified: {cp_count}")
        for err in cp_errors:
            print(f"     [!] {err}")
    else:
        cp_pass = True
        print(" [5] SIGNED CHECKPOINTS:         [NO INDEPENDENT CHECKPOINT FILE PROVIDED]")

    # 7. Judicial Classification Notice
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

    # 8. Final Verdict Determination
    if not sha_pass or not sig_pass or not chain_pass or not cp_pass:
        print(" FINAL VERDICT: EVIDENCE VERIFICATION FAILED (TAMPERING DETECTED).")
        print("================================================================================")
        return VerificationStatus.FAILED

    if not is_trusted_key and not allow_untrusted_key:
        print(" FINAL VERDICT: UNTRUSTED SIGNING IDENTITY.")
        print(" The media and manifest are internally consistent, but the signing key is NOT TRUSTED")
        print(" by an external keystore. A third party may have signed this evidence.")
        print(" Use --trust-store or --trust-key to supply an authoritative root certificate.")
        print("================================================================================")
        return VerificationStatus.UNTRUSTED_SIGNING_IDENTITY

    if is_trusted_key and sha_pass and sig_pass and chain_pass and cp_pass:
        print(" FINAL VERDICT: EVIDENCE IS CRYPTOGRAPHICALLY VALID AND AUTHENTIC.")
        print(" Byte-level media integrity, digital signature, and custody chain are VERIFIED.")
        print("================================================================================")
        return VerificationStatus.VERIFIED
    else:
        print(" FINAL VERDICT: UNTRUSTED SIGNING IDENTITY.")
        print("================================================================================")
        return VerificationStatus.UNTRUSTED_SIGNING_IDENTITY


def main():
    parser = argparse.ArgumentParser(
        description="Standalone Forensic Evidence Verification Utility (CCTV AI Intelligence Platform)",
        epilog=(
            'Example (paths with spaces):\n'
            '  python tools/verify_evidence.py "C:\\xampp\\htdocs\\cctv ai\\storage\\evidence\\export\\EVID-001.cctvevid" '
            '--trust-store "C:\\xampp\\htdocs\\cctv ai\\storage\\evidence\\trust_store\\trusted_keys.json"'
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("target", help="Path to evidence package (.cctvevid/.zip) or unzipped directory")
    parser.add_argument("--trust-store", help="Path to trusted_keys.json authoritative keystore", default=None)
    parser.add_argument("--trust-key", help="Path to trusted public_key.pem file", default=None)
    parser.add_argument("--checkpoints", help="Path to independent external checkpoints file", default=None)
    parser.add_argument(
        "--allow-untrusted-key",
        action="store_true",
        help="Allow verification against self-supplied package public key without failing on trust.",
    )
    args = parser.parse_args()

    status = verify_package(
        args.target,
        trust_store_path=args.trust_store,
        trust_key_path=args.trust_key,
        external_checkpoints_path=args.checkpoints,
        allow_untrusted_key=args.allow_untrusted_key,
    )

    if status == VerificationStatus.VERIFIED:
        sys.exit(0)
    elif status == VerificationStatus.FAILED:
        sys.exit(1)
    elif status == VerificationStatus.UNTRUSTED_SIGNING_IDENTITY:
        sys.exit(2)
    elif status == VerificationStatus.VERIFICATION_INCOMPLETE:
        sys.exit(3)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
