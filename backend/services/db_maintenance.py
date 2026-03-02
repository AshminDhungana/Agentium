"""
Database Maintenance and Backup Service for Agentium (Phase 9)
Handles audit log archival, task history cleanup, constitution version cleanup,
vector DB optimization, backup rotation, and triggers basic snapshot logical backups.
"""

from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import text
import logging
import asyncio
import os
import glob
import subprocess

from backend.models.database import get_db_context
from backend.models.entities.audit import AuditLog
from backend.models.entities.task import Task
from backend.models.entities.constitution import Constitution
from backend.services.alert_manager import AlertManager
from backend.models.entities.monitoring import MonitoringAlert, ViolationSeverity
from backend.core.config import settings
from backend.models.database import get_system_agent_id

logger = logging.getLogger(__name__)


class DatabaseMaintenanceService:
    """Handles routine database cleanup, archival, and trigger for backups."""

    @staticmethod
    async def cleanup_stale_data():
        """
        Background task: Daily cleanup of old audit logs, archived tasks,
        constitution versions, and stale messages.
        Phase 9.2: Memory Management Requirement
        """
        while True:
            try:
                with get_db_context() as db:
                    alert_manager = AlertManager(db)
                    report = {
                        "audit_logs_deleted": 0,
                        "tasks_deleted": 0,
                        "constitution_versions_pruned": 0,
                    }

                    # 1. Clean up Audit Logs older than configured retention
                    audit_cutoff = datetime.utcnow() - timedelta(
                        days=settings.AUDIT_LOG_RETENTION_DAYS
                    )
                    report["audit_logs_deleted"] = (
                        db.query(AuditLog)
                        .filter(AuditLog.created_at < audit_cutoff)
                        .delete()
                    )

                    # 2. Archive completed/cancelled/failed tasks older than
                    #    configured archive period
                    task_cutoff = datetime.utcnow() - timedelta(
                        days=settings.TASK_ARCHIVE_DAYS
                    )
                    report["tasks_deleted"] = (
                        db.query(Task)
                        .filter(
                            Task.status.in_(
                                ["completed", "cancelled", "failed"]
                            ),
                            Task.updated_at < task_cutoff,
                        )
                        .delete()
                    )

                    # 3. Constitution version cleanup
                    #    Keep last N versions, NEVER delete version 1
                    report["constitution_versions_pruned"] = (
                        DatabaseMaintenanceService._prune_constitution_versions(
                            db
                        )
                    )

                    db.commit()

                    total = sum(report.values())
                    if total > 0:
                        logger.info(
                            f"DB Maintenance: {report['audit_logs_deleted']} "
                            f"audit logs, {report['tasks_deleted']} tasks, "
                            f"{report['constitution_versions_pruned']} "
                            f"constitution versions cleaned up."
                        )

            except Exception as e:
                logger.error(f"Error in DB cleanup routine: {e}")

            await asyncio.sleep(86400)  # Sleep 24 hours

    @staticmethod
    def _prune_constitution_versions(db: Session) -> int:
        """
        Keep the latest N constitution versions plus version 1 (original).
        Returns the number of pruned versions.
        Phase 9.2 requirement: NEVER delete original constitution.
        """
        all_versions = (
            db.query(Constitution)
            .order_by(Constitution.version.desc())
            .all()
        )

        if len(all_versions) <= settings.CONSTITUTION_MAX_VERSIONS:
            return 0

        # Versions to keep: the latest N + version 1
        keep_ids = set()
        for v in all_versions[: settings.CONSTITUTION_MAX_VERSIONS]:
            keep_ids.add(v.id)

        # Always keep version 1 (original)
        for v in all_versions:
            if v.version == 1:
                keep_ids.add(v.id)
                break

        # Delete the rest
        pruned = 0
        for v in all_versions:
            if v.id not in keep_ids:
                db.delete(v)
                pruned += 1

        return pruned

    @staticmethod
    async def vector_db_optimization():
        """
        Background task: Weekly vector DB optimization.
        Removes duplicate embeddings from ChromaDB collections.
        Phase 9.2 requirement.
        """
        while True:
            try:
                from backend.core.vector_db import VectorStore
                vs = VectorStore()
                optimized_count = 0

                for collection_name in [
                    "constitution", "task_learnings",
                    "domain_knowledge", "execution_patterns",
                    "rejected",
                ]:
                    try:
                        col = vs.client.get_or_create_collection(
                            name=collection_name
                        )
                        before_count = col.count()
                        if before_count == 0:
                            continue

                        # Get all docs and remove exact duplicates
                        all_docs = col.get(include=["documents"])
                        if not all_docs or not all_docs.get("ids"):
                            continue

                        seen = {}
                        to_delete = []
                        for i, doc in enumerate(
                            all_docs.get("documents", [])
                        ):
                            if doc in seen:
                                to_delete.append(all_docs["ids"][i])
                            else:
                                seen[doc] = all_docs["ids"][i]

                        if to_delete:
                            col.delete(ids=to_delete)
                            optimized_count += len(to_delete)

                    except Exception as col_err:
                        logger.warning(
                            f"Vector optimization skipped "
                            f"{collection_name}: {col_err}"
                        )

                if optimized_count > 0:
                    logger.info(
                        f"Vector DB optimization: removed "
                        f"{optimized_count} duplicate entries."
                    )
            except Exception as e:
                logger.error(f"Error in vector_db_optimization: {e}")

            await asyncio.sleep(604800)  # Weekly

    @staticmethod
    async def index_maintenance():
        """
        Background task: Weekly REINDEX and ANALYZE on key tables.
        Phase 9.2 requirement.

        Table list is read from db_maintenance_config so it stays in sync
        with schema changes.  Falls back to a hardcoded default if the config
        row is absent (e.g. during initial setup).

        Each ANALYZE runs in its own autocommit connection so that a failure
        on one table never aborts the remaining tables.
        """
        while True:
            try:
                from backend.models.database import engine

                # --- resolve table list from config, with safe fallback ---
                default_tables = [
                    "agents", "tasks", "audit_logs", "individual_votes",
                    "constitutions", "monitoring_alerts",
                ]
                try:
                    with engine.connect() as cfg_conn:
                        row = cfg_conn.execute(text(
                            "SELECT config_value FROM db_maintenance_config "
                            "WHERE config_key = 'analyze_tables'"
                        )).fetchone()
                    import json as _json
                    key_tables = _json.loads(row[0]) if row else default_tables
                except Exception as cfg_err:
                    logger.warning(
                        f"Could not read analyze_tables config, "
                        f"using defaults: {cfg_err}"
                    )
                    key_tables = default_tables

                # --- run each ANALYZE in its own autocommit connection so a
                #     single failure cannot abort the remaining tables ----------
                analyzed, skipped = [], []
                for table in key_tables:
                    try:
                        with engine.connect() as conn:
                            conn.execute(text("COMMIT"))          # exit any implicit txn
                            conn.execute(text(f"ANALYZE {table}"))
                        analyzed.append(table)
                    except Exception as tbl_err:
                        skipped.append(table)
                        logger.warning(
                            f"ANALYZE skipped for {table}: {tbl_err}"
                        )

                logger.info(
                    f"Index maintenance: ANALYZE completed "
                    f"({len(analyzed)} tables). "
                    + (f"Skipped: {skipped}" if skipped else "")
                )
            except Exception as e:
                logger.error(f"Error in index_maintenance: {e}")

            await asyncio.sleep(604800)  # Weekly

    @staticmethod
    async def trigger_pg_dump():
        """
        Triggers a local pg_dump backup script with rotation.
        Keeps last 7 daily backups, deletes older ones.
        Phase 9.3: Backup & Disaster Recovery
        """
        while True:
            try:
                db_url = os.getenv("DATABASE_URL")
                backup_dir = os.getenv(
                    "BACKUP_DIR", "/tmp/agentium_backups"
                )

                if db_url and "postgresql" in db_url:
                    if not os.path.exists(backup_dir):
                        os.makedirs(backup_dir, exist_ok=True)

                    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
                    backup_file = os.path.join(
                        backup_dir, f"backup_{timestamp}.sql"
                    )

                    command = f"pg_dump {db_url} > {backup_file}"

                    process = await asyncio.create_subprocess_shell(
                        command,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                    )

                    stdout, stderr = await process.communicate()

                    if process.returncode == 0:
                        logger.info(
                            f"Database backup successful: {backup_file}"
                        )
                        # Rotate: keep last 7 backups
                        DatabaseMaintenanceService._rotate_backups(
                            backup_dir, keep=7
                        )
                    else:
                        logger.error(
                            f"Database backup failed: {stderr.decode()}"
                        )
                        with get_db_context() as db:
                            am = AlertManager(db)
                            alert = MonitoringAlert(
                                alert_type="backup_failure",
                                severity=ViolationSeverity.CRITICAL,
                                detected_by_agent_id=get_system_agent_id(db),
                                affected_agent_id=None,
                                message=(
                                    f"Daily PostgreSQL backup failed: "
                                    f"{stderr.decode()}"
                                ),
                            )
                            db.add(alert)
                            db.commit()
                            await am.dispatch_alert(alert)

            except Exception as e:
                logger.error(f"Error triggering pg_dump: {e}")

            await asyncio.sleep(86400)  # Daily Backups

    @staticmethod
    def _rotate_backups(backup_dir: str, keep: int = 7):
        """
        Keep only the most recent `keep` backup files, delete older ones.
        Phase 9.3 requirement.
        """
        pattern = os.path.join(backup_dir, "backup_*.sql")
        files = sorted(glob.glob(pattern), reverse=True)
        for old_file in files[keep:]:
            try:
                os.remove(old_file)
                logger.info(f"Rotated old backup: {old_file}")
            except OSError as e:
                logger.warning(f"Failed to remove old backup {old_file}: {e}")

    @staticmethod
    async def vector_db_snapshot():
        """
        Background task: Weekly ChromaDB data directory backup.
        Phase 9.3 requirement.
        """
        while True:
            try:
                chroma_dir = settings.CHROMA_PERSIST_DIR
                backup_dir = os.getenv(
                    "BACKUP_DIR", "/tmp/agentium_backups"
                )
                if os.path.exists(chroma_dir):
                    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
                    snapshot_file = os.path.join(
                        backup_dir, f"chromadb_{timestamp}.tar.gz"
                    )
                    os.makedirs(backup_dir, exist_ok=True)

                    process = await asyncio.create_subprocess_shell(
                        f"tar -czf {snapshot_file} -C {chroma_dir} .",
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                    )
                    stdout, stderr = await process.communicate()

                    if process.returncode == 0:
                        logger.info(
                            f"ChromaDB snapshot successful: {snapshot_file}"
                        )
                        # Keep last 4 weekly snapshots
                        DatabaseMaintenanceService._rotate_vector_snapshots(
                            backup_dir, keep=4
                        )
                    else:
                        logger.error(
                            f"ChromaDB snapshot failed: {stderr.decode()}"
                        )
            except Exception as e:
                logger.error(f"Error in vector_db_snapshot: {e}")

            await asyncio.sleep(604800)  # Weekly

    @staticmethod
    def _rotate_vector_snapshots(backup_dir: str, keep: int = 4):
        """Keep only the most recent `keep` ChromaDB snapshots."""
        pattern = os.path.join(backup_dir, "chromadb_*.tar.gz")
        files = sorted(glob.glob(pattern), reverse=True)
        for old_file in files[keep:]:
            try:
                os.remove(old_file)
                logger.info(f"Rotated old vector snapshot: {old_file}")
            except OSError as e:
                logger.warning(
                    f"Failed to remove old snapshot {old_file}: {e}"
                )

    @staticmethod
    def get_maintenance_report(db: Session) -> dict:
        """
        Returns summary of last cleanup operations.
        Phase 9.2 utility.
        """
        audit_cutoff = datetime.utcnow() - timedelta(
            days=settings.AUDIT_LOG_RETENTION_DAYS
        )
        task_cutoff = datetime.utcnow() - timedelta(
            days=settings.TASK_ARCHIVE_DAYS
        )

        return {
            "audit_logs_eligible_for_cleanup": (
                db.query(AuditLog)
                .filter(AuditLog.created_at < audit_cutoff)
                .count()
            ),
            "tasks_eligible_for_archive": (
                db.query(Task)
                .filter(
                    Task.status.in_(["completed", "cancelled", "failed"]),
                    Task.updated_at < task_cutoff,
                )
                .count()
            ),
            "constitution_versions": (
                db.query(Constitution).count()
            ),
            "max_kept_versions": settings.CONSTITUTION_MAX_VERSIONS,
            "retention_config": {
                "audit_log_days": settings.AUDIT_LOG_RETENTION_DAYS,
                "task_archive_days": settings.TASK_ARCHIVE_DAYS,
            },
        }

    @classmethod
    def start_maintenance_monitors(cls):
        """Starts all detached asynchronous maintenance loops (Phase 9)."""
        asyncio.create_task(cls.cleanup_stale_data())
        asyncio.create_task(cls.trigger_pg_dump())
        asyncio.create_task(cls.vector_db_optimization())
        asyncio.create_task(cls.index_maintenance())
        asyncio.create_task(cls.vector_db_snapshot())