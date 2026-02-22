"""Sandbox container management for remote code execution."""
import os
import uuid
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Import docker conditionally to allow module loading without docker installed
try:
    import docker
    import docker.errors
    DOCKER_AVAILABLE = True
except ImportError:
    docker = None  # type: ignore
    DOCKER_AVAILABLE = False
    logger.warning("docker-py not installed – SandboxManager will operate in stub mode")


@dataclass
class SandboxConfig:
    """Configuration for sandbox container."""
    cpu_limit: float = 1.0  # CPU cores
    memory_limit_mb: int = 512  # MB
    timeout_seconds: int = 300  # 5 minutes
    network_mode: str = "none"  # none, bridge
    allowed_hosts: Optional[List[str]] = None  # For network whitelist
    max_disk_mb: int = 1024  # 1GB
    image: str = "python:3.11-slim"  # Base image


class SandboxManager:
    """
    Manages Docker sandbox containers for remote code execution.

    Each execution runs in an isolated container with resource limits.
    Containers are ephemeral – created per execution and destroyed after.
    """

    def __init__(self):
        self.docker_client = None
        self._init_docker()

    def _init_docker(self):
        """Initialize Docker client from environment."""
        if not DOCKER_AVAILABLE:
            logger.warning("SandboxManager: docker-py not available")
            return

        try:
            # Try environment variable first
            docker_socket = os.getenv('HOST_DOCKER_SOCKET', '/var/run/docker.sock')
            self.docker_client = docker.DockerClient(base_url=f'unix://{docker_socket}')

            # Test connection
            self.docker_client.ping()
            logger.info(f"SandboxManager connected to Docker at {docker_socket}")

        except Exception as e:
            logger.error(f"Failed to connect to Docker: {e}")
            self.docker_client = None

    async def create_sandbox(
        self,
        agent_id: str,
        config: Optional[SandboxConfig] = None
    ) -> Dict[str, Any]:
        """
        Create a new sandbox container for code execution.

        Args:
            agent_id: Agent requesting the sandbox
            config: Sandbox configuration (uses defaults if None)

        Returns:
            Dict with sandbox_id, container_id, status
        """
        if not self.docker_client:
            raise RuntimeError("Docker client not available")

        config = config or SandboxConfig()
        sandbox_id = f"sandbox_{uuid.uuid4().hex[:12]}"

        try:
            # Create container with resource limits
            container = self.docker_client.containers.run(
                image=config.image,
                name=sandbox_id,
                detach=True,
                tty=True,
                stdin_open=True,
                network_mode=config.network_mode,
                mem_limit=f"{config.memory_limit_mb}m",
                cpu_quota=int(config.cpu_limit * 100000),
                cpu_period=100000,
                labels={
                    "agentium.sandbox": "true",
                    "agentium.agent_id": agent_id,
                    "agentium.created_at": datetime.utcnow().isoformat(),
                },
                environment={
                    "PYTHONDONTWRITEBYTECODE": "1",
                    "PYTHONUNBUFFERED": "1",
                },
            )

            logger.info(f"Created sandbox {sandbox_id} for agent {agent_id}")

            return {
                "sandbox_id": sandbox_id,
                "container_id": container.id,
                "status": "ready",
                "config": {
                    "cpu_limit": config.cpu_limit,
                    "memory_limit_mb": config.memory_limit_mb,
                    "timeout_seconds": config.timeout_seconds,
                }
            }

        except Exception as e:
            logger.error(f"Failed to create sandbox: {e}")
            raise RuntimeError(f"Sandbox creation failed: {e}")

    async def destroy_sandbox(
        self,
        sandbox_id: str,
        reason: str = "completed"
    ) -> bool:
        """
        Destroy a sandbox container and clean up resources.

        Args:
            sandbox_id: ID of sandbox to destroy
            reason: Reason for destruction (for audit log)

        Returns:
            True if successful
        """
        if not self.docker_client:
            return False

        try:
            container = self.docker_client.containers.get(sandbox_id)

            # Force remove after 5 second grace period
            container.stop(timeout=5)
            container.remove(force=True)

            logger.info(f"Destroyed sandbox {sandbox_id}: {reason}")
            return True

        except Exception as e:
            if DOCKER_AVAILABLE and isinstance(e, docker.errors.NotFound):
                logger.warning(f"Sandbox {sandbox_id} not found for destruction")
                return True  # Already gone
            logger.error(f"Failed to destroy sandbox {sandbox_id}: {e}")
            return False

    async def list_sandboxes(
        self,
        agent_id: Optional[str] = None,
        status: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        List sandbox containers.

        Args:
            agent_id: Filter by agent (None for all)
            status: Filter by status (None for all)

        Returns:
            List of sandbox info dicts
        """
        if not self.docker_client:
            return []

        try:
            filters = {"label": ["agentium.sandbox=true"]}
            if agent_id:
                filters["label"].append(f"agentium.agent_id={agent_id}")

            containers = self.docker_client.containers.list(
                all=True,
                filters=filters
            )

            sandboxes = []
            for container in containers:
                info = {
                    "sandbox_id": container.name,
                    "container_id": container.id,
                    "status": container.status,
                    "agent_id": container.labels.get("agentium.agent_id"),
                    "created_at": container.labels.get("agentium.created_at"),
                }

                if status is None or info["status"] == status:
                    sandboxes.append(info)

            return sandboxes

        except Exception as e:
            logger.error(f"Failed to list sandboxes: {e}")
            return []
