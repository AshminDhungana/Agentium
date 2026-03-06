"""
A/B Model Testing Service for Agentium.
Executes tasks across multiple models and compares results.

"""

import uuid
import asyncio
import time
import logging
from typing import List, Dict, Optional, Any
from datetime import datetime
from sqlalchemy.orm import Session

from backend.models.entities.ab_testing import (
    Experiment, ExperimentRun, ExperimentResult,
    ExperimentStatus, RunStatus, ModelPerformanceCache, TaskComplexity,
)
from backend.models.entities.user_config import UserModelConfig
from backend.models.database import SessionLocal
from backend.services.model_provider import ModelService, calculate_cost

logger = logging.getLogger(__name__)

# ── Transient error types that warrant a retry ────────────────────────────────
try:
    import aiohttp
    _TRANSIENT_ERRORS = (asyncio.TimeoutError, aiohttp.ClientError)
except ImportError:
    _TRANSIENT_ERRORS = (asyncio.TimeoutError,)


# ── Critic service ────────────────────────────────────────────────────────────

class CriticService:
    """Lightweight critic service for evaluating A/B test outputs."""

    def __init__(self, db: Session):
        self.db = db

    async def evaluate_output(
        self,
        task: str,
        output: str,
        system_context: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Evaluate output quality.  Attempts to use the real critic agents;
        falls back to heuristic scoring if they are unavailable.
        """
        try:
            from backend.services.critic_agents import CriticAgents
            agents = CriticAgents(self.db)
            result = await agents.run_all_critics(
                task=task,
                output=output,
                context=system_context or "",
            )
            return {
                "plan_score": result.get("plan_score", 70.0),
                "code_score": result.get("code_score", 70.0),
                "output_score": result.get("output_score", 70.0),
                "violations": result.get("violations", 0),
                "feedback": result.get("feedback", {}),
            }
        except Exception:
            return self._heuristic_score(task, output)

    def _heuristic_score(self, task: str, output: str) -> Dict[str, Any]:
        """
        Heuristic quality scoring used when critic agents are unavailable.

        Scoring rules:
          - Empty output → 0
          - Very short (<50 chars) → 40
          - Short (<200 chars) → 65
          - Reasonable (200–5000 chars) → 80
          - Very long (>5000 chars) → 78   (slight discount for verbosity, not a penalty)
          - No length cap that would rank a short reply above a thorough one.
        """
        output_len = len(output) if output else 0
        has_code = "```" in output or "def " in output or "function " in output

        if output_len == 0:
            output_score = 0.0
        elif output_len < 50:
            output_score = 40.0
        elif output_len < 200:
            output_score = 65.0
        elif output_len <= 5000:
            output_score = 80.0
        else:
            output_score = 78.0  # very long but not penalised below medium

        code_score = 76.0 if has_code else 70.0

        has_structure = any(x in output for x in ["1.", "2.", "##", "**", "- "])
        plan_score = 78.0 if has_structure else 68.0

        return {
            "plan_score": plan_score,
            "code_score": code_score,
            "output_score": output_score,
            "violations": 0,
            "feedback": {
                "plan": "Heuristic evaluation",
                "code": "Heuristic evaluation",
                "output": "Heuristic evaluation",
            },
        }


# ── Main service ──────────────────────────────────────────────────────────────

class ABTestingService:
    """Service for running A/B tests between AI models."""

    def __init__(self, db: Session):
        self.db = db
        self.critic_service = CriticService(db)

    # ── Create ────────────────────────────────────────────────────────────────

    async def create_experiment(
        self,
        name: str,
        task_template: str,
        config_ids: List[str],
        description: str = "",
        system_prompt: Optional[str] = None,
        iterations: int = 1,
        created_by: str = "",
    ) -> Experiment:
        """Create a new A/B test experiment."""
        experiment = Experiment(
            id=str(uuid.uuid4()),
            name=name,
            description=description,
            task_template=task_template,
            system_prompt=system_prompt,
            test_iterations=iterations,
            status=ExperimentStatus.DRAFT,
            created_by=created_by or "unknown",
        )
        self.db.add(experiment)

        for config_id in config_ids:
            config = self.db.query(UserModelConfig).filter(
                UserModelConfig.id == config_id
            ).first()
            model_name = config.default_model if config else "unknown"
            for i in range(1, iterations + 1):
                run = ExperimentRun(
                    id=str(uuid.uuid4()),
                    experiment_id=experiment.id,
                    config_id=config_id,
                    model_name=model_name,
                    iteration_number=i,
                    status=RunStatus.PENDING,
                )
                self.db.add(run)

        self.db.commit()
        self.db.refresh(experiment)
        return experiment

    # ── Run ───────────────────────────────────────────────────────────────────

    async def run_experiment(self, experiment_id: str) -> Experiment:
        """
        Execute all pending runs for an experiment.

        Each run opens its own DB session to avoid SQLAlchemy session
        contention when multiple coroutines run concurrently.
        """
        # Use the service's session only to update top-level experiment state
        experiment = self.db.query(Experiment).filter(
            Experiment.id == experiment_id
        ).first()
        if not experiment:
            raise ValueError(f"Experiment {experiment_id} not found")

        experiment.status = ExperimentStatus.RUNNING
        experiment.started_at = datetime.utcnow()
        self.db.commit()

        pending_run_ids = [
            r.id for r in experiment.runs if r.status == RunStatus.PENDING
        ]

        semaphore = asyncio.Semaphore(3)

        async def _run_isolated(run_id: str):
            """Execute one run with its own DB session."""
            db = SessionLocal()
            try:
                run = db.query(ExperimentRun).filter(ExperimentRun.id == run_id).first()
                if run is None:
                    return
                # Fetch experiment fields needed for execution (read-only)
                exp = db.query(Experiment).filter(Experiment.id == experiment_id).first()
                async with semaphore:
                    await self._execute_single_run(run, exp, db)
            except Exception as exc:
                logger.error("Unhandled error in run %s: %s", run_id, exc)
            finally:
                db.close()

        results = await asyncio.gather(
            *[_run_isolated(rid) for rid in pending_run_ids],
            return_exceptions=True,
        )

        failures = [r for r in results if isinstance(r, Exception)]

        # Reload experiment to see the updated run statuses written by sub-sessions
        self.db.expire_all()
        experiment = self.db.query(Experiment).filter(
            Experiment.id == experiment_id
        ).first()

        if failures and len(failures) == len(pending_run_ids):
            experiment.status = ExperimentStatus.FAILED
        else:
            experiment.status = ExperimentStatus.COMPLETED

        experiment.completed_at = datetime.utcnow()

        await self._generate_comparison(experiment)
        self.db.commit()

        # Emit WebSocket event so frontend can update without polling
        await self._emit_ws_event(experiment)

        return experiment

    # ── Execute single run ────────────────────────────────────────────────────

    async def _execute_single_run(
        self,
        run: ExperimentRun,
        experiment: Experiment,
        db: Session,
    ) -> ExperimentRun:
        """Execute one model run, with up to 3 retries for transient errors."""
        run.status = RunStatus.RUNNING
        run.started_at = datetime.utcnow()
        db.commit()

        last_error: Optional[Exception] = None
        max_attempts = 3

        for attempt in range(max_attempts):
            try:
                provider = await ModelService.get_provider(
                    experiment.created_by or "sovereign",
                    run.config_id,
                )
                if not provider:
                    raise ValueError(f"Provider not found for config {run.config_id}")

                start_time = time.time()
                result = await provider.generate(
                    system_prompt=experiment.system_prompt or "You are a helpful assistant.",
                    user_message=experiment.task_template,
                    agentium_id=f"ab-test-{run.id}",
                )
                latency_ms = int((time.time() - start_time) * 1000)

                run.output_text = result.get("content", "")
                run.tokens_used = result.get("tokens_used", 0)
                run.latency_ms = result.get("latency_ms", latency_ms)
                run.cost_usd = result.get("cost_usd") or self._estimate_cost(
                    run.config_id, run.tokens_used or 0
                )

                critic_results = await self.critic_service.evaluate_output(
                    task=experiment.task_template,
                    output=run.output_text,
                    system_context=experiment.system_prompt,
                )

                run.critic_plan_score = critic_results.get("plan_score", 0)
                run.critic_code_score = critic_results.get("code_score", 0)
                run.critic_output_score = critic_results.get("output_score", 0)
                run.critic_feedback = critic_results
                run.overall_quality_score = self._calculate_quality_score(critic_results)
                run.constitutional_violations = critic_results.get("violations", 0)
                run.status = RunStatus.COMPLETED
                run.completed_at = datetime.utcnow()
                db.commit()
                return run

            except _TRANSIENT_ERRORS as exc:
                last_error = exc
                if attempt < max_attempts - 1:
                    wait = 2 ** attempt  # 1s, 2s, 4s
                    logger.warning(
                        "Transient error on run %s (attempt %d/%d), retrying in %ds: %s",
                        run.id, attempt + 1, max_attempts, wait, exc,
                    )
                    await asyncio.sleep(wait)
                continue

            except Exception as exc:
                # Non-transient error — fail immediately
                last_error = exc
                break

        # All attempts exhausted
        run.status = RunStatus.FAILED
        run.error_message = str(last_error)
        run.completed_at = datetime.utcnow()
        db.commit()
        return run

    # ── Quality score ─────────────────────────────────────────────────────────

    def _calculate_quality_score(self, critic_results: Dict) -> float:
        weights = {"plan_score": 0.25, "code_score": 0.35, "output_score": 0.40}
        total = sum(critic_results.get(k, 0) * w for k, w in weights.items())
        return round(total, 2)

    # ── Cost estimate ─────────────────────────────────────────────────────────

    def _estimate_cost(self, config_id: str, tokens: int) -> float:
        try:
            config = self.db.query(UserModelConfig).filter(
                UserModelConfig.id == config_id
            ).first()
            if config:
                return calculate_cost(
                    model_name=config.default_model or "",
                    provider=config.provider,
                    prompt_tokens=int(tokens * 0.6),
                    completion_tokens=int(tokens * 0.4),
                )
        except Exception:
            pass
        return round((tokens / 1_000_000) * 2.0, 8)

    # ── Comparison generation ─────────────────────────────────────────────────

    async def _generate_comparison(self, experiment: Experiment) -> Optional[ExperimentResult]:
        """Generate aggregated comparison results, counting actual failures."""
        model_stats: Dict[str, Any] = {}

        for run in experiment.runs:
            key = run.config_id
            if key not in model_stats:
                model_stats[key] = {
                    "config_id": key,
                    "model_name": run.model_name,
                    "total_tokens": 0,
                    "total_cost": 0.0,
                    "total_latency": 0,
                    "quality_scores": [],
                    "completed": 0,
                    "failed": 0,
                }

            s = model_stats[key]
            if run.status == RunStatus.COMPLETED:
                s["total_tokens"] += run.tokens_used or 0
                s["total_cost"] += run.cost_usd or 0.0
                s["total_latency"] += run.latency_ms or 0
                s["quality_scores"].append(run.overall_quality_score or 0)
                s["completed"] += 1
            elif run.status == RunStatus.FAILED:
                s["failed"] += 1

        if not model_stats:
            return None

        comparisons = []
        for config_id, s in model_stats.items():
            n_completed = s["completed"]
            n_total = s["completed"] + s["failed"]

            if n_completed == 0:
                # All runs failed for this model
                comparisons.append({
                    "config_id": config_id,
                    "model_name": s["model_name"],
                    "avg_tokens": 0,
                    "avg_cost_usd": 0.0,
                    "avg_latency_ms": 0,
                    "avg_quality_score": 0.0,
                    "success_rate": 0.0,
                    "total_runs": n_total,
                    "completed_runs": 0,
                    "failed_runs": s["failed"],
                })
                continue

            comparisons.append({
                "config_id": config_id,
                "model_name": s["model_name"],
                "avg_tokens": round(s["total_tokens"] / n_completed),
                "avg_cost_usd": round(s["total_cost"] / n_completed, 6),
                "avg_latency_ms": int(s["total_latency"] / n_completed),
                "avg_quality_score": round(sum(s["quality_scores"]) / n_completed, 2),
                "success_rate": round(s["completed"] / n_total * 100, 1),
                "total_runs": n_total,
                "completed_runs": s["completed"],
                "failed_runs": s["failed"],
            })

        winner = self._determine_winner(comparisons)

        result = ExperimentResult(
            id=str(uuid.uuid4()),
            experiment_id=experiment.id,
            winner_config_id=winner["config_id"],
            winner_model_name=winner["model_name"],
            selection_reason=winner["reason"],
            model_comparisons={"models": comparisons},
            confidence_score=winner["confidence"],
        )
        self.db.add(result)

        await self._update_performance_cache(experiment, winner, comparisons)
        self.db.commit()
        return result

    # ── Winner determination ──────────────────────────────────────────────────

    def _determine_winner(self, comparisons: List[Dict]) -> Dict:
        """Determine the winning model using a composite score."""
        # Filter out models with zero successful runs
        viable = [c for c in comparisons if c["success_rate"] > 0]
        if not viable:
            return {
                "config_id": None,
                "model_name": "N/A",
                "reason": "No successful runs across any model",
                "confidence": 0,
            }

        max_cost = max((c["avg_cost_usd"] for c in viable), default=1) or 1
        max_latency = max((c["avg_latency_ms"] for c in viable), default=1) or 1

        scored = []
        for comp in viable:
            quality = comp["avg_quality_score"]
            cost_score = (1 - (comp["avg_cost_usd"] / max_cost)) * 100
            latency_score = (1 - (comp["avg_latency_ms"] / max_latency)) * 100
            success_score = comp["success_rate"]

            composite = (
                quality * 0.40
                + cost_score * 0.25
                + latency_score * 0.20
                + success_score * 0.15
            )
            scored.append({
                **comp,
                "composite_score": round(composite, 2),
                "breakdown": {
                    "quality": quality,
                    "cost_efficiency": round(cost_score, 2),
                    "speed": round(latency_score, 2),
                    "reliability": success_score,
                },
            })

        winner = max(scored, key=lambda x: x["composite_score"])
        reason = (
            f"Selected {winner['model_name']} with composite score "
            f"{winner['composite_score']}/100. "
            f"Quality: {winner['breakdown']['quality']}, "
            f"Cost-efficiency: {winner['breakdown']['cost_efficiency']}, "
            f"Speed: {winner['breakdown']['speed']}, "
            f"Reliability: {winner['breakdown']['reliability']}%"
        )

        if len(scored) > 1:
            runner_up = sorted(scored, key=lambda x: x["composite_score"], reverse=True)[1]
            margin = winner["composite_score"] - runner_up["composite_score"]
            confidence = min(100.0, max(50.0, 50.0 + margin * 2))
        else:
            confidence = 75.0

        return {
            "config_id": winner["config_id"],
            "model_name": winner["model_name"],
            "reason": reason,
            "confidence": round(confidence, 2),
        }

    # ── Performance cache ─────────────────────────────────────────────────────

    async def _update_performance_cache(
        self,
        experiment: Experiment,
        winner: Dict,
        comparisons: List[Dict],
    ):
        """Update the model performance cache with experiment results."""
        if not winner["config_id"]:
            return

        task_category = "general"
        task_lower = (experiment.task_template or "").lower()
        if any(w in task_lower for w in ["code", "function", "def ", "class "]):
            task_category = "coding"
        elif any(w in task_lower for w in ["summarize", "summarise", "summary", "tldr"]):
            task_category = "summarization"
        elif any(w in task_lower for w in ["translate", "translation"]):
            task_category = "translation"
        elif any(w in task_lower for w in ["analyse", "analyze", "analysis"]):
            task_category = "analysis"

        winner_stats = next(
            (c for c in comparisons if c["config_id"] == winner["config_id"]), None
        )
        if not winner_stats:
            return

        existing = self.db.query(ModelPerformanceCache).filter(
            ModelPerformanceCache.task_category == task_category
        ).first()

        if existing:
            existing.best_config_id = winner["config_id"]
            existing.best_model_name = winner["model_name"]
            existing.avg_latency_ms = winner_stats.get("avg_latency_ms", 0)
            existing.avg_cost_usd = winner_stats.get("avg_cost_usd", 0.0)
            existing.avg_quality_score = winner_stats.get("avg_quality_score", 0.0)
            existing.success_rate = winner_stats.get("success_rate", 0.0)
            existing.sample_size = (existing.sample_size or 0) + winner_stats.get("total_runs", 0)
            existing.derived_from_experiment_id = experiment.id
            existing.last_updated = datetime.utcnow()
        else:
            cache_entry = ModelPerformanceCache(
                id=str(uuid.uuid4()),
                task_category=task_category,
                task_complexity=TaskComplexity.MEDIUM,
                best_config_id=winner["config_id"],
                best_model_name=winner["model_name"],
                avg_latency_ms=winner_stats.get("avg_latency_ms", 0),
                avg_cost_usd=winner_stats.get("avg_cost_usd", 0.0),
                avg_quality_score=winner_stats.get("avg_quality_score", 0.0),
                success_rate=winner_stats.get("success_rate", 0.0),
                sample_size=winner_stats.get("total_runs", 0),
                derived_from_experiment_id=experiment.id,
                last_updated=datetime.utcnow(),
            )
            self.db.add(cache_entry)

    # ── WebSocket notification ────────────────────────────────────────────────

    async def _emit_ws_event(self, experiment: Experiment) -> None:
        """
        Emit a WebSocket event when experiment status changes.
        This lets the frontend update without relying on polling.
        """
        try:
            from backend.websocket.manager import ws_manager  # adjust import to your project
            await ws_manager.broadcast({
                "type": "ab_test_update",
                "metadata": {
                    "experiment_id": experiment.id,
                    "status": experiment.status.value,
                },
            })
        except Exception as exc:
            # Never let WS emission crash the service
            logger.debug("WebSocket emit skipped: %s", exc)