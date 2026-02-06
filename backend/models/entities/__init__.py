"""
Agentium Entity Models
======================
All database entities for the AI governance system.

Hierarchy:
- BaseEntity: Abstract base with common fields (id, timestamps, soft delete)
- Constitution & Ethos: Governance documents
- Agents: 4-tier hierarchy (Head, Council, Lead, Task)
- Tasks: Work units with lifecycle management
- Voting: Democratic deliberation system
- Audit: Transparency and compliance logging
- Monitoring: Hierarchical oversight and agent health tracking
"""
from backend.models.entities.channels import (
    ExternalChannel,
    ExternalMessage,
    ChannelType,
    ChannelStatus
)

from backend.models.entities.scheduled_task import (
    ScheduledTask, 
    ScheduledTaskExecution,
    ScheduledTaskStatus,
    ScheduledTaskExecutionStatus
)

from backend.models.entities.task import (
    Task,
    SubTask,
    TaskAuditLog,
    TaskStatus,
    TaskPriority,
    TaskType
)

from backend.models.entities.user_config import (
    UserModelConfig,
    ProviderType,
    ConnectionStatus,
    ModelUsageLog
)

from backend.models.entities.base import Base, BaseEntity

from backend.models.entities.constitution import (
    Constitution, 
    Ethos, 
    DocumentType
)

from backend.models.entities.agents import (
    Agent,
    HeadOfCouncil,
    CouncilMember,
    LeadAgent,
    TaskAgent,
    AgentType,
    AgentStatus,
    AGENT_TYPE_MAP
)

from backend.models.entities.voting import (
    TaskDeliberation,
    IndividualVote,
    VotingRecord,
    VoteType,
    DeliberationStatus,
    AmendmentVoting,
    AmendmentStatus
)

from backend.models.entities.audit import (
    AuditLog,
    ConstitutionViolation,
    SessionLog,
    HealthCheck,
    AuditLevel,
    AuditCategory
)

from backend.models.entities.monitoring import (
    AgentHealthReport,
    ViolationReport,
    ViolationSeverity,
    TaskVerification,
    PerformanceMetric,
    MonitoringAlert,
    MonitoringStatus
)

# All models for Alembic/database creation
__all__ = [
    # Base
    'Base',
    'BaseEntity',
    
    # User Configuration (Frontend-managed models)
    'UserModelConfig',
    'ProviderType', 
    'ConnectionStatus',
    'ModelUsageLog',
    
    # Constitution
    'Constitution',
    'Ethos', 
    'AmendmentVoting',
    'DocumentType',
    'AmendmentStatus',

    'ScheduledTask',
    'ScheduledTaskExecution', 
    'ScheduledTaskStatus',
    'ScheduledTaskExecutionStatus',


    'ExternalChannel',
    'ExternalMessage', 
    'ChannelType',
    'ChannelStatus',
    
    # Agents
    'Agent',
    'HeadOfCouncil',
    'CouncilMember',
    'LeadAgent',
    'TaskAgent',
    'AgentType',
    'AgentStatus',
    'AGENT_TYPE_MAP',
    
    # Tasks
    'Task',
    'SubTask',
    'TaskAuditLog',
    'TaskStatus',
    'TaskPriority',
    'TaskType',
    
    # Voting
    'TaskDeliberation',
    'IndividualVote',
    'VotingRecord',
    'VoteType',
    'DeliberationStatus',
    
    # Audit
    'AuditLog',
    'ConstitutionViolation',
    'SessionLog',
    'HealthCheck',
    'AuditLevel',
    'AuditCategory',
    
    # Monitoring (Checks and Balances)
    'AgentHealthReport',
    'ViolationReport',
    'ViolationSeverity',
    'TaskVerification',
    'PerformanceMetric',
    'MonitoringAlert',
    'MonitoringStatus'
]