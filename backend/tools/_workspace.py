"""Agent workspace resolution on the host-mounted filesystem.

Generated artifacts should persist to a host-visible directory so the
Sovereign can open them outside Docker. The backend container bind-mounts the
host home at /host_home (see docker-compose.yml), so writing under
/host_home/agentium-workspace/... lands on the real machine.

Mirrors host_path.resolve_host_path: relative/bare paths resolve into the
agent workspace; absolute /host or /host_home paths pass through; other
absolute or /tmp paths stay container-local.
"""
import logging
import os

logger = logging.getLogger(__name__)

DEFAULT_WORKSPACE_ROOT = "/host_home/agentium-workspace"
HOME_MOUNT = "/host_home"


def _join(base: str, rest: str) -> str:
    # Resolved paths are always consumed inside the Linux container, so force
    # forward slashes regardless of the dev host's OS path separator.
    return base.rstrip("/") + "/" + rest.lstrip("/")


def workspace_enabled() -> bool:
    return os.getenv("AGENTIUM_WORKSPACE_ENABLED", "true").lower() == "true"


def workspace_root() -> str:
    return os.getenv("AGENTIUM_WORKSPACE_ROOT", DEFAULT_WORKSPACE_ROOT)


def agent_workspace_path(agent_id: str) -> str:
    agent_id = (agent_id or "30001").strip() or "30001"
    return _join(workspace_root(), agent_id)


def ensure_agent_workspace(agent_id: str, task_id: str | None = None) -> str:
    """Create and return the host-visible workspace dir for an agent/task."""
    path = agent_workspace_path(agent_id)
    if task_id:
        path = _join(path, str(task_id))
    os.makedirs(path, exist_ok=True)
    return path


def resolve_in_workspace(path: str, agent_id: str) -> str:
    """Resolve a possibly-relative path into the agent's host workspace.

    - absolute under /host/ or /host_home/ -> unchanged
    - /tmp or other absolute -> unchanged (container-local)
    - relative/bare filename -> <workspace>/<path>

    When the workspace feature is disabled, paths are returned unchanged so
    file writes stay container-local (graceful degradation).
    """
    if not workspace_enabled():
        return path
    if not isinstance(path, str) or not path.strip():
        return path
    if path.startswith("/host/") or path.startswith("/host_home/"):
        return path
    if os.path.isabs(path):
        return path
    return _join(agent_workspace_path(agent_id), path)


def validate_workspace_config() -> bool:
    """Validate AGENTIUM_WORKSPACE_ROOT resolves under a host bind mount.

    Returns True when the root is under /host or /host_home (so artifacts are
    actually visible on the host machine). Logs a warning and returns False
    otherwise — the feature simply degrades to container-local storage.
    """
    root = workspace_root()
    if root.startswith("/host/") or root.startswith("/host_home/"):
        return True
    logger.warning(
        "AGENTIUM_WORKSPACE_ROOT=%s is not under /host or /host_home; "
        "generated artifacts will NOT be visible on the host machine.",
        root,
    )
    return False


def host_visible_path(path: str) -> str:
    """Return a user-friendly '~'-shortened form of a host workspace path."""
    if path and path.startswith(HOME_MOUNT):
        return "~" + path[len(HOME_MOUNT):]
    return path


def _manifest(directory: str) -> list:
    """Walk a directory and return a list of {name, size} for each file."""
    items = []
    if not directory or not os.path.isdir(directory):
        return items
    for root, _, files in os.walk(directory):
        for fname in files:
            fp = os.path.join(root, fname)
            try:
                items.append({
                    "name": os.path.relpath(fp, directory).replace("\\", "/"),
                    "size": os.path.getsize(fp),
                })
            except OSError:
                continue
    return items
