"""
Host System Access Service for Head of Council (00001).
Provides root-level access to the host system while maintaining audit trails.
"""
import subprocess
import os
import docker
from typing import Dict, Any, List, Optional
from datetime import datetime
from backend.models.entities.audit import AuditLog, AuditLevel, AuditCategory

class HostAccessService:
    """
    Grants Head of Council full root access to host system.
    All operations are logged for security auditing.
    """
    
    def __init__(self, agentium_id: str):
        self.agentium_id = agentium_id
        self.is_authorized = agentium_id.startswith('0')  # Only Head of Council (0xxxx)
        self.host_root = os.getenv('HOST_FS_MOUNT', '/host')
        self.docker_socket = os.getenv('HOST_DOCKER_SOCKET', '/var/run/docker.sock')
        
        # Initialize Docker client for host container management
        try:
            self.docker_client = docker.DockerClient(base_url=f'unix://{self.docker_socket}')
        except Exception as e:
            self.docker_client = None
            print(f"Warning: Docker client not available: {e}")
    
    def _log_operation(self, action: str, target: str, details: Dict[str, Any], 
                      level: AuditLevel = AuditLevel.INFO):
        """Log all host access operations."""
        # Create audit log entry (implement based on your audit system)
        log_entry = {
            'timestamp': datetime.utcnow().isoformat(),
            'agentium_id': self.agentium_id,
            'action': f"host_{action}",
            'target': target,
            'details': details,
            'level': level.value
        }
        # Persist to database (implement based on your system)
        print(f"[AUDIT] {log_entry}")
        return log_entry
    
    def execute_command(self, command: List[str], cwd: Optional[str] = None,
                       timeout: int = 300) -> Dict[str, Any]:
        """
        Execute command on host system with root privileges.
        Only Head of Council can execute arbitrary commands.
        """
        if not self.is_authorized:
            raise PermissionError(f"Agent {self.agentium_id} is not authorized for host access")
        
        # Translate container path to host path if needed
        if cwd and cwd.startswith('/host'):
            host_cwd = cwd
        else:
            host_cwd = self.host_root
        
        self._log_operation(
            action='execute_command',
            target=host_cwd,
            details={'command': ' '.join(command), 'cwd': cwd}
        )
        
        try:
            result = subprocess.run(
                ['sudo', '-n'] + command,  # -n = non-interactive (no password prompt)
                cwd=host_cwd,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False
            )
            
            return {
                'success': result.returncode == 0,
                'returncode': result.returncode,
                'stdout': result.stdout,
                'stderr': result.stderr,
                'command': command,
                'executed_at': datetime.utcnow().isoformat()
            }
        except subprocess.TimeoutExpired:
            return {
                'success': False,
                'error': 'Command timed out',
                'command': command
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'command': command
            }
    
    def read_file(self, filepath: str) -> Dict[str, Any]:
        """Read file from host filesystem."""
        if not self.is_authorized:
            raise PermissionError("Unauthorized")
        
        # Ensure path is within host mount
        if not filepath.startswith(self.host_root):
            filepath = os.path.join(self.host_root, filepath.lstrip('/'))
        
        self._log_operation('read_file', filepath, {})
        
        try:
            with open(filepath, 'r') as f:
                content = f.read()
            return {
                'success': True,
                'content': content,
                'path': filepath,
                'size': len(content)
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'path': filepath
            }
    
    def write_file(self, filepath: str, content: str) -> Dict[str, Any]:
        """Write file to host filesystem (root access)."""
        if not self.is_authorized:
            raise PermissionError("Unauthorized")
        
        if not filepath.startswith(self.host_root):
            filepath = os.path.join(self.host_root, filepath.lstrip('/'))
        
        self._log_operation('write_file', filepath, {'size': len(content)})
        
        try:
            # Use sudo to write with root permissions
            proc = subprocess.Popen(
                ['sudo', '-n', 'tee', filepath],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            stdout, stderr = proc.communicate(input=content)
            
            return {
                'success': proc.returncode == 0,
                'path': filepath,
                'bytes_written': len(content),
                'error': stderr if stderr else None
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'path': filepath
            }
    
    def list_directory(self, path: str = '/') -> Dict[str, Any]:
        """List directory contents on host."""
        if not self.is_authorized:
            raise PermissionError("Unauthorized")
        
        if not path.startswith(self.host_root):
            path = os.path.join(self.host_root, path.lstrip('/'))
        
        self._log_operation('list_directory', path, {})
        
        try:
            result = subprocess.run(
                ['sudo', '-n', 'ls', '-la', path],
                capture_output=True,
                text=True,
                check=False
            )
            return {
                'success': result.returncode == 0,
                'listing': result.stdout,
                'path': path
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'path': path
            }
    
    # Docker/Container Management (Full Control)
    def list_containers(self) -> List[Dict[str, Any]]:
        """List all containers on host Docker daemon."""
        if not self.is_authorized or not self.docker_client:
            raise PermissionError("Docker access not available")
        
        self._log_operation('docker_list_containers', 'docker', {})
        
        try:
            containers = self.docker_client.containers.list(all=True)
            return [{
                'id': c.id,
                'name': c.name,
                'status': c.status,
                'image': c.image.tags[0] if c.image.tags else 'unknown',
                'created': c.attrs['Created']
            } for c in containers]
        except Exception as e:
            return [{'error': str(e)}]
    
    def execute_in_container(self, container_name: str, command: List[str]) -> Dict[str, Any]:
        """Execute command inside any container on host."""
        if not self.is_authorized or not self.docker_client:
            raise PermissionError("Docker access not available")
        
        self._log_operation('docker_exec', container_name, {'command': command})
        
        try:
            container = self.docker_client.containers.get(container_name)
            result = container.exec_run(command, tty=False)
            return {
                'success': result.exit_code == 0,
                'exit_code': result.exit_code,
                'output': result.output.decode('utf-8') if result.output else ''
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'container': container_name
            }
    
    def manage_container(self, action: str, container_name: str) -> Dict[str, Any]:
        """
        Start, stop, restart, or remove containers on host.
        """
        if not self.is_authorized or not self.docker_client:
            raise PermissionError("Docker access not available")
        
        self._log_operation(f'docker_{action}', container_name, {})
        
        try:
            container = self.docker_client.containers.get(container_name)
            
            if action == 'start':
                container.start()
            elif action == 'stop':
                container.stop()
            elif action == 'restart':
                container.restart()
            elif action == 'remove':
                container.remove(force=True)
            else:
                return {'success': False, 'error': f'Unknown action: {action}'}
            
            return {
                'success': True,
                'action': action,
                'container': container_name,
                'new_status': container.status
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'container': container_name
            }
    
    def spawn_agent_container(self, agent_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Spawn a new agent container on host system.
        This allows dynamic scaling of agents as real containers.
        """
        if not self.is_authorized or not self.docker_client:
            raise PermissionError("Docker access not available")
        
        agent_type = agent_config.get('agent_type', 'task_agent')
        agentium_id = agent_config.get('agentium_id', '30001')
        
        self._log_operation('spawn_agent_container', agentium_id, agent_config)
        
        try:
            # Create container with appropriate restrictions based on agent type
            container_config = {
                'image': 'agentium-agent:latest',  # Your agent image
                'name': f'agentium-agent-{agentium_id}',
                'environment': {
                    'AGENT_TYPE': agent_type,
                    'AGENTIUM_ID': agentium_id,
                    'PARENT_ID': agent_config.get('parent_id'),
                    'HEAD_COUNCIL_ID': '00001',
                    'API_ENDPOINT': 'http://host.docker.internal:8000'
                },
                'network': 'agentium-network',
                'detach': True,
                'auto_remove': False,
                # Task agents get restricted privileges
                'privileged': agent_type == 'head_of_council',  # Only Head gets full privs
                'volumes': {
                    '/var/run/docker.sock': {'bind': '/var/run/docker.sock', 'mode': 'ro'}
                } if agent_type in ['lead_agent', 'council_member'] else {}
            }
            
            container = self.docker_client.containers.run(**container_config)
            
            return {
                'success': True,
                'container_id': container.id,
                'agentium_id': agentium_id,
                'agent_type': agent_type,
                'status': 'running'
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'agentium_id': agentium_id
            }


class RestrictedHostAccess:
    """
    Limited host access for Council Members (1xxxx), Lead Agents (2xxxx).
    All operations must be approved by Head of Council.
    """
    
    def __init__(self, agentium_id: str, head_council_proxy: HostAccessService):
        self.agentium_id = agentium_id
        self.head_proxy = head_council_proxy  # Routes through Head of Council
        self.approval_required = True
    
    def request_operation(self, operation: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Request host operation - requires Head of Council approval.
        """
        # Log the request
        request_id = f"{self.agentium_id}-{datetime.utcnow().timestamp()}"
        
        # In real implementation, this would create a voting session
        # For now, auto-approve for demonstration (DANGEROUS - change for production)
        print(f"[REQUEST] {self.agentium_id} requests {operation}: {params}")
        
        # Route through Head of Council service
        if hasattr(self.head_proxy, operation):
            method = getattr(self.head_proxy, operation)
            return method(**params)
        
        return {
            'success': False,
            'error': 'Operation not available',
            'request_id': request_id
        }