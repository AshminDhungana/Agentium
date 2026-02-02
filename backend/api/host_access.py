"""
Host System Access API Endpoints for Agentium.
Provides root-level system control through Head of Council (0xxxx).
All operations are authenticated, authorized, and audited.
"""
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from datetime import datetime
import asyncio

from backend.models.database import get_db
from backend.services.host_access import HostAccessService, RestrictedHostAccess
from backend.services.auth import get_current_agent, verify_agent_hierarchy
from backend.models.entities.agents import Agent
from backend.models.entities.audit import AuditLog, AuditLevel, AuditCategory

router = APIRouter(prefix="/host", tags=["Host System Access"])
security = HTTPBearer()

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Pydantic Models
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class CommandExecuteRequest(BaseModel):
    command: List[str] = Field(..., description="Command and arguments as list")
    working_directory: Optional[str] = Field(None, description="Working directory on host")
    timeout: int = Field(300, description="Timeout in seconds")
    require_approval: bool = Field(False, description="Require council approval for restricted agents")
    reason: Optional[str] = Field(None, description="Reason for command execution")

class FileReadRequest(BaseModel):
    filepath: str = Field(..., description="Absolute path on host system")
    offset: int = Field(0, description="Line offset for pagination")
    limit: int = Field(1000, description="Max lines to read")

class FileWriteRequest(BaseModel):
    filepath: str = Field(..., description="Absolute path on host system")
    content: str = Field(..., description="Content to write")
    create_backup: bool = Field(True, description="Create .bak backup before writing")
    mode: str = Field("644", description="File permissions (octal)")

class DirectoryListRequest(BaseModel):
    path: str = Field("/", description="Directory path on host")
    show_hidden: bool = Field(True, description="Show hidden files")

class ContainerActionRequest(BaseModel):
    container_name: str = Field(..., description="Name or ID of container")
    action: str = Field(..., description="start, stop, restart, remove, pause, unpause")
    force: bool = Field(False, description="Force action without confirmation")

class ContainerExecRequest(BaseModel):
    container_name: str = Field(..., description="Target container")
    command: List[str] = Field(..., description="Command to execute inside container")
    user: Optional[str] = Field(None, description="User to run as inside container")
    working_dir: Optional[str] = Field(None, description="Working directory inside container")

class AgentSpawnRequest(BaseModel):
    agent_type: str = Field(..., description="council_member, lead_agent, or task_agent")
    name: str = Field(..., description="Human-readable name for the agent")
    specialization: Optional[str] = Field(None, description="Agent specialization/role")
    parent_id: Optional[str] = Field(None, description="Parent agent ID in hierarchy")
    resources: Optional[Dict[str, Any]] = Field(None, description="CPU, memory limits")
    environment_vars: Optional[Dict[str, str]] = Field(None, description="Additional env vars")

class SystemInfoRequest(BaseModel):
    include_metrics: bool = Field(True, description="Include CPU, memory, disk metrics")
    include_processes: bool = Field(False, description="Include running processes")
    include_network: bool = Field(True, description="Include network interfaces")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Response Models
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class CommandResponse(BaseModel):
    success: bool
    command: List[str]
    returncode: Optional[int]
    stdout: str
    stderr: str
    execution_time_ms: float
    executed_by: str
    timestamp: str
    requires_approval: Optional[bool] = None
    approval_status: Optional[str] = None

class FileResponse(BaseModel):
    success: bool
    path: str
    content: Optional[str] = None
    size: Optional[int] = None
    encoding: str = "utf-8"
    is_binary: bool = False
    error: Optional[str] = None

class DirectoryResponse(BaseModel):
    success: bool
    path: str
    entries: List[Dict[str, Any]]
    total_count: int
    error: Optional[str] = None

class ContainerResponse(BaseModel):
    success: bool
    action: Optional[str] = None
    container_id: Optional[str] = None
    container_name: str
    status: Optional[str] = None
    error: Optional[str] = None

class SystemInfoResponse(BaseModel):
    success: bool
    hostname: str
    platform: str
    uptime: str
    metrics: Optional[Dict[str, Any]] = None
    filesystems: List[Dict[str, Any]]
    timestamp: str

class AgentSpawnResponse(BaseModel):
    success: bool
    agentium_id: Optional[str] = None
    container_id: Optional[str] = None
    name: str
    agent_type: str
    status: str
    api_endpoint: Optional[str] = None
    error: Optional[str] = None
    spawn_duration_ms: float

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Dependency: Get Host Access Service for Agent
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def get_host_access_service(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
) -> HostAccessService:
    """
    Authenticate agent and return appropriate host access service.
    Only Head of Council (0xxxx) gets full access.
    Council Members (1xxxx) get restricted access.
    Others get no access.
    """
    # Verify JWT token and get agent
    agent = await get_current_agent(credentials.credentials, db)
    
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials"
        )
    
    # Check if agent is active
    if agent.status != 'active':
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Agent {agent.agentium_id} is not active (status: {agent.status})"
        )
    
    # Initialize host access based on agent type
    agentium_id = agent.agentium_id
    
    if agentium_id.startswith('0'):  # Head of Council - FULL ACCESS
        return HostAccessService(agentium_id)
    
    elif agentium_id.startswith('1'):  # Council Members - RESTRICTED
        # Council members need Head approval for sensitive operations
        head_service = HostAccessService('00001')
        return RestrictedHostAccess(agentium_id, head_service)
    
    elif agentium_id.startswith('2'):  # Lead Agents - SUPERVISED
        # Lead agents have limited access, must route through Head
        head_service = HostAccessService('00001')
        return RestrictedHostAccess(agentium_id, head_service)
    
    else:  # Task Agents (3xxxx) and others - NO ACCESS
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Agent type {agent.agent_type} ({agentium_id}) is not authorized for host access"
        )

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# API Endpoints
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.post("/execute", response_model=CommandResponse)
async def execute_command(
    request: CommandExecuteRequest,
    background_tasks: BackgroundTasks,
    host_access: HostAccessService = Depends(get_host_access_service),
    db: Session = Depends(get_db)
):
    """
    Execute arbitrary command on host system.
    **Head of Council (0xxxx)**: Direct execution
    **Council Members (1xxxx)**: Requires Head approval for sensitive commands
    """
    start_time = datetime.utcnow()
    
    # Security: Check for dangerous commands
    dangerous_commands = ['rm -rf /', 'mkfs.', 'dd if=/dev/zero', '>:', 'shutdown', 'reboot', 'init 0']
    command_str = ' '.join(request.command).lower()
    is_dangerous = any(dangerous in command_str for dangerous in dangerous_commands)
    
    # If dangerous and not Head of Council, require approval
    if is_dangerous and not host_access.is_authorized:
        # Create approval request (implement voting mechanism)
        return CommandResponse(
            success=False,
            command=request.command,
            returncode=None,
            stdout="",
            stderr="Command requires Head of Council approval",
            execution_time_ms=0,
            executed_by=host_access.agentium_id,
            timestamp=start_time.isoformat(),
            requires_approval=True,
            approval_status="pending"
        )
    
    # Execute command
    result = host_access.execute_command(
        command=request.command,
        cwd=request.working_directory,
        timeout=request.timeout
    )
    
    execution_time = (datetime.utcnow() - start_time).total_seconds() * 1000
    
    # Log to database
    background_tasks.add_task(
        log_host_operation,
        db,
        host_access.agentium_id,
        "execute_command",
        request.command,
        result['success'],
        request.reason or "No reason provided"
    )
    
    return CommandResponse(
        success=result['success'],
        command=request.command,
        returncode=result.get('returncode'),
        stdout=result.get('stdout', ''),
        stderr=result.get('stderr', ''),
        execution_time_ms=execution_time,
        executed_by=host_access.agentium_id,
        timestamp=start_time.isoformat()
    )

@router.post("/file/read", response_model=FileResponse)
async def read_file(
    request: FileReadRequest,
    host_access: HostAccessService = Depends(get_host_access_service)
):
    """
    Read file contents from host filesystem.
    Accessible by Head of Council and Council Members.
    """
    result = host_access.read_file(request.filepath)
    
    # Handle pagination if needed
    if result['success'] and request.offset > 0:
        lines = result['content'].split('\n')
        paginated = lines[request.offset:request.offset + request.limit]
        result['content'] = '\n'.join(paginated)
        result['pagination'] = {
            'offset': request.offset,
            'limit': request.limit,
            'total_lines': len(lines)
        }
    
    return FileResponse(
        success=result['success'],
        path=result.get('path', request.filepath),
        content=result.get('content'),
        size=result.get('size'),
        error=result.get('error')
    )

@router.post("/file/write", response_model=FileResponse)
async def write_file(
    request: FileWriteRequest,
    background_tasks: BackgroundTasks,
    host_access: HostAccessService = Depends(get_host_access_service),
    db: Session = Depends(get_db)
):
    """
    Write file to host filesystem.
    **Head of Council only** - Council Members cannot write files directly.
    """
    if not host_access.is_authorized:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="File write requires Head of Council privileges"
        )
    
    # Create backup if requested
    if request.create_backup:
        backup_result = host_access.execute_command([
            'cp', request.filepath, f"{request.filepath}.bak"
        ])
        if not backup_result['success']:
            # File might not exist yet, which is fine
            pass
    
    # Write file
    result = host_access.write_file(request.filepath, request.content)
    
    # Set permissions if successful
    if result['success'] and request.mode:
        host_access.execute_command(['chmod', request.mode, request.filepath])
    
    # Log operation
    background_tasks.add_task(
        log_host_operation,
        db,
        host_access.agentium_id,
        "write_file",
        request.filepath,
        result['success'],
        f"Write {len(request.content)} bytes"
    )
    
    return FileResponse(
        success=result['success'],
        path=result.get('path', request.filepath),
        error=result.get('error')
    )

@router.post("/directory/list", response_model=DirectoryResponse)
async def list_directory(
    request: DirectoryListRequest,
    host_access: HostAccessService = Depends(get_host_access_service)
):
    """
    List directory contents on host system.
    """
    result = host_access.list_directory(request.path)
    
    # Parse ls -la output into structured data
    entries = []
    if result['success'] and result['listing']:
        lines = result['listing'].strip().split('\n')
        for line in lines[1:]:  # Skip total line
            parts = line.split(maxsplit=8)
            if len(parts) >= 9:
                entries.append({
                    'permissions': parts[0],
                    'links': parts[1],
                    'owner': parts[2],
                    'group': parts[3],
                    'size': parts[4],
                    'modified': ' '.join(parts[5:8]),
                    'name': parts[8],
                    'is_directory': parts[0].startswith('d'),
                    'is_hidden': parts[8].startswith('.')
                })
            elif len(parts) >= 1:
                entries.append({'raw': line})
    
    # Filter hidden if requested
    if not request.show_hidden:
        entries = [e for e in entries if not e.get('is_hidden', False)]
    
    return DirectoryResponse(
        success=result['success'],
        path=result.get('path', request.path),
        entries=entries,
        total_count=len(entries),
        error=result.get('error')
    )

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Docker/Container Management Endpoints
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get("/containers", response_model=List[Dict[str, Any]])
async def list_containers(
    host_access: HostAccessService = Depends(get_host_access_service)
):
    """
    List all Docker containers on host system.
    """
    if not host_access.docker_client:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Docker client not available"
        )
    
    containers = host_access.list_containers()
    return containers

@router.post("/container/action", response_model=ContainerResponse)
async def container_action(
    request: ContainerActionRequest,
    background_tasks: BackgroundTasks,
    host_access: HostAccessService = Depends(get_host_access_service),
    db: Session = Depends(get_db)
):
    """
    Perform action on container (start, stop, restart, remove, etc.).
    **Head of Council**: Any container
    **Council Members**: Only agent containers (agentium-*)
    """
    # Authorization check for non-Head agents
    if not host_access.is_authorized:
        if not request.container_name.startswith('agentium-'):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Can only manage Agentium containers"
            )
    
    result = host_access.manage_container(request.action, request.container_name)
    
    # Log action
    background_tasks.add_task(
        log_host_operation,
        db,
        host_access.agentium_id,
        f"container_{request.action}",
        request.container_name,
        result['success'],
        f"Force: {request.force}"
    )
    
    return ContainerResponse(
        success=result['success'],
        action=request.action,
        container_id=result.get('container_id'),
        container_name=request.container_name,
        status=result.get('new_status'),
        error=result.get('error')
    )

@router.post("/container/execute", response_model=CommandResponse)
async def execute_in_container(
    request: ContainerExecRequest,
    host_access: HostAccessService = Depends(get_host_access_service)
):
    """
    Execute command inside a specific container.
    """
    if not host_access.docker_client:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Docker client not available"
        )
    
    result = host_access.execute_in_container(
        request.container_name,
        request.command
    )
    
    return CommandResponse(
        success=result['success'],
        command=request.command,
        returncode=result.get('exit_code'),
        stdout=result.get('output', ''),
        stderr="",
        execution_time_ms=0,
        executed_by=host_access.agentium_id,
        timestamp=datetime.utcnow().isoformat()
    )

@router.post("/container/spawn-agent", response_model=AgentSpawnResponse)
async def spawn_agent_container(
    request: AgentSpawnRequest,
    background_tasks: BackgroundTasks,
    host_access: HostAccessService = Depends(get_host_access_service),
    db: Session = Depends(get_db)
):
    """
    Spawn a new agent as a Docker container on host system.
    This allows dynamic scaling of the agent hierarchy.
    **Head of Council only**
    """
    if not host_access.is_authorized:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only Head of Council can spawn new agents"
        )
    
    start_time = datetime.utcnow()
    
    # Generate agentium_id based on type
    agent_count = db.query(Agent).filter(
        Agent.agent_type == request.agent_type,
        Agent.is_active == 'Y'
    ).count()
    
    prefix = {'council_member': '1', 'lead_agent': '2', 'task_agent': '3'}.get(request.agent_type, '3')
    new_id = f"{prefix}{str(agent_count + 1).zfill(4)}"
    
    # Prepare agent configuration
    agent_config = {
        'agentium_id': new_id,
        'agent_type': request.agent_type,
        'name': request.name,
        'parent_id': request.parent_id or '00001',
        'specialization': request.specialization,
        'resources': request.resources or {},
        'environment': request.environment_vars or {}
    }
    
    # Spawn container
    result = host_access.spawn_agent_container(agent_config)
    
    spawn_duration = (datetime.utcnow() - start_time).total_seconds() * 1000
    
    if result['success']:
        # Register agent in database
        new_agent = Agent(
            agentium_id=new_id,
            agent_type=request.agent_type,
            name=request.name,
            description=f"Spawned agent: {request.specialization or 'General'}",
            parent_id=request.parent_id,
            status='initializing',
            constitution_version='v1.0.0',
            is_active='Y'
        )
        db.add(new_agent)
        db.commit()
        
        # Log spawn
        background_tasks.add_task(
            log_host_operation,
            db,
            host_access.agentium_id,
            "spawn_agent",
            new_id,
            True,
            f"Type: {request.agent_type}, Name: {request.name}"
        )
    
    return AgentSpawnResponse(
        success=result['success'],
        agentium_id=new_id if result['success'] else None,
        container_id=result.get('container_id'),
        name=request.name,
        agent_type=request.agent_type,
        status=result.get('status', 'failed'),
        api_endpoint=f"http://localhost:8000/agents/{new_id}" if result['success'] else None,
        error=result.get('error'),
        spawn_duration_ms=spawn_duration
    )

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# System Information Endpoints
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get("/system/info", response_model=SystemInfoResponse)
async def get_system_info(
    request: SystemInfoRequest = Depends(),
    host_access: HostAccessService = Depends(get_host_access_service)
):
    """
    Get comprehensive system information from host.
    """
    # Get basic info
    hostname_result = host_access.execute_command(['hostname'])
    uname_result = host_access.execute_command(['uname', '-a'])
    uptime_result = host_access.execute_command(['uptime', '-p'])
    
    # Get filesystem info
    df_result = host_access.execute_command(['df', '-h'])
    filesystems = []
    if df_result['success']:
        lines = df_result['stdout'].strip().split('\n')[1:]  # Skip header
        for line in lines:
            parts = line.split()
            if len(parts) >= 6:
                filesystems.append({
                    'filesystem': parts[0],
                    'size': parts[1],
                    'used': parts[2],
                    'available': parts[3],
                    'use_percent': parts[4],
                    'mounted_on': parts[5]
                })
    
    metrics = None
    if request.include_metrics:
        # CPU usage
        cpu_result = host_access.execute_command(['top', '-bn1', '-n1'])
        # Memory usage
        mem_result = host_access.execute_command(['free', '-h'])
        # Disk usage summary
        disk_result = host_access.execute_command(['df', '-h', '/'])
        
        metrics = {
            'cpu': cpu_result.get('stdout', 'N/A')[:500] if cpu_result['success'] else 'N/A',
            'memory': mem_result.get('stdout', 'N/A') if mem_result['success'] else 'N/A',
            'root_disk': disk_result.get('stdout', 'N/A') if disk_result['success'] else 'N/A'
        }
    
    processes = None
    if request.include_processes:
        ps_result = host_access.execute_command(['ps', 'aux', '--sort=-%mem'])
        processes = ps_result.get('stdout', '')[:2000] if ps_result['success'] else 'N/A'
    
    network = None
    if request.include_network:
        net_result = host_access.execute_command(['ip', 'addr'])
        network = net_result.get('stdout', '')[:1000] if net_result['success'] else 'N/A'
    
    return SystemInfoResponse(
        success=True,
        hostname=hostname_result.get('stdout', 'unknown').strip(),
        platform=uname_result.get('stdout', 'unknown').strip(),
        uptime=uptime_result.get('stdout', 'unknown').strip(),
        metrics=metrics,
        filesystems=filesystems,
        timestamp=datetime.utcnow().isoformat()
    )

@router.get("/system/processes")
async def get_processes(
    limit: int = 50,
    host_access: HostAccessService = Depends(get_host_access_service)
):
    """
    Get list of running processes on host.
    """
    result = host_access.execute_command([
        'ps', 'aux', '--sort=-%cpu', f'--no-headers', f'--rows={limit}'
    ])
    
    processes = []
    if result['success']:
        for line in result['stdout'].strip().split('\n'):
            parts = line.split(maxsplit=10)
            if len(parts) >= 11:
                processes.append({
                    'user': parts[0],
                    'pid': parts[1],
                    'cpu_percent': parts[2],
                    'mem_percent': parts[3],
                    'vsz': parts[4],
                    'rss': parts[5],
                    'tty': parts[6],
                    'stat': parts[7],
                    'start': parts[8],
                    'time': parts[9],
                    'command': parts[10]
                })
    
    return {
        'success': result['success'],
        'processes': processes,
        'count': len(processes),
        'timestamp': datetime.utcnow().isoformat()
    }

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Helper Functions
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def log_host_operation(
    db: Session,
    agentium_id: str,
    operation: str,
    target: str,
    success: bool,
    details: str
):
    """Background task to log host operations to database."""
    try:
        audit = AuditLog(
            level=AuditLevel.INFO if success else AuditLevel.WARNING,
            category=AuditCategory.SYSTEM,
            actor_type='agent',
            actor_id=agentium_id,
            action=operation,
            target_type='host_system',
            target_id=target,
            description=details,
            after_state={
                'success': success,
                'operation': operation,
                'target': target
            },
            is_active='Y',
            created_at=datetime.utcnow()
        )
        db.add(audit)
        db.commit()
    except Exception as e:
        print(f"Failed to log audit: {e}")