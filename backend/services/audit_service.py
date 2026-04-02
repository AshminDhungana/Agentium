from typing import List, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import desc
from backend.models.entities.audit import AuditLog, AuditCategory, AuditLevel

class AuditService:
    @staticmethod
    def get_escalations(
        db: Session,
        skip: int = 0,
        limit: int = 100,
        search: Optional[str] = None
    ) -> Tuple[List[AuditLog], int]:
        """Fetch privilege escalation/revocation events."""
        query = db.query(AuditLog).filter(
            AuditLog.category == AuditCategory.AUTHORIZATION,
            AuditLog.action.in_(["privilege_escalation", "privilege_revocation"])
        )

        if search:
            search_term = f"%{search}%"
            query = query.filter(
                (AuditLog.actor_id.ilike(search_term)) |
                (AuditLog.target_id.ilike(search_term)) |
                (AuditLog.description.ilike(search_term))
            )

        total = query.count()
        logs = query.order_by(desc(AuditLog.created_at)).offset(skip).limit(limit).all()
        
        return logs, total

