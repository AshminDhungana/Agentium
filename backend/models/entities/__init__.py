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
- MCP Tools: Constitutional MCP server registry (Phase 6.7)
"""
from backend.models.entities.channels import (
    ExternalChannel,
    ExternalMessage,
    ChannelType,
    ChannelStatus
)

from backend.models.entities.skill import SkillSchema, SkillDB, SkillSubmission
from backend.models.entities.chat_message import ChatMessage, Conversation

from backend.models.entities.scheduled_task import (
    ScheduledTask, 
    ScheduledTaskExecution,
    ScheduledTaskStatus,
    ScheduledTaskExecutionStatus
)

from .reasoning_trace import ReasoningTraceModel, ReasoningStepModel

from backend.models.entities.task import (
    Task,
    SubTask,
    TaskAuditLog,
    TaskStatus,
    TaskPriority,
    TaskType,
    TaskDependency,
)

from backend.models.entities.task_events import (
    TaskEvent,
    TaskEventType
)

from backend.models.entities.user_config import (
    UserModelConfig,
    ProviderType,
    ConnectionStatus,
    ModelUsageLog
)

from .ab_testing import (
    Experiment, ExperimentRun, ExperimentResult,
    ModelPerformanceCache, ExperimentStatus, RunStatus, TaskComplexity
)

from backend.models.entities.base import Base, BaseEntity

from backend.models.entities.user import User
from backend.models.entities.delegation import Delegation

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

from backend.models.entities.critics import (
    CriticAgent,
    CritiqueReview,
    CriticType,
    CriticVerdict
)

from backend.models.entities.system_settings import SystemSetting

from backend.models.entities.checkpoint import (
    ExecutionCheckpoint,
    CheckpointPhase
)

from backend.models.entities.remote_execution import (
    RemoteExecutionRecord,
    SandboxRecord,
    ExecutionSummary,
    ExecutionStatus,
    SandboxStatus
)

# Phase 6.7 — MCP Server Integration
from backend.models.entities.mcp_tool import MCPTool

# Phase 11 — Ecosystem Expansion
from backend.models.entities.federation import FederatedInstance, FederatedTask, FederatedVote
from backend.models.entities.plugin import Plugin, PluginInstallation, PluginReview
from backend.models.entities.mobile import DeviceToken, NotificationPreference

# Phase 12 — SDK & External Interface
from backend.models.entities.webhook import WebhookSubscription, WebhookDeliveryLog

# Phase 13.5 — Workflow Automation Pipeline
from backend.models.entities.workflow import (Workflow, WorkflowExecution, WorkflowStep, WorkflowVersion, WorkflowExecutionStatus, WorkflowStepType)

# Phase 13.6 — Intelligent Event Processing
from backend.models.entities.event_trigger import EventTrigger, EventLog, TriggerType, EventLogStatus

# All models for Alembic/database creation
__all__ = [
    # Base
    'Base',
    'BaseEntity',
    
    # User Configuration (Frontend-managed models)
    'User',
    'Delegation',
    'UserModelConfig',
    'ProviderType', 
    'ConnectionStatus',
    'ModelUsageLog',
    "ChatMessage",
    "Conversation",
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
    "SkillSchema",
    "SkillDB", 
    "SkillSubmission",

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
    'TaskDependency',
    'TaskEvent',
    'TaskEventType',
    
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
    'MonitoringStatus',
    
    # Critics (Veto Authority)
    'CriticAgent',
    'CritiqueReview',
    'CriticType',
    'CriticVerdict',

    # System Settings
    'SystemSetting',
    
    # Checkpointing (Time-Travel)
    'ExecutionCheckpoint',
    'CheckpointPhase',

    # Remote Execution (Brains vs Hands)
    'RemoteExecutionRecord',
    'SandboxRecord',
    'ExecutionSummary',
    'ExecutionStatus',
    'SandboxStatus',

    # MCP Tools (Constitutional Tool Registry — Phase 6.7)
    'MCPTool',

    # Ecosystem Expansion (Phase 11)
    'FederatedInstance',
    'FederatedTask',
    'FederatedVote',
    'Plugin',
    'PluginInstallation',
    'PluginReview',
    'DeviceToken',
    'NotificationPreference',

    # Outbound Webhooks (Phase 12)
    'WebhookSubscription',
    'WebhookDeliveryLog',

    # Workflow Automation Pipeline (Phase 13.5)
    'Workflow',
    'WorkflowExecution',
    'WorkflowStep',
    'WorkflowVersion',
    'WorkflowExecutionStatus',
    'WorkflowStepType',

    # Intelligent Event Processing (Phase 13.6)
    'EventTrigger',
    'EventLog',
    'TriggerType',
    'EventLogStatus',
]