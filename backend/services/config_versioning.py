import os
import json
import logging
import threading
from datetime import datetime
from typing import Dict, Any, List

import git
from git.exc import InvalidGitRepositoryError, BadName

logger = logging.getLogger(__name__)

REPO_PATH = "/data/config-repo"

# Module-level lock — prevents concurrent GitPython index corruption when
# FastAPI async handlers or Celery workers call commit_snapshot in parallel.
_repo_lock = threading.Lock()

# Sentinel git identity used for all auto-commits so containers without a
# ~/.gitconfig never raise "Please tell me who you are" errors.
_GIT_NAME = "Agentium"
_GIT_EMAIL = "agentium@agentium.system"


class ConfigVersioningService:

    @classmethod
    def _get_repo(cls) -> git.Repo:
        os.makedirs(REPO_PATH, exist_ok=True)
        try:
            repo = git.Repo(REPO_PATH)
        except InvalidGitRepositoryError:
            repo = git.Repo.init(REPO_PATH)
            readme_path = os.path.join(REPO_PATH, "README.md")
            with open(readme_path, "w", encoding="utf-8") as f:
                f.write("# Agentium Config Backups\n")
            system_actor = git.Actor(_GIT_NAME, _GIT_EMAIL)
            repo.index.add(["README.md"])
            # Bug fix 1: always supply author/committer so containers without
            # a ~/.gitconfig don't raise "Please tell me who you are".
            repo.index.commit(
                "Initial commit",
                author=system_actor,
                committer=system_actor,
            )
        return repo

    @classmethod
    def commit_snapshot(
        cls,
        entity_type: str,
        entity_id: str,
        actor_id: str,
        payload_dict: dict,
    ) -> str:
        """
        Commits a JSON snapshot of the config to the git repository.
        Returns the new commit SHA, or the current HEAD SHA if content is
        unchanged (idempotent — won't create empty commits).
        Thread-safe: all git index operations are serialised via _repo_lock.
        """
        # Bug fix 3: serialise all git operations to prevent concurrent
        # index corruption from async FastAPI handlers / Celery workers.
        with _repo_lock:
            try:
                repo = cls._get_repo()
            except Exception as e:
                logger.error("Failed to initialise config-repo: %s", e)
                return ""

            dir_path = os.path.join(REPO_PATH, entity_type)
            os.makedirs(dir_path, exist_ok=True)

            file_name = f"{entity_id}.json"
            file_path = os.path.join(dir_path, file_name)

            try:
                with open(file_path, "w", encoding="utf-8") as f:
                    json.dump(payload_dict, f, indent=2, sort_keys=True)
            except Exception as e:
                logger.error(
                    "Failed to write snapshot for %s/%s: %s", entity_type, entity_id, e
                )
                return ""

            # Normalise path separator for Git (safe on Windows too).
            rel_path = f"{entity_type}/{file_name}"

            try:
                # Bug fix 6: detect changes BEFORE staging by comparing raw
                # bytes against the HEAD blob. This is reliable for both new
                # files (KeyError → always commit) and existing ones, and
                # avoids the dead-branch in the old untracked_files check.
                try:
                    head_blob = repo.head.commit.tree / rel_path
                    with open(file_path, "rb") as fh:
                        disk_bytes = fh.read()
                    if head_blob.data_stream.read() == disk_bytes:
                        # Content identical — skip the commit entirely.
                        return repo.head.commit.hexsha
                except KeyError:
                    # File doesn't exist in HEAD yet — it's new, always commit.
                    pass

                repo.index.add([rel_path])

                timestamp = datetime.utcnow().isoformat()
                commit_msg = (
                    f"[auto] {entity_type}/{entity_id} "
                    f"updated by {actor_id} at {timestamp}"
                )

                # Bug fix 1: pass explicit Actor so the commit never relies on
                # the system git config (absent in Docker containers).
                actor = git.Actor(actor_id, f"{actor_id}@agentium.system")
                commit = repo.index.commit(
                    commit_msg,
                    author=actor,
                    committer=git.Actor(_GIT_NAME, _GIT_EMAIL),
                )
                return commit.hexsha

            except Exception as e:
                logger.error(
                    "Failed to commit snapshot for %s/%s: %s", entity_type, entity_id, e
                )
                return ""

    @classmethod
    def get_config_history(
        cls, entity_type: str, entity_id: str
    ) -> List[Dict[str, Any]]:
        with _repo_lock:
            try:
                repo = cls._get_repo()
            except Exception:
                return []

        rel_path = f"{entity_type}/{entity_id}.json"
        history: List[Dict[str, Any]] = []

        try:
            commits = list(repo.iter_commits(paths=rel_path))
            for c in commits:
                actor_id = "system"
                if "updated by " in c.message:
                    parts = c.message.split("updated by ")
                    if len(parts) > 1 and " at " in parts[1]:
                        actor_id = parts[1].split(" at ")[0].strip()

                history.append(
                    {
                        "sha": c.hexsha,
                        "message": c.message.strip(),
                        "actor_id": actor_id,
                        "timestamp": c.committed_datetime.isoformat(),
                        "author": c.author.name,
                    }
                )
        except Exception as e:
            logger.error(
                "Failed to fetch history for %s/%s: %s", entity_type, entity_id, e
            )

        return history

    @classmethod
    def restore_snapshot(
        cls, entity_type: str, entity_id: str, commit_sha: str
    ) -> Dict[str, Any]:
        """
        Retrieves the JSON content of a file at a specific commit SHA.
        Raises ValueError for unknown SHA, missing file, or corrupt JSON
        so callers can map these to clean HTTP 400 responses.
        """
        with _repo_lock:
            repo = cls._get_repo()

        rel_path = f"{entity_type}/{entity_id}.json"

        try:
            # Bug fix 2: catch BadName raised by repo.commit() when the SHA
            # doesn't exist. The old code only caught KeyError (file missing
            # in tree) which let bad SHAs bubble up as an unhandled 500.
            try:
                commit = repo.commit(commit_sha)
            except BadName:
                raise ValueError(
                    f"Commit {commit_sha!r} not found in repository"
                )

            try:
                blob = commit.tree / rel_path
            except KeyError:
                raise ValueError(
                    f"File {rel_path!r} not found in commit {commit_sha!r}"
                )

            content = blob.data_stream.read().decode("utf-8")
            return json.loads(content)

        except ValueError:
            raise  # Re-raise our own clean errors unchanged.
        except json.JSONDecodeError:
            raise ValueError(
                f"File {rel_path!r} in commit {commit_sha!r} is not valid JSON"
            )
        except Exception as e:
            logger.error(
                "Unexpected error restoring %s/%s@%s: %s",
                entity_type, entity_id, commit_sha, e,
            )
            raise ValueError(f"Restore failed: {e}") from e