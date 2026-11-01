"""
Tests for Health Monitor alert broadcasts.

Verifies:
1. agent_health_scan detects stalled and crashed agents, broadcasts system_alert
2. channel_deep_health detects unhealthy channels, broadcasts system_alert
3. anomaly_correlation detects anomalous tasks using isolation forest, broadcasts system_alert
4. auto_recovery_action resets stuck agents, triggers overflow review
"""
import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch, MagicMock
import asyncio
import uuid

from backend.models.entities.agents import Agent, AgentStatus, AgentType
from backend.models.entities.channels import ExternalChannel as Channel
from backend.models.entities.task import Task, TaskStatus, TaskType


def _unique_agent_id(prefix: int = 1) -> str:
    """Generate a unique 8-digit agentium_id starting with prefix digit."""
    return f"{prefix}{uuid.uuid4().int % 10000000:07d}"


def _unique_channel_id() -> str:
    """Generate a unique channel agentium_id."""
    return f"CH{uuid.uuid4().hex[:6].upper()}"


def _unique_task_id() -> str:
    """Generate a unique task agentium_id."""
    return f"T{uuid.uuid4().int % 100000:05d}"


class TestAgentHealthScan:
    """Tests for agent_health_scan function."""

    @pytest.mark.asyncio
    async def test_detects_stalled_and_crashed_agents(self, ws_capture, db_session):
        """Stalled (>2min) and crashed (>10min) agents trigger system_alert with agent_health type."""
        now = datetime.utcnow()

        # Active agent with recent heartbeat (healthy)
        healthy = Agent(
            agentium_id=_unique_agent_id(1),
            agent_type=AgentType.TASK_AGENT,
            name="Healthy Agent",
            status=AgentStatus.ACTIVE,
            last_heartbeat_at=now - timedelta(seconds=30)
        )

        # Stalled agent (>2min, <10min)
        stalled = Agent(
            agentium_id=_unique_agent_id(2),
            agent_type=AgentType.TASK_AGENT,
            name="Stalled Agent",
            status=AgentStatus.IDLE_WORKING,
            last_heartbeat_at=now - timedelta(minutes=5)
        )

        # Crashed agent (>10min)
        crashed = Agent(
            agentium_id=_unique_agent_id(3),
            agent_type=AgentType.TASK_AGENT,
            name="Crashed Agent",
            status=AgentStatus.ACTIVE,
            last_heartbeat_at=now - timedelta(minutes=15)
        )

        # No heartbeat ever
        no_heartbeat = Agent(
            agentium_id=_unique_agent_id(4),
            agent_type=AgentType.TASK_AGENT,
            name="No Heartbeat Agent",
            status=AgentStatus.ACTIVE,
            last_heartbeat_at=None
        )

        db_session.add_all([healthy, stalled, crashed, no_heartbeat])
        db_session.commit()

        # Create monitor agent
        monitor = Agent(
            agentium_id=_unique_agent_id(9),
            agent_type=AgentType.TASK_AGENT,
            name="Monitor",
            status=AgentStatus.ACTIVE
        )
        db_session.add(monitor)
        db_session.commit()

        from backend.services.idle_tasks.health_monitor import agent_health_scan
        result = await agent_health_scan(db_session, monitor)

        assert result["status"] == "completed"
        assert result["scanned"] == 4
        assert len(result["stalled_agents"]) == 1
        assert result["stalled_agents"][0]["agentium_id"] == stalled.agentium_id
        assert len(result["crashed_agents"]) == 2
        crashed_ids = {c["agentium_id"] for c in result["crashed_agents"]}
        assert crashed_ids == {crashed.agentium_id, no_heartbeat.agentium_id}

        # Verify system_alert broadcast
        alert = await ws_capture.wait_for_event_async("system_alert", timeout=3)
        assert alert["alert_type"] == "agent_health"
        assert len(alert["stalled"]) == 1
        assert alert["stalled"][0]["agentium_id"] == stalled.agentium_id
        assert len(alert["crashed"]) == 2
        crashed_alert_ids = {c["agentium_id"] for c in alert["crashed"]}
        assert crashed_alert_ids == {crashed.agentium_id, no_heartbeat.agentium_id}

    @pytest.mark.asyncio
    async def test_reassigns_orphaned_tasks_from_crashed_agents(self, ws_capture, db_session):
        """Orphaned tasks from crashed agents are reassigned to PENDING."""
        now = datetime.utcnow()

        crashed = Agent(
            agentium_id=_unique_agent_id(5),
            agent_type=AgentType.TASK_AGENT,
            name="Crashed Agent 2",
            status=AgentStatus.ACTIVE,
            last_heartbeat_at=now - timedelta(minutes=15)
        )
        db_session.add(crashed)
        db_session.commit()

        # Create orphaned tasks
        orphaned_task = Task(
            title="Orphaned Task",
            description="Task from crashed agent",
            task_type=TaskType.EXECUTION,
            status=TaskStatus.IN_PROGRESS,
            assigned_task_agent_ids=[crashed.agentium_id],
            created_at=now - timedelta(minutes=20)
        )
        db_session.add(orphaned_task)
        db_session.commit()

        monitor = Agent(
            agentium_id=_unique_agent_id(9),
            agent_type=AgentType.TASK_AGENT,
            name="Monitor 2",
            status=AgentStatus.ACTIVE
        )
        db_session.add(monitor)
        db_session.commit()

        from backend.services.idle_tasks.health_monitor import agent_health_scan
        result = await agent_health_scan(db_session, monitor)

        # Verify task was reassigned
        db_session.refresh(orphaned_task)
        assert orphaned_task.status == TaskStatus.PENDING
        assert crashed.agentium_id not in (orphaned_task.assigned_task_agent_ids or [])

        # Verify crashed agent marked OFFLINE
        db_session.refresh(crashed)
        assert crashed.status == AgentStatus.OFFLINE

        assert crashed.agentium_id in result["recovered"]


class TestChannelDeepHealth:
    """Tests for channel_deep_health function."""

    @pytest.mark.asyncio
    async def test_detects_unhealthy_channels(self, ws_capture, db_session):
        """Unhealthy channels trigger system_alert with channel_unhealthy type."""
        ch1 = Channel(name="slack", channel_type="slack", is_active=True, config={}, agentium_id=_unique_channel_id())
        ch2 = Channel(name="discord", channel_type="discord", is_active=True, config={}, agentium_id=_unique_channel_id())
        db_session.add_all([ch1, ch2])
        db_session.commit()

        monitor = Agent(
            agentium_id=_unique_agent_id(9),
            agent_type=AgentType.TASK_AGENT,
            name="Monitor CH",
            status=AgentStatus.ACTIVE
        )
        db_session.add(monitor)
        db_session.commit()

        # Mock channel health check: slack healthy, discord timeout
        async def mock_health_check(channel_name, payload, timeout=5):
            if channel_name == "slack":
                return {"status": "ok", "channel": channel_name}
            raise asyncio.TimeoutError("Discord timeout")

        from backend.services.idle_tasks.health_monitor import channel_deep_health

        with patch("backend.services.idle_tasks.health_monitor._send_channel_health_check", side_effect=mock_health_check):
            result = await channel_deep_health(db_session, monitor)

        assert result["status"] == "completed"
        assert result["checked"] == 2
        assert result["healthy"] == 1
        assert result["unhealthy"] == 1
        assert result["details"][1]["channel"] == "discord"
        assert result["details"][1]["error"] == "timeout"

        # Verify system_alert broadcast
        alert = await ws_capture.wait_for_event_async("system_alert", timeout=3)
        assert alert["alert_type"] == "channel_unhealthy"
        assert len(alert["channels"]) == 1
        assert alert["channels"][0]["channel"] == "discord"
        assert alert["channels"][0]["error"] == "timeout"

    @pytest.mark.asyncio
    async def test_all_healthy_channels_no_alert(self, ws_capture, db_session):
        """All healthy channels do not trigger alert."""
        ch1 = Channel(name="slack", channel_type="slack", is_active=True, config={}, agentium_id=_unique_channel_id())
        ch2 = Channel(name="email", channel_type="email", is_active=True, config={}, agentium_id=_unique_channel_id())
        db_session.add_all([ch1, ch2])
        db_session.commit()

        monitor = Agent(
            agentium_id=_unique_agent_id(9),
            agent_type=AgentType.TASK_AGENT,
            name="Monitor CH 2",
            status=AgentStatus.ACTIVE
        )
        db_session.add(monitor)
        db_session.commit()

        async def mock_health_check(channel_name, payload, timeout=5):
            return {"status": "ok", "channel": channel_name}

        from backend.services.idle_tasks.health_monitor import channel_deep_health

        with patch("backend.services.idle_tasks.health_monitor._send_channel_health_check", side_effect=mock_health_check):
            result = await channel_deep_health(db_session, monitor)

        assert result["healthy"] == 2
        assert result["unhealthy"] == 0

        # No system_alert should be broadcast
        channel_alerts = [e for e in ws_capture.captured_events if e.get("alert_type") == "channel_unhealthy"]
        assert len(channel_alerts) == 0


class TestAnomalyCorrelation:
    """Tests for anomaly_correlation function."""

    @pytest.mark.asyncio
    async def test_detects_outliers_using_isolation_forest(self, ws_capture, db_session):
        """Isolation forest detects anomalous tasks with high duration/tokens."""
        # Need sklearn for this test
        try:
            from sklearn.ensemble import IsolationForest
        except ImportError:
            pytest.skip("sklearn not installed")

        base_time = datetime.utcnow() - timedelta(hours=1)

        # Create 20 normal tasks (2 min duration, 1000 tokens)
        for i in range(20):
            task = Task(
                agentium_id=_unique_task_id(),
                title=f"Normal Task {i}",
                description="Normal",
                task_type=TaskType.EXECUTION,
                status=TaskStatus.COMPLETED,
                created_at=base_time + timedelta(minutes=i*3),
                completed_at=base_time + timedelta(minutes=i*3 + 2),
                tokens_used=1000,
            )
            db_session.add(task)

        # Create 3 anomalous tasks (60 min duration, 50000 tokens)
        for i in range(3):
            task = Task(
                agentium_id=_unique_task_id(),
                title=f"Anomalous Task {i}",
                description="Anomalous",
                task_type=TaskType.EXECUTION,
                status=TaskStatus.COMPLETED,
                created_at=base_time + timedelta(minutes=60 + i*5),
                completed_at=base_time + timedelta(minutes=60 + i*5 + 60),  # 60 min duration
                tokens_used=50000,  # High tokens
            )
            db_session.add(task)

        db_session.commit()

        monitor = Agent(
            agentium_id=_unique_agent_id(9),
            agent_type=AgentType.TASK_AGENT,
            name="Monitor Anom",
            status=AgentStatus.ACTIVE
        )
        db_session.add(monitor)
        db_session.commit()

        from backend.services.idle_tasks.health_monitor import anomaly_correlation
        result = await anomaly_correlation(db_session, monitor)

        assert result["status"] == "completed"
        assert result["analyzed"] == 23
        assert result["anomalies_found"] >= 1

        if result["anomalies_found"] > 0:
            # Verify system_alert broadcast
            alert = await ws_capture.wait_for_event_async("system_alert", timeout=3)
            assert alert["alert_type"] == "anomaly_detected"
            assert len(alert["anomalies"]) >= 1

    @pytest.mark.asyncio
    async def test_insufficient_data_returns_early(self, ws_capture, db_session):
        """Less than 10 tasks returns early without alert."""
        base_time = datetime.utcnow() - timedelta(hours=1)

        # Create only 5 tasks
        for i in range(5):
            task = Task(
                agentium_id=_unique_task_id(),
                title=f"Task {i}",
                description="Test",
                task_type=TaskType.EXECUTION,
                status=TaskStatus.COMPLETED,
                created_at=base_time + timedelta(minutes=i*10),
                completed_at=base_time + timedelta(minutes=i*10 + 2),
                tokens_used=1000,
            )
            db_session.add(task)

        db_session.commit()

        monitor = Agent(
            agentium_id=_unique_agent_id(9),
            agent_type=AgentType.TASK_AGENT,
            name="Monitor Anom 2",
            status=AgentStatus.ACTIVE
        )
        db_session.add(monitor)
        db_session.commit()

        from backend.services.idle_tasks.health_monitor import anomaly_correlation
        result = await anomaly_correlation(db_session, monitor)

        assert result["status"] == "completed"
        assert result["note"] == "insufficient_data"

        # No alert should be broadcast
        anomaly_alerts = [e for e in ws_capture.captured_events if e.get("alert_type") == "anomaly_detected"]
        assert len(anomaly_alerts) == 0


class TestAutoRecoveryAction:
    """Tests for auto_recovery_action function."""

    @pytest.mark.asyncio
    async def test_resets_stuck_idle_working_agents(self, ws_capture, db_session):
        """Stuck IDLE_WORKING agents (>10min) reset to ACTIVE."""
        stuck = Agent(
            agentium_id=_unique_agent_id(6),
            agent_type=AgentType.TASK_AGENT,
            name="Stuck Agent",
            status=AgentStatus.IDLE_WORKING,
            updated_at=datetime.utcnow() - timedelta(minutes=15)
        )
        db_session.add(stuck)
        db_session.commit()

        monitor = Agent(
            agentium_id=_unique_agent_id(9),
            agent_type=AgentType.TASK_AGENT,
            name="Monitor Rec",
            status=AgentStatus.ACTIVE
        )
        db_session.add(monitor)
        db_session.commit()

        from backend.services.idle_tasks.health_monitor import auto_recovery_action
        result = await auto_recovery_action(db_session, monitor)

        assert result["status"] == "completed"
        assert f"reset_agent_status:{stuck.agentium_id}" in result["actions_taken"]

        # Verify agent status changed
        db_session.refresh(stuck)
        assert stuck.status == AgentStatus.ACTIVE

    @pytest.mark.asyncio
    async def test_triggers_overflow_review_when_queue_deep(self, ws_capture, db_session):
        """Redis queue depth >500 triggers overflow_review alert."""
        # Create a stuck agent to ensure function runs
        stuck = Agent(
            agentium_id=_unique_agent_id(6),
            agent_type=AgentType.TASK_AGENT,
            name="Stuck Agent 2",
            status=AgentStatus.IDLE_WORKING,
            updated_at=datetime.utcnow() - timedelta(minutes=15)
        )
        db_session.add(stuck)
        db_session.commit()

        monitor = Agent(
            agentium_id=_unique_agent_id(9),
            agent_type=AgentType.TASK_AGENT,
            name="Monitor Rec 2",
            status=AgentStatus.ACTIVE
        )
        db_session.add(monitor)
        db_session.commit()

        from backend.services.idle_tasks.health_monitor import auto_recovery_action

        # Mock redis to return high queue depth
        mock_redis = MagicMock()
        mock_redis.llen.return_value = 600  # >500 threshold

        with patch("backend.services.idle_tasks.health_monitor.redis") as mock_redis_module:
            mock_redis_module.from_url.return_value = mock_redis

            result = await auto_recovery_action(db_session, monitor)

        assert "overflow_review_triggered" in result["actions_taken"]

        # Verify system_alert broadcast for overflow review
        alert = await ws_capture.wait_for_event_async("system_alert", timeout=3)
        assert alert["alert_type"] == "overflow_review_needed"
        assert alert["queue_depth"] == 600


class TestSystemResourceCheck:
    """Tests for system_resource_check function (from Task 9)."""

    @pytest.mark.asyncio
    async def test_pool_exhaustion_triggers_resource_warning(self, ws_capture, db_session):
        """When DB pool checked_out == size, resource_warning broadcast fires."""
        monitor = Agent(
            agentium_id=_unique_agent_id(9),
            agent_type=AgentType.TASK_AGENT,
            name="Health Monitor",
            status=AgentStatus.ACTIVE
        )
        db_session.add(monitor)
        db_session.commit()

        from backend.services.idle_tasks.health_monitor import system_resource_check

        # Mock psutil and engine pool
        mock_pool = MagicMock()
        mock_pool.size.return_value = 10
        mock_pool.checkedout.return_value = 10  # 100% utilized
        mock_pool.overflow.return_value = 0

        with patch("backend.services.idle_tasks.health_monitor.psutil") as mock_psutil:
            mock_psutil.cpu_percent.return_value = 10.0
            mock_memory = MagicMock()
            mock_memory.percent = 30.0
            mock_psutil.virtual_memory.return_value = mock_memory
            mock_disk = MagicMock()
            mock_disk.percent = 40.0
            mock_psutil.disk_usage.return_value = mock_disk

            with patch("backend.models.database.engine") as mock_engine:
                mock_engine.pool = mock_pool

                # Also mock redis
                with patch("backend.services.idle_tasks.health_monitor.redis") as mock_redis_module:
                    mock_redis = MagicMock()
                    mock_redis.llen.return_value = 100
                    mock_redis_module.from_url.return_value = mock_redis

                    result = await system_resource_check(db_session, monitor)

        assert result["status"] == "completed"
        assert "warnings" in result
        assert any("DB pool" in w for w in result["warnings"])

        # Verify system_alert broadcast
        alert = await ws_capture.wait_for_event_async("system_alert", timeout=3)
        assert alert["alert_type"] == "resource_warning"
        assert any("DB pool" in w for w in alert["warnings"])
        assert alert["metrics"]["db_pool"]["checked_out"] == 10
        assert alert["metrics"]["db_pool"]["size"] == 10

    @pytest.mark.asyncio
    async def test_pool_under_threshold_no_warning(self, ws_capture, db_session):
        """Pool at 50% does not trigger warning."""
        monitor = Agent(
            agentium_id=_unique_agent_id(9),
            agent_type=AgentType.TASK_AGENT,
            name="Health Monitor 2",
            status=AgentStatus.ACTIVE
        )
        db_session.add(monitor)
        db_session.commit()

        from backend.services.idle_tasks.health_monitor import system_resource_check

        mock_pool = MagicMock()
        mock_pool.size.return_value = 10
        mock_pool.checkedout.return_value = 5  # 50% utilized
        mock_pool.overflow.return_value = 0

        with patch("backend.services.idle_tasks.health_monitor.psutil") as mock_psutil:
            mock_psutil.cpu_percent.return_value = 10.0
            mock_memory = MagicMock()
            mock_memory.percent = 30.0
            mock_psutil.virtual_memory.return_value = mock_memory
            mock_disk = MagicMock()
            mock_disk.percent = 40.0
            mock_psutil.disk_usage.return_value = mock_disk

            with patch("backend.models.database.engine") as mock_engine:
                mock_engine.pool = mock_pool

                with patch("backend.services.idle_tasks.health_monitor.redis") as mock_redis_module:
                    mock_redis = MagicMock()
                    mock_redis.llen.return_value = 100
                    mock_redis_module.from_url.return_value = mock_redis

                    result = await system_resource_check(db_session, monitor)

        db_warnings = [w for w in result.get("warnings", []) if "DB pool" in w]
        assert len(db_warnings) == 0

        # No resource_warning alert for DB pool
        pool_alerts = [e for e in ws_capture.captured_events
                      if e.get("alert_type") == "resource_warning" and any("DB pool" in w for w in e.get("warnings", []))]
        assert len(pool_alerts) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])