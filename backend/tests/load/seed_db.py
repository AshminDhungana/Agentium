import os
import sys
import json

# Ensure backend can be imported
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../")))

from backend.models.database import init_db, get_db_context
from backend.models.entities.user import User
from backend.models.entities.agents import (
    Agent,
    CouncilMember,
    HeadOfCouncil,
    LeadAgent,
    AgentType,
    AgentStatus,
)
from backend.models.entities.constitution import Ethos
from backend.services.reincarnation_service import reincarnation_service
from sqlalchemy.orm import Session


async def create_genesis_agents(db: Session) -> dict:
    """
    Create minimal genesis agents for testing (CI load tests).

    Creates: Head 00001, Council 10001/10002, Lead 20001.
    Only runs when TESTING=true. Idempotent.
    """
    result = {"head": None, "council": [], "lead": None}

    # ── Head 00001 ──────────────────────────────────────────────
    head = db.query(HeadOfCouncil).filter_by(agentium_id="00001", is_active=True).first()
    if not head:
        head = HeadOfCouncil(
            agentium_id="00001",
            name="Head of Council Prime",
            description="The supreme authority of Agentium. Eternal and persistent.",
            status=AgentStatus.ACTIVE,
            is_active=True,
            is_persistent=True,
            idle_mode_enabled=True,
            constitution_version="v1.0.0"
        )
        db.add(head)
        db.flush()

        # Create minimal ethos for Head (required for auth path)
        head_ethos = Ethos(
            agentium_id="E00001",
            agent_type="head_of_council",
            mission_statement="Supreme executive authority of Agentium for testing.",
            core_values=json.dumps(["Constitutional Fidelity", "Sovereign Loyalty"]),
            behavioral_rules=json.dumps(["Read Constitution before tasks"]),
            restrictions=json.dumps(["Cannot violate Constitution"]),
            capabilities=json.dumps(["Full governance authority"]),
            created_by_agentium_id="00001",
            agent_id=head.id,
            is_verified=True,
            verified_by_agentium_id="00001"
        )
        db.add(head_ethos)
        db.flush()
        head.ethos_id = head_ethos.id
        db.flush()

        result["head"] = head
    else:
        result["head"] = head

    # ── Council Members 10001, 10002 ───────────────────────────
    specializations = ["Constitutional Law", "System Security"]
    for i in range(2):
        agentium_id = f"1{i+1:04d}"  # 10001, 10002
        member = db.query(CouncilMember).filter_by(agentium_id=agentium_id, is_active=True).first()
        if not member:
            member = CouncilMember(
                agentium_id=agentium_id,
                name=f"Council Member {i+1}",
                description=f"Founding Council Member {i+1}",
                status=AgentStatus.ACTIVE,
                is_active=True,
                parent_id=head.id,
                specialization=specializations[i]
            )
            db.add(member)
            db.flush()

            # Create minimal ethos for Council
            member_ethos = Ethos(
                agentium_id=f"E{agentium_id}",
                agent_type="council_member",
                mission_statement=f"Council Member {i+1} — specialist in {specializations[i]}.",
                core_values=json.dumps(["Democratic Deliberation", "Constitutional Compliance"]),
                behavioral_rules=json.dumps(["Vote on amendments", "Monitor compliance"]),
                restrictions=json.dumps(["Cannot unilaterally approve amendments"]),
                capabilities=json.dumps(["Voting rights", "Oversight access"]),
                created_by_agentium_id="00001",
                agent_id=member.id,
                is_verified=True,
                verified_by_agentium_id="00001"
            )
            db.add(member_ethos)
            db.flush()
            member.ethos_id = member_ethos.id
            db.flush()

        result["council"].append(member)

    # ── Lead Agent 20001 ────────────────────────────────────────
    lead = db.query(LeadAgent).filter_by(agentium_id="20001", is_active=True).first()
    if not lead:
        lead = reincarnation_service.spawn_lead_agent(
            parent=head,
            name="Prime Lead",
            description="Default Lead Agent seeded for CI load testing.",
            db=db
        )
        # Override agentium_id to 20001 if different
        if lead.agentium_id != "20001":
            lead.agentium_id = "20001"
        db.flush()
        result["lead"] = lead
    else:
        result["lead"] = lead

    # Commit so agents are visible to other DB sessions (WebSocket handler)
    db.commit()

    return result

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

    # Create genesis agents for CI load testing when TESTING=true
    if os.environ.get("TESTING") == "true":
        print("TESTING=true detected — creating genesis agents for CI load test...")
        import asyncio
        with get_db_context() as db:
            asyncio.run(create_genesis_agents(db))
        print("Genesis agents created successfully.")

    print("Database seeding completed successfully.")

if __name__ == "__main__":
    seed()
