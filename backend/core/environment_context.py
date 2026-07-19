"""Single source of truth for agent runtime / host-environment grounding.

The string below is injected into every agent's Ethos `environment_context`
field at creation AND seeded into the read-only `agent_environment` ChromaDB
collection for RAG retrieval. Both channels import from here so the wording
stays in exactly one place.

Background (6.1): agents run inside a Docker container and otherwise have no
model of where the host machine is. The known failure mode is an agent writing
to its own container filesystem when the user asked for "my desktop". The
/host_home and /host bind mounts are the bridge to the real machine.
"""

AGENT_ENVIRONMENT_CONTEXT: str = (
    "You execute inside a sandboxed Docker container. The container is NOT the "
    "user's machine - it is an isolated execution environment with its own "
    "filesystem and process space. The real (host) machine is reachable through "
    "explicit read-write bind mounts:\n"
    "\n"
    "- /host_home  -> the host user's home directory (Desktop, Documents, "
    "Downloads, etc.). Example: the Sovereign's Desktop is /host_home/Desktop.\n"
    "- /host       -> the entire host filesystem root (e.g. /host/Users/... on "
    "macOS, /host/c/Users/... on Windows).\n"
    "\n"
    "When the Sovereign says 'my desktop', 'my Documents', or 'save to my "
    "machine', write to /host_home/... (NOT the container's own filesystem). "
    "These mounts are read-write; treat them as the user's real files. Prefer "
    "writing generated artifacts directly to the host mount over copying them "
    "out of the container.\n"
    "\n"
    "Your per-agent workspace for generated files is "
    "/host_home/agentium-workspace/<your_agent_id>/ so the user can open them "
    "on their machine. Use the get_workspace tool to discover your exact path.\n"
    "\n"
    "Network: the container has normal outbound internet egress, so you CAN "
    "reach external APIs, websites, and services. (Inbound/loopback and "
    "host-internal services are governed separately.) The host machine is "
    "reachable from the container via host.docker.internal when needed.\n"
)

# Stable id used for the idempotent ChromaDB document (Task 4/5).
ENV_CONTEXT_DOC_ID: str = "agent_environment_context"
