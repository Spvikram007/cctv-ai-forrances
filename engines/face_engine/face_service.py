"""
Authorized Face Intelligence Service and Privacy Management Engine.
Enforces authorized-only identity enrollment, AES-256 template encryption,
cosine similarity verification, human review workflows, and comprehensive biometric audit logging.
"""

import os
import time
import json
import threading
from typing import Optional, List, Dict, Tuple, Any
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
import shutil
from pathlib import Path

import cv2
import numpy as np

from database.database_manager import db_manager
from database.models.biometrics import (
    FaceIdentity,
    FaceTemplate,
    FaceEnrollment,
    FaceMatchEvent,
    BiometricAuditLog,
)
from core.events.event_bus import bus
from core.config.settings import settings
from core.logging.logger import get_logger
from engines.face_engine.face_detector import FaceDetector, DetectedFace, FaceQuality
from engines.face_engine.face_embedder import FaceEmbedder
from engines.face_engine.face_vault import FaceBiometricVault

logger = get_logger("face_service")


@dataclass
class FaceMatchCandidate:
    identity_id: str
    name: str
    category: str
    similarity_score: float
    threshold_applied: float
    face_bbox: Tuple[int, int, int, int]
    snapshot_path: Optional[str]
    is_verified: bool = False
    timestamp: float = 0.0


class FaceIntelligenceService:
    """
    Central Face Intelligence Engine.
    Strictly restricted to authorized enrolled identities.
    Never identifies arbitrary persons without an authorized enrolled biometric template.
    """

    _instance: Optional["FaceIntelligenceService"] = None
    _lock = threading.Lock()

    ROLE_PERMISSIONS: Dict[str, set] = {
        "ADMIN": {
            "ENROLL_IDENTITY",
            "REVOKE_IDENTITY",
            "ROTATE_KEYS",
            "PURGE_RETENTION",
            "VERIFY_MATCH",
            "VIEW_AUDIT_LOGS",
        },
        "SECURITY_OPERATOR": {
            "ENROLL_IDENTITY",
            "VERIFY_MATCH",
        },
        "AUDITOR": {
            "VIEW_AUDIT_LOGS",
        },
        "VIEWER": set(),
    }

    @classmethod
    def check_rbac_permission(cls, user_role: Optional[str], action: str) -> Tuple[bool, str]:
        """
        Validates whether the user's role possesses authorization for the biometric action.
        Defaults to ADMIN if role is not supplied (e.g. system background processes).
        """
        role = (user_role or "ADMIN").upper()
        if role not in cls.ROLE_PERMISSIONS:
            return False, f"Unknown user role: '{role}'"

        allowed_actions = cls.ROLE_PERMISSIONS[role]
        if action not in allowed_actions:
            return False, f"Role '{role}' is not authorized to perform biometric action '{action}'"

        return True, ""

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(
        self,
        recording_manager=None,
        persist_to_db: bool = True,
        snapshots_dir: Optional[str] = None,
        default_threshold: float = 0.65,
    ) -> None:
        if getattr(self, "_initialized", False):
            return

        self.recording_manager = recording_manager
        self.persist_to_db = persist_to_db
        self.snapshots_dir = snapshots_dir or settings.storage.snapshots_dir
        self.default_threshold = default_threshold

        self.detector = FaceDetector()
        self.embedder = FaceEmbedder()

        # In-memory template cache: identity_id -> (name, category, embedding_512)
        self._enrolled_templates: Dict[str, Tuple[str, str, np.ndarray]] = {}
        self._cache_lock = threading.Lock()
        self._initialized = True
        self.reload_enrolled_templates()

    def set_recording_manager(self, mgr) -> None:
        self.recording_manager = mgr

    def reload_enrolled_templates(self) -> int:
        """
        Loads all active, unrevoked face templates from database into memory,
        decrypting them via the AES-256 biometric vault.
        """
        loaded_count = 0
        try:
            with db_manager.get_session() as session:
                active_templates = (
                    session.query(FaceTemplate)
                    .join(FaceIdentity)
                    .filter(
                        FaceTemplate.is_revoked == False,
                        FaceIdentity.is_active == True,
                        FaceIdentity.is_deleted == False,
                    )
                    .all()
                )

                with self._cache_lock:
                    self._enrolled_templates.clear()
                    for tmpl in active_templates:
                        try:
                            emb = FaceBiometricVault.decrypt_template(tmpl.encrypted_template)
                            self._enrolled_templates[tmpl.identity_id] = (
                                tmpl.identity.name,
                                tmpl.identity.category,
                                emb,
                            )
                            loaded_count += 1
                        except Exception as dec_err:
                            logger.error("Failed to decrypt biometric template %s: %s", tmpl.id, dec_err)

            logger.info("Face Intelligence: %d authorized identities loaded into cache.", loaded_count)
        except Exception as e:
            logger.error("Failed to load enrolled face templates: %s", e)

        return loaded_count

    def enroll_identity(
        self,
        name: str,
        identity_code: str,
        category: str,
        face_image_bgr: np.ndarray,
        enrolled_by_user_id: Optional[str] = None,
        department: Optional[str] = None,
        authorization_ref: Optional[str] = None,
        valid_until: Optional[datetime] = None,
        user_role: Optional[str] = None,
    ) -> Tuple[bool, str]:
        """
        Enrolls an authorized individual into the biometric catalog.
        Validates quality, extracts 512-d embedding, encrypts with AES-256, and logs audit record.
        Enforces RBAC authorization checks.
        """
        # RBAC Check
        allowed, err_msg = self.check_rbac_permission(user_role, "ENROLL_IDENTITY")
        if not allowed:
            return False, f"RBAC access denied: {err_msg}"

        if face_image_bgr is None or face_image_bgr.size == 0:
            return False, "Invalid face image (empty image data)"

        # 1. Quality Check
        quality = self.detector.assess_quality(face_image_bgr)
        if not quality.is_acceptable:
            return False, f"Enrollment rejected due to low biometric quality: {quality.rejection_reason}"

        # 2. Extract Embedding
        aligned = cv2.resize(face_image_bgr, (112, 112))
        embedding = self.embedder.extract_embedding(aligned)

        # 3. Encrypt Embedding
        try:
            encrypted_hex = FaceBiometricVault.encrypt_template(embedding)
        except Exception as e:
            return False, f"Encryption failure: {e}"

        # 4. Database Persistence
        try:
            now_dt = datetime.now(timezone.utc)
            with db_manager.get_session() as session:
                # Check for existing code
                existing = session.query(FaceIdentity).filter_by(identity_code=identity_code).first()
                if existing:
                    return False, f"Identity code '{identity_code}' is already registered."

                identity = FaceIdentity(
                    name=name,
                    identity_code=identity_code,
                    category=category,
                    department=department,
                    is_active=True,
                )
                session.add(identity)
                session.flush()  # Generate identity.id
                saved_id = str(identity.id)

                template = FaceTemplate(
                    identity_id=saved_id,
                    encrypted_template=encrypted_hex,
                    algorithm="MobileFaceNet-512",
                    vector_dim=512,
                    quality_score=quality.overall_quality,
                    is_revoked=False,
                )
                session.add(template)

                enrollment = FaceEnrollment(
                    identity_id=saved_id,
                    enrolled_by_user_id=enrolled_by_user_id,
                    status="APPROVED",
                    authorization_ref=authorization_ref,
                    valid_until=valid_until,
                )
                session.add(enrollment)

                # Log biometric audit entry
                audit = BiometricAuditLog(
                    user_id=enrolled_by_user_id,
                    action="ENROLL_IDENTITY",
                    identity_id=saved_id,
                    template_id=template.id,
                    details_json=json.dumps({
                        "name": name,
                        "code": identity_code,
                        "quality": quality.overall_quality,
                        "auth_ref": authorization_ref,
                    }),
                    timestamp=now_dt,
                )
                session.add(audit)
                session.commit()

                # Update in-memory cache
                with self._cache_lock:
                    self._enrolled_templates[saved_id] = (name, category, embedding)

            logger.info("Successfully enrolled authorized identity '%s' [%s].", name, identity_code)
            return True, saved_id
        except Exception as e:
            logger.error("Database error during identity enrollment: %s", e)
            return False, f"Database persistence error: {e}"

    def revoke_identity(
        self,
        identity_id: str,
        reason: str,
        revoked_by_user_id: Optional[str] = None,
        user_role: Optional[str] = None,
    ) -> bool:
        """
        Permanently revokes an identity's biometric template.
        Enforces RBAC authorization checks.
        """
        # RBAC Check
        allowed, err_msg = self.check_rbac_permission(user_role, "REVOKE_IDENTITY")
        if not allowed:
            logger.warning("Revoke identity denied: %s", err_msg)
            return False

        try:
            now_dt = datetime.now(timezone.utc)
            with db_manager.get_session() as session:
                identity = session.query(FaceIdentity).filter_by(id=identity_id).first()
                if not identity:
                    return False

                identity.is_active = False

                for tmpl in identity.templates:
                    tmpl.is_revoked = True
                    tmpl.revoked_at = now_dt
                    tmpl.revocation_reason = reason

                audit = BiometricAuditLog(
                    user_id=revoked_by_user_id,
                    action="REVOKE_IDENTITY",
                    identity_id=identity_id,
                    details_json=json.dumps({"reason": reason}),
                    timestamp=now_dt,
                )
                session.add(audit)
                session.commit()

            with self._cache_lock:
                self._enrolled_templates.pop(identity_id, None)

            logger.info("Revoked face template for identity %s (Reason: %s).", identity_id, reason)
            return True
        except Exception as e:
            logger.error("Failed to revoke identity: %s", e)
            return False

    def evaluate_faces(
        self,
        channel_id: str,
        frame_bgr: np.ndarray,
        threshold: Optional[float] = None,
        timestamp: Optional[float] = None,
    ) -> List[FaceMatchCandidate]:
        """
        Scans frame for faces and evaluates them STRICTLY against enrolled authorized identities.
        Un-enrolled faces are NOT identified.
        """
        if frame_bgr is None or frame_bgr.size == 0:
            return []

        active_thresh = threshold or self.default_threshold
        now = timestamp or time.time()
        matches: List[FaceMatchCandidate] = []

        # 1. Detect Faces
        detected = self.detector.detect_faces(frame_bgr)
        if not detected:
            return []

        # Check if any templates are enrolled
        with self._cache_lock:
            if not self._enrolled_templates:
                return []
            enrolled_items = list(self._enrolled_templates.items())

        for face in detected:
            if not face.quality.is_acceptable:
                continue

            # 2. Extract Embedding
            probe_emb = self.embedder.extract_embedding(face.aligned_face)

            # 3. Match against enrolled authorized identities
            best_id: Optional[str] = None
            best_name = "Unknown"
            best_cat = "UNKNOWN"
            best_sim = 0.0

            for ident_id, (name, cat, enrolled_emb) in enrolled_items:
                sim = self.embedder.compute_similarity(probe_emb, enrolled_emb)
                if sim > best_sim:
                    best_sim = sim
                    best_id = ident_id
                    best_name = name
                    best_cat = cat

            # 4. Check Threshold (Zero proof of identity - candidate match requires human review)
            if best_id and best_sim >= active_thresh:
                # Save snapshot
                snap_path = self._save_face_snapshot(channel_id, face.aligned_face, best_name, now)

                # Persist event to DB
                if self.persist_to_db:
                    self._persist_match_event(
                        channel_id=channel_id,
                        identity_id=best_id,
                        name=best_name,
                        category=best_cat,
                        similarity=best_sim,
                        threshold=active_thresh,
                        snap_path=snap_path,
                        bbox=face.bbox,
                        timestamp=now,
                    )

                candidate = FaceMatchCandidate(
                    identity_id=best_id,
                    name=best_name,
                    category=best_cat,
                    similarity_score=best_sim,
                    threshold_applied=active_thresh,
                    face_bbox=face.bbox,
                    snapshot_path=snap_path,
                    is_verified=False,  # Human verification required
                    timestamp=now,
                )
                matches.append(candidate)

                # Dispatch Alert to EventBus
                bus.publish("face.candidate_match", {
                    "channel_id": channel_id,
                    "identity_id": best_id,
                    "candidate_name": best_name,
                    "category": best_cat,
                    "similarity": round(best_sim, 3),
                    "threshold": active_thresh,
                    "is_verified": False,
                    "snapshot_path": snap_path,
                    "timestamp": now,
                }, source=f"face:{channel_id}")

                # If watchlist alert, trigger video recording
                if best_cat == "WATCHLIST_ALERT" and self.recording_manager:
                    try:
                        self.recording_manager.trigger_event_recording(
                            channel_id=channel_id,
                            event_type="FACE_WATCHLIST",
                            pre_event_sec=5,
                            post_event_sec=20,
                        )
                    except Exception as e:
                        logger.debug("Failed to trigger face recording: %s", e)

        return matches

    def _save_face_snapshot(
        self,
        channel_id: str,
        face_aligned: np.ndarray,
        name: str,
        timestamp: float,
    ) -> Optional[str]:
        try:
            dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
            folder = Path(self.snapshots_dir) / channel_id / "face" / dt.strftime("%Y%m%d")
            folder.mkdir(parents=True, exist_ok=True)

            clean_name = "".join(c for c in name if c.isalnum())
            filename = f"face_{clean_name}_{dt.strftime('%H%M%S_%f')[:-3]}.jpg"
            path = folder / filename
            cv2.imwrite(str(path), face_aligned)
            return str(path.resolve())
        except Exception as e:
            logger.error("Failed to save face match snapshot: %s", e)
            return None

    def _persist_match_event(
        self,
        channel_id: str,
        identity_id: str,
        name: str,
        category: str,
        similarity: float,
        threshold: float,
        snap_path: Optional[str],
        bbox: Tuple[int, int, int, int],
        timestamp: float,
    ) -> None:
        try:
            dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
            with db_manager.get_session() as session:
                ev = FaceMatchEvent(
                    channel_id=channel_id,
                    identity_id=identity_id,
                    candidate_name=name,
                    category=category,
                    similarity_score=similarity,
                    threshold_applied=threshold,
                    snapshot_path=snap_path,
                    face_bbox_json=json.dumps(list(bbox)),
                    is_verified=False,
                    timestamp=dt,
                )
                session.add(ev)
                session.commit()
        except Exception as e:
            logger.error("Failed to persist face match event: %s", e)

    def verify_match_event(
        self,
        event_id: str,
        verified_by_user_id: str,
        is_confirmed: bool = True,
        user_role: Optional[str] = None,
    ) -> bool:
        """
        Human operator verification workflow for biometric candidate match.
        Enforces RBAC verification authorization.
        """
        # RBAC Check
        allowed, err_msg = self.check_rbac_permission(user_role, "VERIFY_MATCH")
        if not allowed:
            logger.warning("Verify match event denied: %s", err_msg)
            return False

        try:
            now_dt = datetime.now(timezone.utc)
            with db_manager.get_session() as session:
                ev = session.query(FaceMatchEvent).filter_by(id=event_id).first()
                if not ev:
                    return False

                ev.is_verified = is_confirmed
                ev.verified_by_user_id = verified_by_user_id
                ev.verified_at = now_dt

                audit = BiometricAuditLog(
                    user_id=verified_by_user_id,
                    action="VERIFY_CANDIDATE_MATCH",
                    identity_id=ev.identity_id,
                    details_json=json.dumps({"event_id": event_id, "confirmed": is_confirmed}),
                    timestamp=now_dt,
                )
                session.add(audit)
                session.commit()
            return True
        except Exception as e:
            logger.error("Verification update error: %s", e)
            return False

    def rotate_biometric_keys(
        self,
        user_role: Optional[str] = "ADMIN",
        user_id: Optional[str] = "admin",
    ) -> Tuple[bool, str]:
        """
        Rotates the AES-256 DPAPI master key and re-encrypts all stored biometric templates.
        Enforces strict ADMIN RBAC authorization and logs an immutable audit event.
        """
        allowed, err_msg = self.check_rbac_permission(user_role, "ROTATE_KEYS")
        if not allowed:
            return False, f"RBAC access denied: {err_msg}"

        try:
            now_dt = datetime.now(timezone.utc)
            with db_manager.get_session() as session:
                templates = session.query(FaceTemplate).all()
                decrypted_pairs: List[Tuple[FaceTemplate, np.ndarray]] = []

                # 1. Decrypt all existing templates under current key
                for tmpl in templates:
                    try:
                        emb = FaceBiometricVault.decrypt_template(tmpl.encrypted_template)
                        decrypted_pairs.append((tmpl, emb))
                    except Exception as dec_err:
                        logger.warning("Skipping undecryptable historical template %s during key rotation: %s", tmpl.id, dec_err)

                # 2. Rotate master key in vault
                new_key = FaceBiometricVault.rotate_master_key()

                # 3. Re-encrypt all templates under new key
                for tmpl, emb in decrypted_pairs:
                    tmpl.encrypted_template = FaceBiometricVault.encrypt_template(emb)

                # 4. Audit Log
                audit = BiometricAuditLog(
                    user_id=user_id,
                    action="ROTATE_MASTER_KEY",
                    details_json=json.dumps({
                        "re_encrypted_count": len(decrypted_pairs),
                        "key_version": FaceBiometricVault._active_key_version,
                    }),
                    timestamp=now_dt,
                )
                session.add(audit)
                session.commit()

            # 5. Reload in-memory cache
            self.reload_enrolled_templates()
            logger.info("Successfully completed biometric key rotation: %d templates re-encrypted.", len(decrypted_pairs))
            return True, f"Successfully rotated key and re-encrypted {len(decrypted_pairs)} biometric templates."
        except Exception as e:
            logger.error("Biometric key rotation failed: %s", e)
            return False, f"Key rotation error: {e}"

    def enforce_retention_policy(
        self,
        retention_days: int = 30,
        purge_expired_enrollments: bool = True,
        user_role: Optional[str] = "ADMIN",
        user_id: Optional[str] = "system",
    ) -> Dict[str, int]:
        """
        Enforces biometric privacy retention compliance:
        - Deactivates expired enrollments (valid_until < now).
        - Purges match events older than retention_days along with snapshot files.
        - Records immutable audit log.
        """
        allowed, err_msg = self.check_rbac_permission(user_role, "PURGE_RETENTION")
        if not allowed:
            logger.warning("Retention enforcement denied: %s", err_msg)
            return {"error": -1, "expired_enrollments_deactivated": 0, "match_events_purged": 0, "snapshots_deleted": 0}

        counts = {
            "expired_enrollments_deactivated": 0,
            "match_events_purged": 0,
            "snapshots_deleted": 0,
        }

        try:
            now_dt = datetime.now(timezone.utc)
            cutoff_dt = now_dt - timedelta(days=retention_days)

            with db_manager.get_session() as session:
                # 1. Expired Enrollments
                if purge_expired_enrollments:
                    expired_enrollments = (
                        session.query(FaceEnrollment)
                        .filter(
                            FaceEnrollment.valid_until != None,
                            FaceEnrollment.valid_until < now_dt,
                            FaceEnrollment.status == "APPROVED",
                        )
                        .all()
                    )
                    for enr in expired_enrollments:
                        enr.status = "EXPIRED"
                        if enr.identity:
                            enr.identity.is_active = False
                            for tmpl in enr.identity.templates:
                                tmpl.is_revoked = True
                                tmpl.revocation_reason = "RETENTION_POLICY_EXPIRED"
                        counts["expired_enrollments_deactivated"] += 1

                # 2. Old Match Events & Snapshots
                old_events = (
                    session.query(FaceMatchEvent)
                    .filter(FaceMatchEvent.timestamp < cutoff_dt)
                    .all()
                )

                for ev in old_events:
                    if ev.snapshot_path and os.path.exists(ev.snapshot_path):
                        try:
                            os.remove(ev.snapshot_path)
                            counts["snapshots_deleted"] += 1
                        except OSError as os_err:
                            logger.debug("Could not remove snapshot file %s: %s", ev.snapshot_path, os_err)
                    session.delete(ev)
                    counts["match_events_purged"] += 1

                # 3. Audit Log
                audit = BiometricAuditLog(
                    user_id=user_id,
                    action="ENFORCE_RETENTION_POLICY",
                    details_json=json.dumps({
                        "retention_days": retention_days,
                        "expired_deactivated": counts["expired_enrollments_deactivated"],
                        "events_purged": counts["match_events_purged"],
                        "snapshots_deleted": counts["snapshots_deleted"],
                    }),
                    timestamp=now_dt,
                )
                session.add(audit)
                session.commit()

            # Refresh cache if identities were deactivated
            if counts["expired_enrollments_deactivated"] > 0:
                self.reload_enrolled_templates()

            logger.info("Biometric Retention Enforced: %s", counts)
            return counts
        except Exception as e:
            logger.error("Biometric retention policy enforcement failed: %s", e)
            return counts


face_intelligence_service = FaceIntelligenceService()
