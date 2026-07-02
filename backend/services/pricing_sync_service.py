"""
Pricing Synchronization Service for Agentium.
Fetches up-to-date pricing data from the LiteLLM registry and stores it in the database.
"""

import logging
import httpx
from typing import Optional, Dict, Tuple
from sqlalchemy.orm import Session
from backend.models.entities.model_pricing import ModelPricing

logger = logging.getLogger(__name__)


class PricingSyncService:
    """PricingSyncService."""
    # Class-level cache (model_id_lower -> (input_rate_per_1m, output_rate_per_1m))
    _cache: Dict[str, Tuple[float, float]] = {}
    _initialized = False

    @classmethod
    def load_cache_from_db(cls, db: Session):
        """Pre-populate the in-memory cache from the database."""
        try:
            pricings = db.query(ModelPricing).filter_by(is_active=True).all()
            cls._cache = {
                p.model_id.lower().strip(): (p.input_rate_per_1m, p.output_rate_per_1m)
                for p in pricings
            }
            cls._initialized = True
            logger.info(f"Loaded {len(cls._cache)} model prices from DB into memory cache.")
        except Exception as e:
            logger.error(f"Failed to load pricing cache from DB: {e}")

    @classmethod
    def get_price(cls, model_id: str, db: Optional[Session] = None) -> Optional[Tuple[float, float]]:
        """
        Retrieve pricing for a given model ID (case-insensitive).
        Checks the in-memory cache first. If not found and a db session is provided,
        checks the database and caches it.
        """
        if not model_id:
            return None
            
        normalized = model_id.lower().strip()
        
        # 1. In-memory lookup
        if normalized in cls._cache:
            return cls._cache[normalized]
            
        # 2. Database lookup (fallback)
        if db:
            try:
                pricing = db.query(ModelPricing).filter(
                    ModelPricing.model_id == normalized,
                    ModelPricing.is_active == True
                ).first()
                if pricing:
                    rates = (pricing.input_rate_per_1m, pricing.output_rate_per_1m)
                    cls._cache[normalized] = rates
                    return rates
            except Exception as e:
                logger.error(f"Error querying ModelPricing for model {model_id}: {e}")
                
        return None

    @classmethod
    async def sync_prices(cls, db: Session) -> dict:
        """
        Download pricing data from LiteLLM's public registry and upsert it into the database.
        Updates the in-memory cache upon success.
        """
        url = "https://raw.githubusercontent.com/BerriAI/litellm/main/model_prices_and_context_window.json"
        logger.info(f"Synchronizing LLM prices from {url}...")
        
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(url)
                if resp.status_code != 200:
                    raise Exception(f"HTTP error {resp.status_code}")
                pricing_data = resp.json()
        except Exception as e:
            logger.error(f"Failed to fetch remote pricing JSON: {e}")
            # Ensure cache is at least loaded from DB if we haven't yet
            if not cls._initialized:
                cls.load_cache_from_db(db)
            return {"success": False, "error": f"Network fetch failed: {str(e)}"}

        added_count = 0
        updated_count = 0
        
        # Process and upsert models
        try:
            # Load existing models to optimize updates
            existing = {p.model_id.lower().strip(): p for p in db.query(ModelPricing).all()}
            processed_model_ids = set()
            
            for model_name, info in pricing_data.items():
                if not isinstance(info, dict):
                    continue
                    
                model_id_normalized = model_name.lower().strip()
                if model_id_normalized in processed_model_ids:
                    continue
                processed_model_ids.add(model_id_normalized)
                
                # Fetch input/output rates per token
                input_cost_per_token = info.get("input_cost_per_token")
                output_cost_per_token = info.get("output_cost_per_token")
                
                # Skip models that have no pricing defined
                if input_cost_per_token is None or output_cost_per_token is None:
                    continue
                    
                # Convert to rate per 1M tokens
                input_rate = float(input_cost_per_token) * 1_000_000
                output_rate = float(output_cost_per_token) * 1_000_000
                
                # Determine provider
                raw_provider = info.get("litellm_provider") or info.get("provider") or ""
                provider_str = str(raw_provider).upper().strip() if raw_provider else "CUSTOM"
                
                if model_id_normalized in existing:
                    pricing_record = existing[model_id_normalized]
                    # Update rates if changed
                    if (pricing_record.input_rate_per_1m != input_rate or 
                            pricing_record.output_rate_per_1m != output_rate):
                        pricing_record.input_rate_per_1m = input_rate
                        pricing_record.output_rate_per_1m = output_rate
                        pricing_record.provider = provider_str
                        pricing_record.is_active = True
                        updated_count += 1
                else:
                    new_pricing = ModelPricing(
                        model_id=model_id_normalized,
                        provider=provider_str,
                        input_rate_per_1m=input_rate,
                        output_rate_per_1m=output_rate,
                        is_active=True
                    )
                    db.add(new_pricing)
                    added_count += 1
            
            db.commit()
            
            # Refresh in-memory cache
            cls.load_cache_from_db(db)
            
            logger.info(f"Pricing synchronization complete. Added {added_count}, updated {updated_count} models.")
            return {
                "success": True,
                "added": added_count,
                "updated": updated_count,
                "total_cached": len(cls._cache)
            }
            
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to upsert pricing data: {e}")
            return {"success": False, "error": f"Database write failed: {str(e)}"}
