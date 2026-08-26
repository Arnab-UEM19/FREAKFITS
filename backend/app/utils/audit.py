import logging
from sqlalchemy.orm import Session
from ..models import AdminAuditLog

logger = logging.getLogger("uvicorn.error")

def log_admin_action(db: Session, admin_identifier: str, action: str, target_type: str, target_id: str, details: dict = None):
    """
    Log an administrative action to the audit trail.
    """
    try:
        audit_log = AdminAuditLog(
            admin_identifier=admin_identifier,
            action=action,
            target_type=target_type,
            target_id=target_id,
            details=details or {}
        )
        db.add(audit_log)
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to write admin audit log: {e}")
