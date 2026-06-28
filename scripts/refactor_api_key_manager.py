"""Refactor api_key_manager.py session boilerplate."""
import pathlib, re

p = pathlib.Path("backend/services/api_key_manager.py")
text = p.read_text()

# Helper: replace inner _update + if/else with inline db usage

def replace_method(text, method_name, inner_func_name, inner_body, new_body):
    """Replace a method's inner _func and if/else boilerplate with inline body."""
    # This is a simplified placeholder - we'll use regex for precision
    pass

# We'll use a simpler block-replacement strategy for each method

# 1. record_spend: add decorator, replace _update body
old_record_spend = """    def record_spend(
        self,
        key_id: str,
        cost_usd: float,
        tokens_used: int = 0,
        db: Optional[Session] = None
    ) -> Dict[str, Any]:"""
new_record_spend = """    @with_db_session
    def record_spend(
        self,
        key_id: str,
        cost_usd: float,
        tokens_used: int = 0,
        db: Optional[Session] = None
    ) -> Dict[str, Any]:"""
text = text.replace(old_record_spend, new_record_spend, 1)

# Now replace the _update inner + if/else wrapper for record_spend
old_body = """        def _update(db_session: Session) -> Dict[str, Any]:
            now = datetime.utcnow()

            # Single atomic statement: if we've rolled into a new month,
            # reset current_spend_usd to just this charge and bump
            # last_spend_reset; otherwise add to the existing total.
            # The CASE conditions are evaluated server-side against the
            # row's actual current values at UPDATE time (under the
            # row lock Postgres takes for the UPDATE), so there is no
            # read-then-write gap for a concurrent request to land in.
            row = db_session.execute(
                text(\"\"\"
                    UPDATE user_model_configs
                    SET
                        current_spend_usd = CASE
                            WHEN EXTRACT(MONTH FROM last_spend_reset) != EXTRACT(MONTH FROM :now)
                                 OR EXTRACT(YEAR FROM last_spend_reset) != EXTRACT(YEAR FROM :now)
                            THEN :cost_usd
                            ELSE current_spend_usd + :cost_usd
                        END,
                        last_spend_reset = CASE
                            WHEN EXTRACT(MONTH FROM last_spend_reset) != EXTRACT(MONTH FROM :now)
                                 OR EXTRACT(YEAR FROM last_spend_reset) != EXTRACT(YEAR FROM :now)
                            THEN :now
                            ELSE last_spend_reset
                        END,
                        total_requests = total_requests + 1,
                        estimated_cost_usd = COALESCE(estimated_cost_usd, 0) + :cost_usd
                    WHERE id = :key_id
                    RETURNING current_spend_usd, monthly_budget_usd
                \"\"\"),
                {\"key_id\": key_id, \"cost_usd\": cost_usd, \"now\": now},
            ).first()

            if row is None:
                logger.warning(f\"record_spend: key {key_id} not found\")
                return {}

            current_spend_usd, monthly_budget_usd = float(row[0]), float(row[1] or 0.0)
            budget_exceeded = monthly_budget_usd > 0 and current_spend_usd >= monthly_budget_usd

            if budget_exceeded:
                logger.warning(
                    f\"💸 Key {key_id} monthly budget EXHAUSTED: \"
                    f\"${current_spend_usd:.2f} / ${monthly_budget_usd:.2f}\"
                )
                self._notify_budget_exceeded(key_id, current_spend_usd, monthly_budget_usd, db_session)
            else:
                # Early-warning thresholds so spend is visible before the
                # hard cap is hit, not just after.
                self._maybe_warn_budget_threshold(key_id, current_spend_usd, monthly_budget_usd)

            return {
                \"current_spend_usd\": current_spend_usd,
                \"monthly_budget_usd\": monthly_budget_usd,
                \"budget_exceeded\": budget_exceeded,
                \"remaining_usd\": (
                    max(0.0, monthly_budget_usd - current_spend_usd)
                    if monthly_budget_usd > 0 else None
                ),
            }

        if db:
            return _update(db)
        else:
            with get_db_context() as db_session:
                result = _update(db_session)
                db_session.commit()
                return result"""

new_body = """        now = datetime.utcnow()

        # Single atomic statement: if we've rolled into a new month,
        # reset current_spend_usd to just this charge and bump
        # last_spend_reset; otherwise add to the existing total.
        # The CASE conditions are evaluated server-side against the
        # row's actual current values at UPDATE time (under the
        # row lock Postgres takes for the UPDATE), so there is no
        # read-then-write gap for a concurrent request to land in.
        row = db.execute(
            text(\"\"\"
                UPDATE user_model_configs
                SET
                    current_spend_usd = CASE
                        WHEN EXTRACT(MONTH FROM last_spend_reset) != EXTRACT(MONTH FROM :now)
                             OR EXTRACT(YEAR FROM last_spend_reset) != EXTRACT(YEAR FROM :now)
                        THEN :cost_usd
                        ELSE current_spend_usd + :cost_usd
                    END,
                    last_spend_reset = CASE
                        WHEN EXTRACT(MONTH FROM last_spend_reset) != EXTRACT(MONTH FROM :now)
                             OR EXTRACT(YEAR FROM last_spend_reset) != EXTRACT(YEAR FROM :now)
                        THEN :now
                        ELSE last_spend_reset
                    END,
                    total_requests = total_requests + 1,
                    estimated_cost_usd = COALESCE(estimated_cost_usd, 0) + :cost_usd
                WHERE id = :key_id
                RETURNING current_spend_usd, monthly_budget_usd
            \"\"\"),
            {\"key_id\": key_id, \"cost_usd\": cost_usd, \"now\": now},
        ).first()

        if row is None:
            logger.warning(f\"record_spend: key {key_id} not found\")
            return {}

        current_spend_usd, monthly_budget_usd = float(row[0]), float(row[1] or 0.0)
        budget_exceeded = monthly_budget_usd > 0 and current_spend_usd >= monthly_budget_usd

        if budget_exceeded:
            logger.warning(
                f\"💸 Key {key_id} monthly budget EXHAUSTED: \"
                f\"${current_spend_usd:.2f} / ${monthly_budget_usd:.2f}\"
            )
            self._notify_budget_exceeded(key_id, current_spend_usd, monthly_budget_usd, db)
        else:
            # Early-warning thresholds so spend is visible before the
            # hard cap is hit, not just after.
            self._maybe_warn_budget_threshold(key_id, current_spend_usd, monthly_budget_usd)

        return {
            \"current_spend_usd\": current_spend_usd,
            \"monthly_budget_usd\": monthly_budget_usd,
            \"budget_exceeded\": budget_exceeded,
            \"remaining_usd\": (
                max(0.0, monthly_budget_usd - current_spend_usd)
                if monthly_budget_usd > 0 else None
            ),
        }"""

text = text.replace(old_body, new_body, 1)

# 2. check_budget
old = """    def check_budget(self, key_id: str, estimated_cost: float, db: Optional[Session] = None) -> bool:
        \"\"\"\"""""" # truncated for brevity
