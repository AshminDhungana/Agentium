"""
One-time repair: the Head of Council (00001) was terminated by a reincarnation
cycle that minted a new ID (00002). Because ~90 code paths hardcode "00001" as
the canonical Head, the system now routes to a terminated agent.

This script revives 00001 in place (it still holds its capabilities + Ethos
wisdom from the cycle) and retires the redundant 00002.
"""
from datetime import datetime, timezone

from backend.models.database import SessionLocal
from backend.models.entities.agents import Agent, AgentStatus


def main():
    db = SessionLocal()
    try:
        head = db.query(Agent).filter_by(agentium_id="00001").first()
        twin = db.query(Agent).filter_by(agentium_id="00002").first()

        if head is None:
            print("ERROR: 00001 not found — aborting.")
            return

        # Revive 00001 in place.
        head.status = AgentStatus.ACTIVE
        head.is_active = True
        head.terminated_at = None
        head.termination_reason = None
        head.current_task_id = None
        prev_inc = head.incarnation_number or 1
        head.incarnation_number = prev_inc + 1
        print(f"00001 ({head.name}) revived -> status={head.status.value}, "
              f"incarnation {prev_inc} -> {head.incarnation_number}")

        # Retire the redundant 00002 (has 0 subordinates / 0 tasks per dashboard).
        if twin is not None:
            # Safety: reassign any children/tasks back to 00001 first.
            children = db.query(Agent).filter_by(parent_id=twin.id).all()
            for child in children:
                child.parent_id = head.id
            twin.status = AgentStatus.TERMINATED
            twin.is_active = False
            twin.terminated_at = datetime.now(timezone.utc)
            twin.termination_reason = (
                "Retired: redundant Head spawn from pre-fix reincarnation cycle; "
                "00001 revived in place."
            )
            twin.current_task_id = None
            print(f"00002 ({twin.name}) retired -> status={twin.status.value}, "
                  f"reassigned {len(children)} children to 00001")

        db.commit()
        print("REPAIR COMPLETE.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
