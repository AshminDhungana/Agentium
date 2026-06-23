"""
Git Tool — Repository operations and version control.

Provides:
- Clone, pull, push repositories
- Branch management
- Commit creation
- Diff viewing
- Blame/ history
- Repository status
"""

import subprocess
import os
import re
from pathlib import Path
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from datetime import datetime


class GitTool:
    """
    Git operations for agent code management.
    """
    
    TOOL_NAME = "git"
    TOOL_DESCRIPTION = """
    Git version control operations.
    
    Use for:
    - Cloning repositories to work on
    - Checking out specific branches/commits
    - Viewing file history and diffs
    - Creating commits of agent work
    - Pushing changes to remotes
    
    All operations use the host git installation via /host mount.
    """
    
    AUTHORIZED_TIERS = ["0xxxx", "1xxxx", "2xxxx"]  # Task agents can't push
    
    def __init__(self):
        self.base_path = Path("/host_home/agentium-git")

    def _ensure_base_path(self):
        self.base_path.mkdir(parents=True, exist_ok=True)
    
    async def execute(
        self,
        action: str,
        repo_url: Optional[str] = None,
        path: Optional[str] = None,
        branch: Optional[str] = None,
        message: Optional[str] = None,
        files: Optional[List[str]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """Execute git action."""
        
        handlers = {
            "clone": self._clone,
            "status": self._status,
            "log": self._log,
            "diff": self._diff,
            "checkout": self._checkout,
            "pull": self._pull,
            "commit": self._commit,
            "push": self._push,
            "branch_list": self._branch_list,
            "blame": self._blame,
        }
        
        handler = handlers.get(action)
        if not handler:
            return {"success": False, "error": f"Unknown action: {action}"}
        
        try:
            result = await handler(
                repo_url=repo_url,
                path=path,
                branch=branch,
                message=message,
                files=files,
                **kwargs
            )
            return {"success": True, "action": action, **result}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def _clone(self, repo_url: str, path: Optional[str] = None, **kwargs) -> Dict[str, Any]:
        """Clone repository."""
        self._ensure_base_path()
        target = self.base_path / (path or self._repo_name_from_url(repo_url))
        
        result = subprocess.run(
            ["git", "clone", repo_url, str(target)],
            capture_output=True,
            text=True,
            timeout=300
        )
        
        if result.returncode != 0:
            return {"error": result.stderr}
        
        return {
            "cloned_to": str(target),
            "repo_name": target.name
        }
    
    async def _status(self, path: str, **kwargs) -> Dict[str, Any]:
        """Get repository status."""
        result = subprocess.run(
            ["git", "-C", path, "status", "--porcelain", "-b"],
            capture_output=True,
            text=True
        )
        
        lines = result.stdout.strip().split("\n") if result.stdout else []
        
        # Parse branch info
        branch_line = lines[0] if lines else ""
        branch_match = re.search(r'## (\S+)\.\.\.(\S+)?', branch_line)
        branch = branch_match.group(1) if branch_match else "unknown"
        remote = branch_match.group(2) if branch_match and branch_match.group(2) else None
        
        # Parse file status
        staged = []
        unstaged = []
        untracked = []
        
        for line in lines[1:]:
            if not line:
                continue
            status = line[:2]
            filename = line[3:].strip()
            
            if status[0] != ' ' and status[0] != '?':
                staged.append({"file": filename, "status": status[0]})
            elif status[1] != ' ':
                unstaged.append({"file": filename, "status": status[1]})
            elif status == '??':
                untracked.append(filename)
        
        return {
            "branch": branch,
            "remote_tracking": remote,
            "ahead_behind": self._get_ahead_behind(path),
            "staged": staged,
            "unstaged": unstaged,
            "untracked": untracked,
            "is_clean": len(staged) == 0 and len(unstaged) == 0 and len(untracked) == 0
        }
    
    async def _log(self, path: str, limit: int = 10, **kwargs) -> Dict[str, Any]:
        """Get commit history."""
        result = subprocess.run(
            ["git", "-C", path, "log", f"-{limit}", "--pretty=format:%H|%an|%ad|%s", "--date=short"],
            capture_output=True,
            text=True
        )
        
        commits = []
        for line in result.stdout.strip().split("\n"):
            if "|" in line:
                hash_, author, date, message = line.split("|", 3)
                commits.append({
                    "hash": hash_[:8],
                    "full_hash": hash_,
                    "author": author,
                    "date": date,
                    "message": message
                })
        
        return {"commits": commits}
    
    async def _diff(self, path: str, commit: Optional[str] = None, **kwargs) -> Dict[str, Any]:
        """Get diff."""
        cmd = ["git", "-C", path, "diff"]
        if commit:
            cmd.extend([f"{commit}~1", commit])
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        return {
            "diff": result.stdout,
            "files_changed": len([l for l in result.stdout.split("\n") if l.startswith("diff --git")])
        }
    
    async def _checkout(self, path: str, branch: str, **kwargs) -> Dict[str, Any]:
        """Checkout branch."""
        result = subprocess.run(
            ["git", "-C", path, "checkout", branch],
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            # Try to create branch
            result = subprocess.run(
                ["git", "-C", path, "checkout", "-b", branch],
                capture_output=True,
                text=True
            )
        
        return {
            "checked_out": result.returncode == 0,
            "branch": branch,
            "output": result.stdout or result.stderr
        }
    
    async def _commit(self, path: str, message: str, files: Optional[List[str]] = None, **kwargs) -> Dict[str, Any]:
        """Create commit."""
        # Stage files if specified
        if files:
            subprocess.run(["git", "-C", path, "add"] + files, check=True)
        else:
            # Stage all
            subprocess.run(["git", "-C", path, "add", "-A"], check=True)
        
        # Commit
        result = subprocess.run(
            ["git", "-C", path, "commit", "-m", message],
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            return {"error": result.stderr, "nothing_to_commit": "nothing to commit" in result.stderr}
        
        # Get commit hash
        hash_result = subprocess.run(
            ["git", "-C", path, "rev-parse", "HEAD"],
            capture_output=True,
            text=True
        )
        
        return {
            "committed": True,
            "hash": hash_result.stdout.strip()[:8],
            "message": message
        }
    
    async def _push(self, path: str, remote: str = "origin", branch: Optional[str] = None, **kwargs) -> Dict[str, Any]:
        """Push to remote."""
        cmd = ["git", "-C", path, "push", remote]
        if branch:
            cmd.append(branch)
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        return {
            "pushed": result.returncode == 0,
            "output": result.stdout,
            "error": result.stderr if result.returncode != 0 else None
        }
    
    async def _pull(self, path: str, **kwargs) -> Dict[str, Any]:
        """Pull from remote."""
        result = subprocess.run(
            ["git", "-C", path, "pull"],
            capture_output=True,
            text=True
        )
        
        return {
            "pulled": result.returncode == 0,
            "output": result.stdout,
            "files_changed": self._parse_pull_output(result.stdout)
        }
    
    async def _branch_list(self, path: str, **kwargs) -> Dict[str, Any]:
        """List branches."""
        result = subprocess.run(
            ["git", "-C", path, "branch", "-a", "--format=%(refname:short)|%(upstream:short)|%(HEAD)"],
            capture_output=True,
            text=True
        )
        
        branches = []
        current = None
        for line in result.stdout.strip().split("\n"):
            if "|" in line:
                name, upstream, is_head = line.split("|")
                is_current = is_head == "*"
                if is_current:
                    current = name
                
                branches.append({
                    "name": name,
                    "current": is_current,
                    "remote": upstream if upstream else None
                })
        
        return {"branches": branches, "current": current}
    
    async def _blame(self, path: str, file: str, **kwargs) -> Dict[str, Any]:
        """Get blame for file."""
        result = subprocess.run(
            ["git", "-C", path, "blame", "--porcelain", file],
            capture_output=True,
            text=True
        )
        
        # Parse blame output
        lines = []
        current_author = None
        
        for line in result.stdout.split("\n"):
            if line.startswith("author "):
                current_author = line[7:]
            elif line.startswith("\t"):
                lines.append({
                    "content": line[1:],
                    "author": current_author
                })
        
        return {
            "file": file,
            "lines": lines[:50],  # Limit
            "total_lines": len(lines)
        }
    
    def _repo_name_from_url(self, url: str) -> str:
        """Extract repo name from URL."""
        return url.rstrip("/").split("/")[-1].replace(".git", "")
    
    def _get_ahead_behind(self, path: str) -> Dict[str, int]:
        """Get ahead/behind counts."""
        result = subprocess.run(
            ["git", "-C", path, "rev-list", "--left-right", "--count", "HEAD...@{upstream}"],
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            ahead, behind = result.stdout.strip().split("\t")
            return {"ahead": int(ahead), "behind": int(behind)}
        return {"ahead": 0, "behind": 0}
    
    def _parse_pull_output(self, output: str) -> int:
        """Parse number of files changed from pull output."""
        # Look for "X files changed"
        match = re.search(r'(\d+) files? changed', output)
        return int(match.group(1)) if match else 0


git_tool = GitTool()

# Alias required by ToolFactory.load_tool() dynamic loader
tool_instance = git_tool