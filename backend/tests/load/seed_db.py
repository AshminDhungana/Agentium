import os
import sys

# Ensure backend can be imported
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../")))

from backend.models.database import init_db, get_db_context
from backend.models.entities.user import User
from backend.models.entities.agents import Agent, CouncilMember, AgentType, AgentStatus

def seed():
    print("Initializing database...")
    init_db()
    
    with get_db_context() as db:
        print("Checking default admin...")
        admin = db.query(User).filter(User.username == "admin").first()
        if not admin:
            admin = User.create_user(
                db=db,
                username="admin",
                email="admin@agentium.local",
                password="admin",
                is_admin=True,
                is_active=True,
                is_pending=False,
            )
            print("Default admin created.")
        else:
            admin.is_active = True
            admin.is_pending = False
            admin.is_admin = True
            print("Default admin updated/verified.")
            
        print("Checking default agents...")
        agent1 = db.query(Agent).filter_by(agentium_id="10003").first()
        if not agent1:
            agent1 = CouncilMember(
                agentium_id="10003",
                name="Agent 10003",
                status=AgentStatus.ACTIVE,
            )
            db.add(agent1)
            print("Agent 10003 created.")
            
        agent2 = db.query(Agent).filter_by(agentium_id="10004").first()
        if not agent2:
            agent2 = CouncilMember(
                agentium_id="10004",
                name="Agent 10004",
                status=AgentStatus.ACTIVE,
            )
            db.add(agent2)
            print("Agent 10004 created.")
            
        db.commit()
    print("Database seeding completed successfully.")

if __name__ == "__main__":
    seed()
