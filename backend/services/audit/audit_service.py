from sqlalchemy.ext.asyncio import AsyncSession

class AuditService:
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def log_action(self, user_id: int, action: str, entity_type: str, entity_id: int):
        # Implementation to be added later (requires AuditLog model)
        # print(f"AUDIT LOG: User {user_id} performed {action} on {entity_type} {entity_id}")
        pass
