"""
Model Pricing database entity.
Stores dynamic pricing for different models and providers.
"""
import random
from datetime import datetime
from sqlalchemy import Column, String, Float

from .base import BaseEntity


class ModelPricing(BaseEntity):
    """
    Dynamic model pricing tracking table.
    Stores prompt and completion costs per 1M tokens in USD.
    """
    __tablename__ = 'model_pricings'

    # Model ID returned by the API (e.g. 'gpt-4o', 'claude-3-5-sonnet-20241022')
    model_id = Column(String(150), unique=True, nullable=False, index=True)
    
    # Provider identifier (e.g. 'OPENAI', 'ANTHROPIC')
    provider = Column(String(50), nullable=False)
    
    # Cost in USD per 1M tokens
    input_rate_per_1m = Column(Float, nullable=False, default=0.0)
    output_rate_per_1m = Column(Float, nullable=False, default=0.0)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if not self.agentium_id:
            import uuid
            self.agentium_id = f"P{uuid.uuid4().hex[:9]}"

    def to_dict(self) -> dict:
        base = super().to_dict()
        base.update({
            'model_id': self.model_id,
            'provider': self.provider,
            'input_rate_per_1m': self.input_rate_per_1m,
            'output_rate_per_1m': self.output_rate_per_1m,
        })
        return base
