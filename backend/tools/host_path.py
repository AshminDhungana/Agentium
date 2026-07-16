"""Host filesystem path resolution for containerized agents.

Agentium runs inside Docker. The host machine's filesystem is exposed to the
agent through two read-write bind mounts (see docker-compose.yml):

    HOST_FS_MOUNT  (/host)       -> the host's root filesystem (/)
    HOST_HOME_MOUNT (/host_home) -> the host user's home (USERPROFILE / $HOME)

When the Sovereign asks for a file "on my desktop" or "in my home directory",
the agent should write to the mount, not to the container's own filesystem.
These helpers translate an agent-supplied path onto the correct mount so files
actually land on the host PC.
"""

import os

# Defaults match docker-compose.yml (HOST_FS_MOUNT / HOST_HOME_MOUNT).
HOST_FS_MOUNT = os.getenv("HOST_FS_MOUNT", "/host")
HOST_HOME_MOUNT = os.getenv("HOST_HOME_MOUNT", "/host_home")


def resolve_host_path(
    path: str,
    fs_mount: str | None = None,
    home_mount: str | None = None,
) -> str:
    """Map an agent-supplied path onto the host bind mounts.

    Rules:
    - ``~`` expands to the host home mount (``/host_home``).
    - Paths already under ``/host`` or ``/host_home`` are returned unchanged.
    - ``/tmp`` and relative paths stay container-local (unchanged).
    - Any other absolute path is placed under the full host FS mount (``/host``).

    Args:
        path: Path as supplied by the agent / LLM.
        fs_mount: Override for tests; defaults to ``HOST_FS_MOUNT``.
        home_mount: Override for tests; defaults to ``HOST_HOME_MOUNT``.

    Returns:
        The resolved path to use for actual filesystem operations.
    """
    if not isinstance(path, str) or not path.strip():
        return path

    fs_mount = fs_mount or HOST_FS_MOUNT
    home_mount = home_mount or HOST_HOME_MOUNT

    # Resolved paths are always consumed inside the Linux container, so force
    # forward slashes regardless of the dev host's OS path separator.
    def _join(base: str, rest: str) -> str:
        return base.rstrip("/") + "/" + rest.lstrip("/")

    # Expand ~ to host home mount
    if path.startswith("~"):
        path = _join(home_mount, path[1:].lstrip("/"))

    # Already inside a host mount -> keep as-is
    for mount in (fs_mount, home_mount):
        if path == mount or path.startswith(mount + "/"):
            return path

    # Container-local paths -> leave untouched
    if path.startswith("/tmp") or not path.startswith("/"):
        return path

    # Other absolute paths -> place under the full host FS mount
    return _join(fs_mount, path.lstrip("/"))
