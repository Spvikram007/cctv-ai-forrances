"""
Utility to recalculate audit hash chain with canonical timestamps.
"""
from database.database_manager import db_manager
from database.models.users import AuditLog
from core.security.audit_service import audit_service, canon_ts, GENESIS_HASH
import hashlib

def relink():
    with db_manager.get_session() as s:
        rows = s.query(AuditLog).filter(AuditLog.record_hash.isnot(None)).order_by(AuditLog.created_at.asc()).all()
        prev = GENESIS_HASH
        for r in rows:
            ts = canon_ts(r.created_at)
            uid = r.user_id if r.user_id else "none"
            uname = r.username if r.username else "system"
            rid = r.resource_id if r.resource_id else "none"
            cat = r.category if r.category else "SYSTEM"
            st = r.status if r.status else "SUCCESS"
            det = r.details_json if r.details_json else "{}"

            payload = f"{prev}:{ts}:{uid}:{uname}:{r.action}:{cat}:{r.resource_type}:{rid}:{st}:{det}"
            h = hashlib.sha256(payload.encode("utf-8")).hexdigest()
            r.prev_hash = prev
            r.record_hash = h
            prev = h
        s.commit()

    is_v, count, msg = audit_service.verify_audit_integrity()
    print(f"Audit chain re-sealed! Valid: {is_v}, Count: {count}, Msg: {msg}")

if __name__ == "__main__":
    relink()
