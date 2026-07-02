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
        """Initialize the sandbox manager and Docker client.

        Args:
            None

        Returns:
            None

        Raises:
            None
        """
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

        # ── WARM POOLING CONFIGURATION ──
        self.MIN_WARM_CONTAINERS = int(os.getenv("AGENTIUM_MIN_WARM_SANDBOXES", "3"))
        self._warm_pool: List[Dict[str, Any]] = []
        self._pool_lock = None  # Initialized in async context
        
    async def _ensure_pool_lock(self):
        """Ensure pool lock."""

        import asyncio
        if self._pool_lock is None:
            self._pool_lock = asyncio.Lock()

    async def _replenish_warm_pool(self, config: Optional[SandboxConfig] = None):
        """Background task to keep warm pool stocked."""
        await self._ensure_pool_lock()
        
        async with self._pool_lock:
            current_count = len(self._warm_pool)
            needed = self.MIN_WARM_CONTAINERS - current_count
            
        if needed > 0 and self.docker_client:
            logger.info(f"[Warm Pool] Replenishing {needed} containers in background...")
            for _ in range(needed):
                try:
                    # Create without tying to a specific agent yet
                    container_info = await self._create_raw_container("warm_pool", config)
                    async with self._pool_lock:
                        self._warm_pool.append(container_info)
                except Exception as e:
                    logger.error(f"[Warm Pool] Failed to create warm container: {e}")

    async def _create_raw_container(
        self,
        agent_id: str,
        config: Optional[SandboxConfig] = None
    ) -> Dict[str, Any]:
        """Internal helper to actually spin up docker."""
        if not self.docker_client:
            raise RuntimeError("Docker client not available")

        config = config or SandboxConfig()
        sandbox_id = f"sandbox_{uuid.uuid4().hex[:12]}"

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
                "agentium.is_warm": "true" if agent_id == "warm_pool" else "false"
            },
            environment={
                "PYTHONDONTWRITEBYTECODE": "1",
                "PYTHONUNBUFFERED": "1",
            },
        )

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

    async def create_sandbox(
        self,
        agent_id: str,
        config: Optional[SandboxConfig] = None
    ) -> Dict[str, Any]:
        """
        Create a new sandbox container for code execution.
        Uses warm pool if available for instant startup.

        Args:
            agent_id: Agent requesting the sandbox
            config: Sandbox configuration (uses defaults if None)

        Returns:
            Dict with sandbox_id, container_id, status
        """
        import asyncio
        if not self.docker_client:
            raise RuntimeError("Docker client not available")

        await self._ensure_pool_lock()
        
        warm_container = None
        # Fast path: try to pop from warm pool
        async with self._pool_lock:
            if self._warm_pool:
                warm_container = self._warm_pool.pop()
                
        if warm_container:
            logger.info(f"Popped warm sandbox {warm_container['sandbox_id']} for agent {agent_id}. Replenishing pool...")
            # Claim it by updating labels (best effort)
            try:
                container = self.docker_client.containers.get(warm_container['container_id'])
                # Docker doesn't support updating labels on running containers easily,
                # but we logically track it in our system now.
            except Exception as e:
                logger.warning(f"Could not retrieve warm container {warm_container['sandbox_id']}: {e}")
            
            # Kick off background replenishment
            asyncio.create_task(self._replenish_warm_pool(config))
            return warm_container
            
        # Slow path: create on demand if pool is empty
        logger.warning(f"Warm pool empty. Cold-starting sandbox for agent {agent_id}")
        config = config or SandboxConfig()
        
        try:
            container_info = await self._create_raw_container(agent_id, config)
            logger.info(f"Created cold sandbox {container_info['sandbox_id']} for agent {agent_id}")
            # Still kick off background replenishment to fix the empty pool
            asyncio.create_task(self._replenish_warm_pool(config))
            return container_info

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
