import os
import json
import logging
from datetime import datetime
from typing import Dict, Any, List

import git
from git.exc import InvalidGitRepositoryError

logger = logging.getLogger(__name__)

REPO_PATH = "/data/config-repo"

class ConfigVersioningService:
    @classmethod
    def _get_repo(cls) -> git.Repo:
        os.makedirs(REPO_PATH, exist_ok=True)
        try:
            repo = git.Repo(REPO_PATH)
        except InvalidGitRepositoryError:
            repo = git.Repo.init(REPO_PATH)
            # Make an initial commit
            readme_path = os.path.join(REPO_PATH, "README.md")
            with open(readme_path, "w", encoding="utf-8") as f:
                f.write("# Agentium Config Backups\n")
            repo.index.add(["README.md"])
            repo.index.commit("Initial commit")
        return repo

    @classmethod
    def commit_snapshot(cls, entity_type: str, entity_id: str, actor_id: str, payload_dict: dict) -> str:
        """
        Commits a JSON snapshot of the config to the git repository.
        Returns the new commit SHA or current SHA if unmodified.
        """
        try:
            repo = cls._get_repo()
        except Exception as e:
            logger.error(f"Failed to initialize config-repo for git versioning: {e}")
            return ""
            
        # Determine path
        dir_path = os.path.join(REPO_PATH, entity_type)
        os.makedirs(dir_path, exist_ok=True)
        
        file_name = f"{entity_id}.json"
        file_path = os.path.join(dir_path, file_name)
        
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(payload_dict, f, indent=2, sort_keys=True)
        except Exception as e:
            logger.error(f"Failed to write snapshot for {entity_type}/{entity_id}: {e}")
            return ""
            
        rel_path = os.path.join(entity_type, file_name)
        
        # Replace Windows slashes for Git index insertion just in case
        rel_path = rel_path.replace("\\", "/")
        
        try:
            repo.index.add([rel_path])
            
            # Check if actually changed
            changed = [item.a_path for item in repo.index.diff(repo.head.commit)]
            if rel_path not in changed and rel_path not in repo.untracked_files:
                # No changes
                return repo.head.commit.hexsha
                
            timestamp = datetime.utcnow().isoformat()
            commit_msg = f"[auto] {entity_type}/{entity_id} updated by {actor_id} at {timestamp}"
            
            commit = repo.index.commit(commit_msg)
            return commit.hexsha
        except Exception as e:
            logger.error(f"Failed to commit snapshot for {entity_type}/{entity_id}: {e}")
            return ""

    @classmethod
    def get_config_history(cls, entity_type: str, entity_id: str) -> List[Dict[str, Any]]:
        try:
            repo = cls._get_repo()
        except Exception:
            return []
            
        rel_path = f"{entity_type}/{entity_id}.json"
        
        history = []
        try:
            commits = list(repo.iter_commits(paths=rel_path))
            for c in commits:
                actor_id = "system"
                if "updated by " in c.message:
                    parts = c.message.split("updated by ")
                    if len(parts) > 1 and " at " in parts[1]:
                        actor_id = parts[1].split(" at ")[0]
                
                history.append({
                    "sha": c.hexsha,
                    "message": c.message.strip(),
                    "actor_id": actor_id,
                    "timestamp": c.committed_datetime.isoformat(),
                    "author": c.author.name
                })
        except Exception as e:
            logger.error(f"Failed to fetch history for {entity_type}/{entity_id}: {e}")
            
        return history

    @classmethod
    def restore_snapshot(cls, entity_type: str, entity_id: str, commit_sha: str) -> Dict[str, Any]:
        """
        Retrieves the JSON content of a file at a specific commit.
        """
        repo = cls._get_repo()
        rel_path = f"{entity_type}/{entity_id}.json"
        try:
            commit = repo.commit(commit_sha)
            blob = commit.tree / rel_path
            content = blob.data_stream.read().decode("utf-8")
            return json.loads(content)
        except KeyError:
            raise ValueError(f"File {rel_path} not found in commit {commit_sha}")
        except json.JSONDecodeError:
            raise ValueError(f"File {rel_path} in commit {commit_sha} is not valid JSON")
