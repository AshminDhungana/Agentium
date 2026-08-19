"""
Integration tests for Voting, TaskDeliberation, AmendmentVoting, and IndividualVote models (3.3.8).
Verifies voting processes, quorum thresholds, supermajority requirements, vote changes, and tally logic.
"""
import pytest
import json
from backend.models.entities.voting import (
    AmendmentVoting, TaskDeliberation, IndividualVote, VotingRecord,
    VoteType, AmendmentStatus, DeliberationStatus
)
from backend.models.entities.task import TaskStatus
from backend.models.entities.agents import Agent, AgentType, AgentStatus


def test_amendment_voting_cast_and_tally(db_session, sample_amendment_voting, sample_council_member):
    """Verify casting votes on AmendmentVoting updates counters correctly."""
    sample_amendment_voting.start_voting()
    db_session.commit()

    assert sample_amendment_voting.status == AmendmentStatus.VOTING

    # Cast FOR vote
    vote1 = sample_amendment_voting.cast_vote(
        council_member_id=sample_council_member.agentium_id,
        vote=VoteType.FOR,
        rationale="Strongly support this amendment.",
    )
    db_session.commit()

    assert sample_amendment_voting.votes_for == 1
    assert sample_amendment_voting.votes_against == 0
    assert vote1.vote == VoteType.FOR
    assert vote1.voter_agentium_id == sample_council_member.agentium_id


def test_amendment_voting_supermajority_pass(db_session, sample_constitution):
    """Verify supermajority calculation (>=66%) passes amendment when quorum met."""
    voters = ["10001", "10002", "10003"]
    voting = AmendmentVoting(
        agentium_id="AV99001",
        amendment_id=sample_constitution.id,
        status=AmendmentStatus.VOTING,
        eligible_voters=json.dumps(voters),
        required_votes=2,
        supermajority_threshold=66,
        proposed_by_agentium_id="00001",
        proposed_changes="Amendment text",
        rationale="Rationale text",
        discussion_thread=[],
    )
    db_session.add(voting)
    db_session.commit()

    # 2 FOR out of 3 = 66.6% -> PASSED
    voting.cast_vote("10001", VoteType.FOR, "Yes")
    voting.cast_vote("10002", VoteType.FOR, "Yes")
    voting.cast_vote("10003", VoteType.AGAINST, "No")
    db_session.commit()

    res = voting.conclude()
    db_session.commit()

    assert res["result"] == "passed"
    assert voting.status == AmendmentStatus.PASSED
    assert voting.final_result == "passed"


def test_amendment_voting_quorum_failure(db_session, sample_constitution):
    """Verify participation < 60% results in REJECTED due to lack of quorum."""
    voters = ["10001", "10002", "10003", "10004", "10005"]  # 5 eligible
    voting = AmendmentVoting(
        agentium_id="AV99002",
        amendment_id=sample_constitution.id,
        status=AmendmentStatus.VOTING,
        eligible_voters=json.dumps(voters),
        required_votes=3,
        supermajority_threshold=66,
        proposed_by_agentium_id="00001",
        proposed_changes="Low quorum amendment",
        rationale="Rationale",
        discussion_thread=[],
    )
    db_session.add(voting)
    db_session.commit()

    # Only 2 out of 5 vote (40% participation < 60% quorum)
    voting.cast_vote("10001", VoteType.FOR, "Yes")
    voting.cast_vote("10002", VoteType.FOR, "Yes")
    db_session.commit()

    res = voting.conclude()
    db_session.commit()

    assert res["result"] == "rejected"
    assert voting.status == AmendmentStatus.REJECTED


def test_amendment_voting_vote_change(db_session, sample_amendment_voting, sample_council_member):
    """Verify changing a vote decrements previous counter and increments new counter."""
    sample_amendment_voting.start_voting()
    db_session.commit()

    # Vote FOR
    sample_amendment_voting.cast_vote(sample_council_member.agentium_id, VoteType.FOR, "Initial yes")
    db_session.commit()
    assert sample_amendment_voting.votes_for == 1
    assert sample_amendment_voting.votes_against == 0

    # Change vote to AGAINST
    sample_amendment_voting.cast_vote(sample_council_member.agentium_id, VoteType.AGAINST, "Changed to no")
    db_session.commit()

    assert sample_amendment_voting.votes_for == 0
    assert sample_amendment_voting.votes_against == 1


def test_task_deliberation_approve_flow(db_session, sample_task_deliberation, sample_council_member, sample_lead_agent):
    """Verify TaskDeliberation approval flow and task status update."""
    sample_task_deliberation.start()
    sample_task_deliberation.task.status = TaskStatus.DELIBERATING
    db_session.commit()

    assert sample_task_deliberation.status == DeliberationStatus.ACTIVE

    sample_task_deliberation.cast_vote(sample_council_member.agentium_id, VoteType.FOR, "Approve task")
    sample_task_deliberation.cast_vote(sample_lead_agent.agentium_id, VoteType.FOR, "Approve task")
    db_session.commit()

    assert sample_task_deliberation.status == DeliberationStatus.QUORUM_REACHED

    res = sample_task_deliberation.conclude()
    db_session.commit()

    assert res["decision"] == "approved"
    assert sample_task_deliberation.final_decision == "approved"
    assert sample_task_deliberation.task.approved_by_council is True


def test_task_deliberation_reject_flow(db_session, sample_task_deliberation, sample_council_member, sample_lead_agent):
    """Verify TaskDeliberation rejection flow."""
    sample_task_deliberation.start()
    sample_task_deliberation.task.status = TaskStatus.DELIBERATING
    db_session.commit()

    sample_task_deliberation.cast_vote(sample_council_member.agentium_id, VoteType.AGAINST, "Reject task")
    sample_task_deliberation.cast_vote(sample_lead_agent.agentium_id, VoteType.AGAINST, "Reject task")
    db_session.commit()

    res = sample_task_deliberation.conclude()
    db_session.commit()

    assert res["decision"] == "rejected"
    assert sample_task_deliberation.final_decision == "rejected"
    assert sample_task_deliberation.task.approved_by_council is False


def test_task_deliberation_emergency_override(db_session, sample_task_deliberation):
    """Verify Head of Council emergency_override bypasses voting."""
    sample_task_deliberation.start()
    sample_task_deliberation.task.status = TaskStatus.DELIBERATING
    db_session.commit()

    sample_task_deliberation.emergency_override(
        head_agentium_id="00001",
        reason="Security priority override",
        approve=True,
    )
    db_session.commit()

    assert sample_task_deliberation.head_overridden is True
    assert sample_task_deliberation.final_decision == "approved"
    assert sample_task_deliberation.status == DeliberationStatus.CONCLUDED
    assert sample_task_deliberation.task.approved_by_council is True


def test_individual_vote_change_tracking(db_session, sample_amendment_voting, sample_council_member):
    """Verify IndividualVote.change_vote sets vote_changed=True and records original_vote."""
    sample_amendment_voting.start_voting()
    db_session.commit()

    vote_rec = sample_amendment_voting.cast_vote(sample_council_member.agentium_id, VoteType.FOR, "Yes")
    db_session.commit()

    assert vote_rec.vote_changed is False

    vote_rec.change_vote(VoteType.AGAINST, "Changed mind")
    db_session.commit()

    fetched = db_session.query(IndividualVote).filter_by(id=vote_rec.id).first()
    assert fetched.vote_changed is True
    assert fetched.original_vote == VoteType.FOR
    assert fetched.vote == VoteType.AGAINST


def test_voting_record_generate_for_period(db_session, sample_amendment_voting, sample_council_member):
    """Verify VotingRecord.generate_for_period aggregates voting statistics."""
    from datetime import datetime, timedelta
    sample_amendment_voting.start_voting()
    sample_amendment_voting.cast_vote(sample_council_member.agentium_id, VoteType.FOR, "Yes")
    db_session.commit()

    now = datetime.utcnow()
    record = VotingRecord.generate_for_period(
        agentium_id=sample_council_member.agentium_id,
        start=now - timedelta(hours=1),
        end=now + timedelta(hours=1),
        session=db_session,
    )
    db_session.add(record)
    db_session.commit()

    fetched = db_session.query(VotingRecord).filter_by(agentium_id=sample_council_member.agentium_id).first()
    assert fetched is not None
    assert fetched.total_votes_cast == 1
    assert fetched.votes_for == 1
    assert fetched.votes_against == 0
