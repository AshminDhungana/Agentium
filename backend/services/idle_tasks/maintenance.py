"""
Scheduled maintenance idle tasks for Strategic Planner (10002).
"""
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any
from sqlalchemy.orm import Session
from sqlalchemy import func

from backend.models.entities.agents import Agent
from backend.models.entities.task import Task, TaskStatus, TaskType
from backend.models.entities.constitution import ConstitutionArticle
from backend.services.agent_bridge import agent_bridge

logger = logging.getLogger(__name__)

# ─── Constitution Review ──────────────────────────────────────────────────

async def constitution_review(db: Session, agent: Agent) -> Dict[str, Any]:
    """
    Weekly constitution review: analyze articles, detect conflicts,
    propose refinements. Runs weekly (cooldown 7 days).
    """
    # Get all active articles
    articles = db.query(ConstitutionArticle).filter(
        ConstitutionArticle.is_active == True
    ).all()
    
    proposals = []
    
    # Check for stale articles (not reviewed in 90 days)
    for art in articles:
        if art.updated_at < datetime.utcnow() - timedelta(days=90):
            proposals.append({
                'article_id': art.id,
                'article_number': art.article_number,
                'type': 'stale_review',
                'message': f'Article {art.article_number} not reviewed in 90+ days',
                'priority': 'medium'
            })
    
    # Check for conflicting keywords (simplified)
    # In practice, use NLP or LLM for semantic conflict detection
    
    # Check for articles with high violation rates
    # (would need violation tracking - placeholder)
    
    result = {
        'status': 'completed',
        'analyzed': len(articles),
        'proposals': proposals,
        'timestamp': datetime.utcnow().isoformat()
    }
    
    if proposals:
        logger.info(f"Constitution review: {len(proposals)} proposals")
        await agent_bridge.broadcast_event('constitution_proposals', {
            'proposals': proposals,
            'timestamp': datetime.utcnow().isoformat()
        })
    
    return result

# ─── Predictive Scaling ───────────────────────────────────────────────────

async def predictive_scaling(db: Session, agent: Agent) -> Dict[str, Any]:
    """
    Daily predictive scaling: forecast resource needs based on trends,
    recommend preemptive scaling actions. Runs daily.
    """
    # Analyze task volume trends (last 7 days)
    since = datetime.utcnow() - timedelta(days=7)
    tasks = db.query(Task).filter(Task.created_at >= since).all()
    
    # Daily volume
    daily_counts = {}
    for t in tasks:
        day = t.created_at.date().isoformat()
        daily_counts[day] = daily_counts.get(day, 0) + 1
    
    # Simple trend: average daily growth
    volumes = list(daily_counts.values())
    if len(volumes) >= 3:
        recent_avg = sum(volumes[-3:]) / 3
        older_avg = sum(volumes[:-3]) / max(len(volumes) - 3, 1)
        growth_rate = (recent_avg - older_avg) / max(older_avg, 1)
    else:
        growth_rate = 0
        recent_avg = sum(volumes) / max(len(volumes), 1)
    
    # Current resource usage (simplified)
    forecast = {
        'current_daily_avg': recent_avg,
        'growth_rate_pct': growth_rate * 100,
        'projected_7d': recent_avg * (1 + growth_rate) ** 7,
        'projected_30d': recent_avg * (1 + growth_rate) ** 30
    }
    
    recommendations = []
    if growth_rate > 0.2:  # >20% growth
        recommendations.append({
            'action': 'scale_workers',
            'reason': f'Task volume growing at {growth_rate*100:.1f}%/day',
            'urgency': 'high' if growth_rate > 0.5 else 'medium'
        })
    if forecast['projected_7d'] > 1000:
        recommendations.append({
            'action': 'increase_db_pool',
            'reason': f'Projected 7-day volume: {forecast["projected_7d"]:.0f} tasks/day',
            'urgency': 'medium'
        })
    
    result = {
        'status': 'completed',
        'forecast': forecast,
        'recommendations': recommendations,
        'timestamp': datetime.utcnow().isoformat()
    }
    
    if recommendations:
        logger.info(f"Predictive scaling: {len(recommendations)} recommendations")
        await agent_bridge.broadcast_event('scaling_recommendations', {
            'recommendations': recommendations,
            'forecast': forecast,
            'timestamp': datetime.utcnow().isoformat()
        })
    
    return result