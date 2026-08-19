"""
Unit tests for Voting models.
Tests AmendmentVoting, TaskDeliberation, IndividualVote, and VotingRecord.
"""
import pytest
import json
from datetime import datetime, timezone
from uuid import uuid4

try:
    from backend.models.entities.voting import (
        AmendmentVoting, TaskDeliberation, IndividualVote, VotingRecord,
        VoteType, DeliberationStatus, AmendmentStatus
    )
except ImportError:
    from models.entities.voting import (
        AmendmentVoting, TaskDeliberation, IndividualVote, VotingRecord,
        VoteType, DeliberationStatus, AmendmentStatus
    )


class TestVoteType:
    """Tests for VoteType enum."""

    @pytest.mark.parametrize("vote_type", [VoteType.FOR, VoteType.AGAINST, VoteType.ABSTAIN])
    def test_vote_type_values(self, vote_type):
        """All VoteType values are valid."""
        assert vote_type in (VoteType.FOR, VoteType.AGAINST, VoteType.ABSTAIN)
        assert isinstance(vote_type.value, str)

    def test_vote_type_string_values(self):
        """VoteType string values match expected."""
        assert VoteType.FOR.value == "for"
        assert VoteType.AGAINST.value == "against"
        assert VoteType.ABSTAIN.value == "abstain"


class TestDeliberationStatus:
    """Tests for DeliberationStatus enum."""

    @pytest.mark.parametrize("status", [
        DeliberationStatus.PENDING,
        DeliberationStatus.ACTIVE,
        DeliberationStatus.QUORUM_REACHED,
        DeliberationStatus.CONCLUDED,
        DeliberationStatus.EXECUTED,
    ])
    def test_deliberation_status_values(self, status):
        """All DeliberationStatus values are valid."""
        assert status in (
            DeliberationStatus.PENDING,
            DeliberationStatus.ACTIVE,
            DeliberationStatus.QUORUM_REACHED,
            DeliberationStatus.CONCLUDED,
            DeliberationStatus.EXECUTED,
        )
        assert isinstance(status.value, str)


class TestAmendmentStatus:
    """Tests for AmendmentStatus enum."""

    @pytest.mark.parametrize("status", [
        AmendmentStatus.PROPOSED,
        AmendmentStatus.DELIBERATING,
        AmendmentStatus.VOTING,
        AmendmentStatus.PASSED,
        AmendmentStatus.REJECTED,
        AmendmentStatus.RATIFIED,
    ])
    def test_amendment_status_values(self, status):
        """All AmendmentStatus values are valid."""
        assert status in (
            AmendmentStatus.PROPOSED,
            AmendmentStatus.DELIBERATING,
            AmendmentStatus.VOTING,
            AmendmentStatus.PASSED,
            AmendmentStatus.REJECTED,
            AmendmentStatus.RATIFIED,
        )
        assert isinstance(status.value, str)


class TestAmendmentVoting:
    """Tests for AmendmentVoting model."""

    def test_amendment_voting_creation(self, db_session):
        """AmendmentVoting creates with all required fields."""
        voting = AmendmentVoting(
            amendment_id="test-amendment-id",
            eligible_voters=json.dumps(["10001", "10002", "10003"]),
            required_votes=3,
            supermajority_threshold=66,
            proposed_by_agentium_id="00001",
            proposed_changes="Add new article",
            rationale="Required for governance update",
        )
        db_session.add(voting)
        db_session.commit()
        db_session.refresh(voting)

        assert voting.amendment_id == "test-amendment-id"
        assert voting.required_votes == 3
        assert voting.supermajority_threshold == 66
        assert voting.proposed_by_agentium_id == "00001"
        assert voting.status == AmendmentStatus.PROPOSED
        assert voting.votes_for == 0
        assert voting.votes_against == 0
        assert voting.votes_abstain == 0
        assert voting.agentium_id.startswith("AV")
        assert len(voting.agentium_id) == 10

    def test_amendment_voting_defaults(self, db_session):
        """AmendmentVoting defaults are correct."""
        voting = AmendmentVoting(
            amendment_id="test-amendment-id-2",
            eligible_voters=json.dumps(["10001", "10002", "10003"]),
            proposed_by_agentium_id="00001",
            proposed_changes="Test change",
            rationale="Test rationale",
        )
        db_session.add(voting)
        db_session.commit()

        assert voting.required_votes == 3
        assert voting.supermajority_threshold == 66
        assert voting.status == AmendmentStatus.PROPOSED
        assert voting.votes_for == 0
        assert voting.votes_against == 0
        assert voting.votes_abstain == 0
        assert voting.discussion_thread == []
        assert voting.started_at is None
        assert voting.ended_at is None

    def test_amendment_voting_start_voting(self, db_session):
        """start_voting() changes status and sets started_at."""
        voting = AmendmentVoting(
            amendment_id="test-amendment-id-3",
            eligible_voters=json.dumps(["10001", "10002", "10003"]),
            proposed_by_agentium_id="00001",
            proposed_changes="Test change",
            rationale="Test rationale",
        )
        db_session.add(voting)
        db_session.commit()

        assert voting.status == AmendmentStatus.PROPOSED
        assert voting.started_at is None

        voting.start_voting()
        db_session.commit()

        assert voting.status == AmendmentStatus.VOTING
        assert voting.started_at is not None
        assert len(voting.discussion_thread) == 1
        assert voting.discussion_thread[0]["agent"] == "System"
        assert "started" in voting.discussion_thread[0]["message"].lower()

    def test_amendment_voting_cast_vote_for(self, db_session):
        """cast_vote() records FOR vote correctly."""
        voting = AmendmentVoting(
            amendment_id="test-amendment-id-4",
            eligible_voters=json.dumps(["10001", "10002", "10003"]),
            proposed_by_agentium_id="00001",
            proposed_changes="Test change",
            rationale="Test rationale",
        )
        db_session.add(voting)
        db_session.commit()
        voting.start_voting()
        db_session.commit()

        vote_record = voting.cast_vote("10001", VoteType.FOR, "Support this change")
        db_session.commit()

        assert vote_record.vote == VoteType.FOR
        assert vote_record.voter_agentium_id == "10001"
        assert vote_record.rationale == "Support this change"
        assert voting.votes_for == 1
        assert voting.votes_against == 0
        assert voting.votes_abstain == 0

    def test_amendment_voting_cast_vote_against(self, db_session):
        """cast_vote() records AGAINST vote correctly."""
        voting = AmendmentVoting(
            amendment_id="test-amendment-id-5",
            eligible_voters=json.dumps(["10001", "10002", "10003"]),
            proposed_by_agentium_id="00001",
            proposed_changes="Test change",
            rationale="Test rationale",
        )
        db_session.add(voting)
        db_session.commit()
        voting.start_voting()
        db_session.commit()

        voting.cast_vote("10002", VoteType.AGAINST, "Oppose this change")
        db_session.commit()

        assert voting.votes_for == 0
        assert voting.votes_against == 1
        assert voting.votes_abstain == 0

    def test_amendment_voting_cast_vote_abstain(self, db_session):
        """cast_vote() records ABSTAIN vote correctly."""
        voting = AmendmentVoting(
            amendment_id="test-amendment-id-6",
            eligible_voters=json.dumps(["10001", "10002", "10003"]),
            proposed_by_agentium_id="00001",
            proposed_changes="Test change",
            rationale="Test rationale",
        )
        db_session.add(voting)
        db_session.commit()
        voting.start_voting()
        db_session.commit()

        voting.cast_vote("10003", VoteType.ABSTAIN, "No opinion")
        db_session.commit()

        assert voting.votes_for == 0
        assert voting.votes_against == 0
        assert voting.votes_abstain == 1

    def test_amendment_voting_cast_vote_not_eligible(self, db_session):
        """cast_vote() rejects ineligible voters."""
        voting = AmendmentVoting(
            amendment_id="test-amendment-id-7",
            eligible_voters=json.dumps(["10001", "10002", "10003"]),
            proposed_by_agentium_id="00001",
            proposed_changes="Test change",
            rationale="Test rationale",
        )
        db_session.add(voting)
        db_session.commit()
        voting.start_voting()
        db_session.commit()

        with pytest.raises(PermissionError, match="not eligible"):
            voting.cast_vote("99999", VoteType.FOR)  # Not in eligible_voters

    def test_amendment_voting_cast_vote_not_open(self, db_session):
        """cast_vote() rejects votes when not in VOTING status."""
        voting = AmendmentVoting(
            amendment_id="test-amendment-id-8",
            eligible_voters=json.dumps(["10001", "10002", "10003"]),
            proposed_by_agentium_id="00001",
            proposed_changes="Test change",
            rationale="Test rationale",
        )
        db_session.add(voting)
        db_session.commit()
        # Not calling start_voting()

        with pytest.raises(ValueError, match="not currently open"):
            voting.cast_vote("10001", VoteType.FOR)

    def test_amendment_voting_change_vote(self, db_session):
        """Changing a vote updates counters correctly."""
        voting = AmendmentVoting(
            amendment_id="test-amendment-id-9",
            eligible_voters=json.dumps(["10001", "10002", "10003"]),
            proposed_by_agentium_id="00001",
            proposed_changes="Test change",
            rationale="Test rationale",
        )
        db_session.add(voting)
        db_session.commit()
        voting.start_voting()
        db_session.commit()

        # First vote FOR
        voting.cast_vote("10001", VoteType.FOR, "Initially for")
        db_session.commit()
        assert voting.votes_for == 1

        # Change to AGAINST
        vote_record = voting.cast_vote("10001", VoteType.AGAINST, "Changed mind")
        db_session.commit()
        assert voting.votes_for == 0
        assert voting.votes_against == 1
        assert vote_record.vote == VoteType.AGAINST

    def test_amendment_voting_conclude_passed(self, db_session):
        """conclude() with supermajority returns PASSED."""
        voting = AmendmentVoting(
            amendment_id="test-amendment-id-10",
            eligible_voters=json.dumps(["10001", "10002", "10003"]),
            required_votes=2,
            supermajority_threshold=66,
            proposed_by_agentium_id="00001",
            proposed_changes="Test change",
            rationale="Test rationale",
        )
        db_session.add(voting)
        db_session.commit()
        voting.start_voting()
        db_session.commit()

        # 2 FOR, 1 AGAINST => 66.6% FOR => passes
        voting.cast_vote("10001", VoteType.FOR)
        voting.cast_vote("10002", VoteType.FOR)
        voting.cast_vote("10003", VoteType.AGAINST)
        db_session.commit()

        result = voting.conclude()
        db_session.commit()

        assert voting.status == AmendmentStatus.PASSED
        assert voting.final_result == "passed"
        assert result["result"] == "passed"
        assert voting.ended_at is not None

    def test_amendment_voting_conclude_rejected_not_quorum(self, db_session):
        """conclude() without quorum returns REJECTED."""
        voting = AmendmentVoting(
            amendment_id="test-amendment-id-11",
            eligible_voters=json.dumps(["10001", "10002", "10003", "10004", "10005"]),
            required_votes=2,
            supermajority_threshold=66,
            proposed_by_agentium_id="00001",
            proposed_changes="Test change",
            rationale="Test rationale",
        )
        db_session.add(voting)
        db_session.commit()
        voting.start_voting()
        db_session.commit()

        # Only 2 votes out of 5 eligible = 40% < 60% quorum
        voting.cast_vote("10001", VoteType.FOR)
        voting.cast_vote("10002", VoteType.FOR)
        db_session.commit()

        result = voting.conclude()
        db_session.commit()

        assert voting.status == AmendmentStatus.REJECTED
        assert voting.final_result == "rejected"
        assert result["result"] == "rejected"

    def test_amendment_voting_conclude_rejected_no_supermajority(self, db_session):
        """conclude() without supermajority returns REJECTED."""
        voting = AmendmentVoting(
            amendment_id="test-amendment-id-12",
            eligible_voters=json.dumps(["10001", "10002", "10003"]),
            required_votes=2,
            supermajority_threshold=66,
            proposed_by_agentium_id="00001",
            proposed_changes="Test change",
            rationale="Test rationale",
        )
        db_session.add(voting)
        db_session.commit()
        voting.start_voting()
        db_session.commit()

        # 2 FOR, 1 AGAINST = 66.6% => needs >= 66%... wait, that should pass
        # Let's do 1 FOR, 2 AGAINST
        voting.cast_vote("10001", VoteType.FOR)
        voting.cast_vote("10002", VoteType.AGAINST)
        voting.cast_vote("10003", VoteType.AGAINST)
        db_session.commit()

        result = voting.conclude()
        db_session.commit()

        assert voting.status == AmendmentStatus.REJECTED
        assert voting.final_result == "rejected"

    def test_amendment_voting_eligible_voters_string_parsing(self, db_session):
        """eligible_voters works whether stored as list or JSON string."""
        # Test with list directly
        voting1 = AmendmentVoting(
            amendment_id="test-amendment-id-13",
            eligible_voters=["10001", "10002", "10003"],
            proposed_by_agentium_id="00001",
            proposed_changes="Test",
            rationale="Test",
        )
        db_session.add(voting1)
        db_session.commit()
        voting1.start_voting()
        db_session.commit()

        # Should work with list
        voting1.cast_vote("10001", VoteType.FOR)
        db_session.commit()
        assert voting1.votes_for == 1

    def test_amendment_voting_to_dict(self, db_session):
        """to_dict() includes all relevant fields."""
        voting = AmendmentVoting(
            amendment_id="test-amendment-id-14",
            eligible_voters=json.dumps(["10001", "10002", "10003"]),
            proposed_by_agentium_id="00001",
            proposed_changes="Test change",
            rationale="Test rationale",
        )
        db_session.add(voting)
        db_session.commit()

        data = voting.to_dict()
        assert data["status"] == "proposed"
        assert data["votes_for"] == 0
        assert data["votes_against"] == 0
        assert data["result"] is None


class TestTaskDeliberation:
    """Tests for TaskDeliberation model."""

    def test_task_deliberation_creation(self, db_session):
        """TaskDeliberation creates with all required fields."""
        deliberation = TaskDeliberation(
            task_id="test-task-id",
            participating_members=json.dumps(["10001", "10002", "10003"]),
            required_approvals=2,
            min_quorum=2,
            time_limit_minutes=30,
        )
        db_session.add(deliberation)
        db_session.commit()
        db_session.refresh(deliberation)

        assert deliberation.task_id == "test-task-id"
        assert deliberation.required_approvals == 2
        assert deliberation.min_quorum == 2
        assert deliberation.time_limit_minutes == 30
        assert deliberation.status == DeliberationStatus.PENDING
        assert deliberation.votes_for == 0
        assert deliberation.votes_against == 0
        assert deliberation.votes_abstain == 0
        assert deliberation.agentium_id.startswith("DL")
        assert len(deliberation.agentium_id) == 10
        assert deliberation.head_overridden is False

    def test_task_deliberation_defaults(self, db_session):
        """TaskDeliberation defaults are correct."""
        deliberation = TaskDeliberation(
            task_id="test-task-id-2",
            participating_members=json.dumps(["10001", "10002"]),
        )
        db_session.add(deliberation)
        db_session.commit()

        assert deliberation.required_approvals == 2
        assert deliberation.min_quorum == 2
        assert deliberation.time_limit_minutes == 30
        assert deliberation.status == DeliberationStatus.PENDING
        assert deliberation.discussion_thread == []

    def test_task_deliberation_start(self, db_session):
        """start() changes status and sets started_at."""
        deliberation = TaskDeliberation(
            task_id="test-task-id-3",
            participating_members=json.dumps(["10001", "10002", "10003"]),
        )
        db_session.add(deliberation)
        db_session.commit()

        assert deliberation.status == DeliberationStatus.PENDING
        assert deliberation.started_at is None

        deliberation.start()
        db_session.commit()

        assert deliberation.status == DeliberationStatus.ACTIVE
        assert deliberation.started_at is not None
        assert len(deliberation.discussion_thread) == 1

    def test_task_deliberation_cast_vote_for(self, db_session):
        """cast_vote() records FOR vote and updates counters."""
        deliberation = TaskDeliberation(
            task_id="test-task-id-4",
            participating_members=json.dumps(["10001", "10002", "10003"]),
            required_approvals=2,
            min_quorum=2,
        )
        db_session.add(deliberation)
        db_session.commit()
        deliberation.start()
        db_session.commit()

        vote_record = deliberation.cast_vote("10001", VoteType.FOR, "Approve task")
        db_session.commit()

        assert vote_record.vote == VoteType.FOR
        assert deliberation.votes_for == 1
        assert deliberation.votes_against == 0

    def test_task_deliberation_cast_vote_against(self, db_session):
        """cast_vote() records AGAINST vote and updates counters."""
        deliberation = TaskDeliberation(
            task_id="test-task-id-5",
            participating_members=json.dumps(["10001", "10002", "10003"]),
            required_approvals=2,
            min_quorum=2,
        )
        db_session.add(deliberation)
        db_session.commit()
        deliberation.start()
        db_session.commit()

        deliberation.cast_vote("10002", VoteType.AGAINST, "Reject task")
        db_session.commit()

        assert deliberation.votes_for == 0
        assert deliberation.votes_against == 1

    def test_task_deliberation_cast_vote_not_participating(self, db_session):
        """cast_vote() rejects non-participating members."""
        deliberation = TaskDeliberation(
            task_id="test-task-id-6",
            participating_members=json.dumps(["10001", "10002", "10003"]),
            required_approvals=2,
            min_quorum=2,
        )
        db_session.add(deliberation)
        db_session.commit()
        deliberation.start()
        db_session.commit()

        with pytest.raises(PermissionError, match="not part of this deliberation"):
            deliberation.cast_vote("99999", VoteType.FOR)

    def test_task_deliberation_cast_vote_not_active(self, db_session):
        """cast_vote() rejects when not in ACTIVE or QUORUM_REACHED status."""
        deliberation = TaskDeliberation(
            task_id="test-task-id-7",
            participating_members=json.dumps(["10001", "10002", "10003"]),
            required_approvals=2,
            min_quorum=2,
        )
        db_session.add(deliberation)
        db_session.commit()
        # Not calling start()

        with pytest.raises(ValueError, match="not currently open"):
            deliberation.cast_vote("10001", VoteType.FOR)

    def test_task_deliberation_change_vote(self, db_session):
        """Changing a vote updates counters correctly."""
        deliberation = TaskDeliberation(
            task_id="test-task-id-8",
            participating_members=json.dumps(["10001", "10002", "10003"]),
            required_approvals=2,
            min_quorum=2,
        )
        db_session.add(deliberation)
        db_session.commit()
        deliberation.start()
        db_session.commit()

        # First vote FOR
        deliberation.cast_vote("10001", VoteType.FOR)
        db_session.commit()
        assert deliberation.votes_for == 1

        # Change to ABSTAIN
        deliberation.cast_vote("10001", VoteType.ABSTAIN)
        db_session.commit()
        assert deliberation.votes_for == 0
        assert deliberation.votes_abstain == 1

    def test_task_deliberation_quorum_reached(self, db_session):
        """Status changes to QUORUM_REACHED when min_quorum met."""
        deliberation = TaskDeliberation(
            task_id="test-task-id-9",
            participating_members=json.dumps(["10001", "10002", "10003"]),
            required_approvals=2,
            min_quorum=2,
        )
        db_session.add(deliberation)
        db_session.commit()
        deliberation.start()
        db_session.commit()

        # First vote
        deliberation.cast_vote("10001", VoteType.FOR)
        db_session.commit()
        assert deliberation.status == DeliberationStatus.ACTIVE

        # Second vote reaches quorum
        deliberation.cast_vote("10002", VoteType.FOR)
        db_session.commit()
        assert deliberation.status == DeliberationStatus.QUORUM_REACHED

    def test_task_deliberation_conclude_approved(self, db_session):
        """conclude() with enough approvals returns APPROVED."""
        deliberation = TaskDeliberation(
            task_id="test-task-id-10",
            participating_members=json.dumps(["10001", "10002", "10003"]),
            required_approvals=2,
            min_quorum=2,
        )
        db_session.add(deliberation)
        db_session.commit()
        deliberation.start()
        db_session.commit()

        # 2 FOR votes = required_approvals met, FOR > AGAINST
        deliberation.cast_vote("10001", VoteType.FOR)
        deliberation.cast_vote("10002", VoteType.FOR)
        deliberation.cast_vote("10003", VoteType.AGAINST)
        db_session.commit()

        result = deliberation.conclude()
        db_session.commit()

        assert deliberation.status == DeliberationStatus.CONCLUDED
        assert deliberation.final_decision == "approved"
        assert result["decision"] == "approved"
        assert deliberation.ended_at is not None

    def test_task_deliberation_conclude_rejected(self, db_session):
        """conclude() with enough rejections returns REJECTED."""
        deliberation = TaskDeliberation(
            task_id="test-task-id-11",
            participating_members=json.dumps(["10001", "10002", "10003"]),
            required_approvals=2,
            min_quorum=2,
        )
        db_session.add(deliberation)
        db_session.commit()
        deliberation.start()
        db_session.commit()

        # 2 AGAINST votes
        deliberation.cast_vote("10001", VoteType.AGAINST)
        deliberation.cast_vote("10002", VoteType.AGAINST)
        deliberation.cast_vote("10003", VoteType.FOR)
        db_session.commit()

        result = deliberation.conclude()
        db_session.commit()

        assert deliberation.final_decision == "rejected"
        assert result["decision"] == "rejected"

    def test_task_deliberation_conclude_tie(self, db_session):
        """conclude() with tie returns TIE."""
        # When votes_for == votes_against but neither meets required_approvals
        # For required_approvals=2, 1 FOR + 1 AGAINST = tie
        deliberation = TaskDeliberation(
            task_id="test-task-id-12",
            participating_members=json.dumps(["10001", "10002"]),
            required_approvals=2,
            min_quorum=2,
        )
        db_session.add(deliberation)
        db_session.commit()
        deliberation.start()
        db_session.commit()

        deliberation.cast_vote("10001", VoteType.FOR)
        deliberation.cast_vote("10002", VoteType.AGAINST)
        db_session.commit()

        result = deliberation.conclude()
        db_session.commit()

        assert deliberation.final_decision == "tie"
        assert result["decision"] == "tie"

    def test_task_deliberation_conclude_not_active(self, db_session):
        """conclude() raises error when not active."""
        deliberation = TaskDeliberation(
            task_id="test-task-id-13",
            participating_members=json.dumps(["10001", "10002"]),
        )
        db_session.add(deliberation)
        db_session.commit()
        # Not started

        with pytest.raises(ValueError, match="not active"):
            deliberation.conclude()

    def test_task_deliberation_emergency_override_approve(self, db_session):
        """emergency_override() with approve=True sets decision to approved."""
        deliberation = TaskDeliberation(
            task_id="test-task-id-14",
            participating_members=json.dumps(["10001", "10002", "10003"]),
        )
        db_session.add(deliberation)
        db_session.commit()
        deliberation.start()
        db_session.commit()

        deliberation.emergency_override("00001", "Critical security fix", approve=True)
        db_session.commit()

        assert deliberation.head_overridden is True
        assert deliberation.head_override_reason == "Critical security fix"
        assert deliberation.final_decision == "approved"
        assert deliberation.status == DeliberationStatus.CONCLUDED

    def test_task_deliberation_emergency_override_reject(self, db_session):
        """emergency_override() with approve=False sets decision to rejected."""
        deliberation = TaskDeliberation(
            task_id="test-task-id-15",
            participating_members=json.dumps(["10001", "10002", "10003"]),
        )
        db_session.add(deliberation)
        db_session.commit()
        deliberation.start()
        db_session.commit()

        deliberation.emergency_override("00001", "Security risk", approve=False)
        db_session.commit()

        assert deliberation.final_decision == "rejected"

    def test_task_deliberation_get_participation_rate(self, db_session):
        """get_participation_rate() calculates correct percentage."""
        # Use list to ensure proper parsing
        deliberation = TaskDeliberation(
            task_id="test-task-id-16",
            participating_members=["10001", "10002", "10003", "10004"],
            required_approvals=2,
            min_quorum=2,
        )
        db_session.add(deliberation)
        db_session.commit()
        deliberation.start()
        db_session.commit()

        # 2 votes out of 4 = 50%
        deliberation.cast_vote("10001", VoteType.FOR)
        deliberation.cast_vote("10002", VoteType.AGAINST)
        db_session.commit()

        rate = deliberation.get_participation_rate()
        assert rate == 50.0

    def test_task_deliberation_to_dict(self, db_session):
        """to_dict() includes all relevant fields."""
        # Use list directly - to_dict returns what participating_members contains
        deliberation = TaskDeliberation(
            task_id="test-task-id-17",
            participating_members=["10001", "10002"],
            required_approvals=2,
            min_quorum=2,
        )
        db_session.add(deliberation)
        db_session.commit()

        data = deliberation.to_dict()
        assert data["status"] == "pending"
        assert data["participants"] == ["10001", "10002"]
        assert data["votes"]["required"] == 2
        assert data["overridden"] is False
        assert "timing" in data


class TestIndividualVote:
    """Tests for IndividualVote model."""

    def test_individual_vote_creation(self, db_session):
        """IndividualVote creates with all required fields."""
        # Create parent TaskDeliberation first
        deliberation = TaskDeliberation(
            task_id="test-task-id",
            participating_members=json.dumps(["10001", "10002", "10003"]),
        )
        db_session.add(deliberation)
        db_session.commit()
        db_session.refresh(deliberation)

        vote = IndividualVote(
            agentium_id="V00000001",  # Required - IndividualVote doesn't auto-generate
            task_deliberation_id=deliberation.id,
            voter_agentium_id="10001",
            vote=VoteType.FOR,
            rationale="Support this proposal",
        )
        db_session.add(vote)
        db_session.commit()
        db_session.refresh(vote)

        assert vote.voter_agentium_id == "10001"
        assert vote.vote == VoteType.FOR
        assert vote.rationale == "Support this proposal"
        assert vote.vote_changed is False
        assert vote.original_vote is None
        assert vote.changed_at is None
        assert vote.agentium_id == "V00000001"
        assert vote.task_deliberation_id == deliberation.id

    def test_individual_vote_defaults(self, db_session):
        """IndividualVote defaults are correct."""
        # Create parent AmendmentVoting first
        voting = AmendmentVoting(
            amendment_id="test-amendment-id",
            eligible_voters=json.dumps(["10001", "10002", "10003"]),
            proposed_by_agentium_id="00001",
            proposed_changes="Test change",
            rationale="Test rationale",
        )
        db_session.add(voting)
        db_session.commit()
        db_session.refresh(voting)

        vote = IndividualVote(
            agentium_id="V00000002",  # Required
            amendment_voting_id=voting.id,
            voter_agentium_id="10002",
            vote=VoteType.AGAINST,
        )
        db_session.add(vote)
        db_session.commit()

        assert vote.vote == VoteType.AGAINST
        assert vote.rationale is None
        assert vote.vote_changed is False
        assert vote.original_vote is None
        assert vote.changed_at is None

    def test_individual_vote_with_amendment_voting(self, db_session):
        """IndividualVote can link to AmendmentVoting."""
        voting = AmendmentVoting(
            amendment_id="test-amendment-id-2",
            eligible_voters=json.dumps(["10001", "10002", "10003"]),
            proposed_by_agentium_id="00001",
            proposed_changes="Test change",
            rationale="Test rationale",
        )
        db_session.add(voting)
        db_session.commit()
        db_session.refresh(voting)

        vote = IndividualVote(
            agentium_id="V00000003",  # Required
            amendment_voting_id=voting.id,
            voter_agentium_id="10003",
            vote=VoteType.ABSTAIN,
        )
        db_session.add(vote)
        db_session.commit()

        assert vote.amendment_voting_id == voting.id
        assert vote.task_deliberation_id is None

    def test_individual_vote_check_constraint(self, db_session):
        """IndividualVote requires either task_deliberation_id or amendment_voting_id."""
        vote = IndividualVote(
            agentium_id="V00000004",  # Required
            voter_agentium_id="10001",
            vote=VoteType.FOR,
            # Neither task_deliberation_id nor amendment_voting_id set
        )
        db_session.add(vote)
        with pytest.raises(Exception):  # CheckConstraint violation
            db_session.commit()
        db_session.rollback()

    def test_individual_vote_change_vote(self, db_session):
        """change_vote() updates vote and tracks original."""
        # Create parent TaskDeliberation first
        deliberation = TaskDeliberation(
            task_id="test-task-id",
            participating_members=json.dumps(["10001", "10002", "10003"]),
        )
        db_session.add(deliberation)
        db_session.commit()
        db_session.refresh(deliberation)

        vote = IndividualVote(
            agentium_id="V00000005",  # Required
            task_deliberation_id=deliberation.id,
            voter_agentium_id="10001",
            vote=VoteType.FOR,
            rationale="Initially for",
        )
        db_session.add(vote)
        db_session.commit()

        assert vote.vote == VoteType.FOR
        assert vote.vote_changed is False

        vote.change_vote(VoteType.AGAINST, "Changed mind")
        db_session.commit()

        assert vote.vote == VoteType.AGAINST
        assert vote.vote_changed is True
        assert vote.original_vote == VoteType.FOR
        assert vote.rationale == "Changed mind"
        assert vote.changed_at is not None

    def test_individual_vote_change_vote_keeps_original_on_subsequent_changes(self, db_session):
        """Original vote is preserved on subsequent changes."""
        deliberation = TaskDeliberation(
            task_id="test-task-id-2",
            participating_members=json.dumps(["10001", "10002", "10003"]),
        )
        db_session.add(deliberation)
        db_session.commit()
        db_session.refresh(deliberation)

        vote = IndividualVote(
            agentium_id="V00000006",  # Required
            task_deliberation_id=deliberation.id,
            voter_agentium_id="10001",
            vote=VoteType.FOR,
        )
        db_session.add(vote)
        db_session.commit()

        vote.change_vote(VoteType.ABSTAIN)
        db_session.commit()
        original = vote.original_vote

        vote.change_vote(VoteType.AGAINST)
        db_session.commit()

        assert vote.original_vote == original == VoteType.FOR

    def test_individual_vote_to_dict(self, db_session):
        """to_dict() includes all relevant fields."""
        deliberation = TaskDeliberation(
            task_id="test-task-id-3",
            participating_members=json.dumps(["10001", "10002", "10003"]),
        )
        db_session.add(deliberation)
        db_session.commit()
        db_session.refresh(deliberation)

        vote = IndividualVote(
            agentium_id="V00000007",  # Required
            task_deliberation_id=deliberation.id,
            voter_agentium_id="10001",
            vote=VoteType.FOR,
            rationale="Test rationale",
        )
        db_session.add(vote)
        db_session.commit()

        data = vote.to_dict()
        assert data["voter"] == "10001"
        assert data["vote"] == "for"
        assert data["rationale"] == "Test rationale"
        assert data["changed"] is False
        assert data["original_vote"] is None


class TestVotingRecord:
    """Tests for VotingRecord model."""

    def test_voting_record_creation(self, db_session):
        """VotingRecord creates with all fields."""
        period_start = datetime(2026, 1, 1)
        period_end = datetime(2026, 1, 7)

        record = VotingRecord(
            agentium_id="10001",
            period_start=period_start,
            period_end=period_end,
            total_votes_cast=10,
            votes_for=7,
            votes_against=2,
            votes_abstain=1,
            votes_changed=1,
            deliberations_participated=5,
            deliberations_missed=0,
            avg_participation_rate=100,
            proposals_made=2,
            proposals_accepted=1,
        )
        db_session.add(record)
        db_session.commit()
        db_session.refresh(record)

        assert record.agentium_id == "10001"
        assert record.period_start == period_start
        assert record.period_end == period_end
        assert record.total_votes_cast == 10
        assert record.votes_for == 7
        assert record.votes_against == 2
        assert record.votes_abstain == 1
        assert record.votes_changed == 1

    def test_voting_record_defaults(self, db_session):
        """VotingRecord defaults are correct."""
        record = VotingRecord(
            agentium_id="10002",
            period_start=datetime(2026, 1, 1),
            period_end=datetime(2026, 1, 7),
        )
        db_session.add(record)
        db_session.commit()

        assert record.total_votes_cast == 0
        assert record.votes_for == 0
        assert record.votes_against == 0
        assert record.votes_abstain == 0
        assert record.votes_changed == 0
        assert record.deliberations_participated == 0
        assert record.deliberations_missed == 0
        assert record.avg_participation_rate == 0
        assert record.proposals_made == 0
        assert record.proposals_accepted == 0

    def test_voting_record_to_dict(self, db_session):
        """to_dict() includes all relevant fields."""
        period_start = datetime(2026, 1, 1)
        period_end = datetime(2026, 1, 7)

        record = VotingRecord(
            agentium_id="10001",
            period_start=period_start,
            period_end=period_end,
            total_votes_cast=5,
            votes_for=3,
            votes_against=1,
            votes_abstain=1,
        )
        db_session.add(record)
        db_session.commit()

        data = record.to_dict()
        assert data["agent"] == "10001"
        assert data["period"]["start"] == period_start.isoformat()
        assert data["period"]["end"] == period_end.isoformat()
        assert data["votes"]["total"] == 5
        assert data["votes"]["breakdown"]["for"] == 3
        assert data["votes"]["breakdown"]["against"] == 1
        assert data["votes"]["breakdown"]["abstain"] == 1
        assert data["participation"]["attended"] == 0
        assert data["influence"]["proposals"] == 0


class TestVotingIntegration:
    """Integration tests for voting workflows."""

    def test_full_amendment_voting_workflow(self, db_session):
        """Complete amendment voting workflow from start to conclude."""
        voting = AmendmentVoting(
            amendment_id="integration-amendment-1",
            eligible_voters=json.dumps(["10001", "10002", "10003"]),
            required_votes=2,
            supermajority_threshold=66,
            proposed_by_agentium_id="00001",
            proposed_changes="Add emergency powers",
            rationale="Crisis response",
        )
        db_session.add(voting)
        db_session.commit()

        # Start voting
        voting.start_voting()
        db_session.commit()
        assert voting.status == AmendmentStatus.VOTING

        # Cast votes
        voting.cast_vote("10001", VoteType.FOR, "Essential")
        voting.cast_vote("10002", VoteType.FOR, "Agreed")
        voting.cast_vote("10003", VoteType.AGAINST, "Too risky")
        db_session.commit()

        # Conclude
        result = voting.conclude()
        db_session.commit()

        assert voting.status == AmendmentStatus.PASSED
        assert result["result"] == "passed"
        assert voting.votes_for == 2
        assert voting.votes_against == 1
        assert len(voting.discussion_thread) >= 4  # start + 3 votes + conclude

    def test_full_task_deliberation_workflow(self, db_session):
        """Complete task deliberation workflow from start to conclude."""
        deliberation = TaskDeliberation(
            task_id="integration-task-1",
            participating_members=json.dumps(["10001", "10002", "10003"]),
            required_approvals=2,
            min_quorum=2,
        )
        db_session.add(deliberation)
        db_session.commit()

        # Start deliberation
        deliberation.start()
        db_session.commit()
        assert deliberation.status == DeliberationStatus.ACTIVE

        # Cast votes
        deliberation.cast_vote("10001", VoteType.FOR)
        deliberation.cast_vote("10002", VoteType.FOR)
        deliberation.cast_vote("10003", VoteType.ABSTAIN)
        db_session.commit()

        # Conclude
        result = deliberation.conclude()
        db_session.commit()

        assert deliberation.status == DeliberationStatus.CONCLUDED
        assert deliberation.final_decision == "approved"
        assert result["decision"] == "approved"
        assert deliberation.votes_for == 2