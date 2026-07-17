"""
Vector Store configuration for Agentium.
ChromaDB-backed RAG infrastructure for collective agent memory.
"""

import json
import logging
import os
from contextlib import contextmanager
from typing import Any, Dict, Generator, List, Optional, Union

import chromadb
from chromadb.api.types import EmbeddingFunction, QueryResult
from sentence_transformers import SentenceTransformer

from backend.core.config import settings as _settings
from backend.core.chunking import chunk_text
from backend.models.entities.knowledge_document import KnowledgeDocument

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration — read from environment, no hardcoded fallbacks for server
# ---------------------------------------------------------------------------
CHROMA_PERSIST_DIR: str = os.getenv("CHROMA_PERSIST_DIR", "./chroma_data")
V2_EMBEDDING_MODEL = "BAAI/bge-base-en-v1.5"
V2_EMBEDDING_DIM = 768
BGE_QUERY_PREFIX = "Represent this sentence for searching relevant passages: "
CHROMA_HOST: Optional[str] = os.getenv("CHROMA_HOST")  # None → local mode
CHROMA_PORT: int = int(os.getenv("CHROMA_PORT", "8000"))

V2_SUFFIX = "_v2"

COLLECTIONS_V2: Dict[str, str] = {
    "constitution": "supreme_law_v2",
    "ethos": "agent_ethos_v2",
    "task_patterns": "execution_patterns_v2",
    "domain_knowledge": "domain_knowledge_v2",
}


class BgeEmbeddingFunction(EmbeddingFunction):
    """bge-base-en-v1.5 — asymmetric: prefix queries, not documents; L2-normalized."""

    def __init__(self, model_name: Optional[str] = None) -> None:
        self.model_name = model_name or _settings.EMBEDDING_MODEL
        self._model = None

    @property
    def model(self) -> SentenceTransformer:
        if self._model is None:
            self._model = SentenceTransformer(self.model_name)
        return self._model

    def _with_prefix(self, text: str) -> str:
        return f"{BGE_QUERY_PREFIX}{text}"

    def embed_documents(self, input: List[str]) -> List[List[float]]:
        return self.model.encode(input, convert_to_numpy=True, normalize_embeddings=True).tolist()

    def embed_query(self, input: Union[str, List[str]]) -> List[List[float]]:
        # ChromaDB 1.5.1 calls embed_query with a list of query texts; accept
        # both a single string and a list so v2 queries don't crash.
        texts = input if isinstance(input, list) else [input]
        prefixed = [self._with_prefix(t) for t in texts]
        return self.model.encode(prefixed, convert_to_numpy=True, normalize_embeddings=True).tolist()

    def __call__(self, input: List[str]) -> List[List[float]]:
        # Default path (collection init / stored documents) = no prefix, normalized.
        return self.embed_documents(input)


AgentiumEmbeddingFunction = BgeEmbeddingFunction


class VectorStore:
    """
    ChromaDB wrapper for Agentium.

    Provides tiered collections for different knowledge types with
    persistent storage and semantic search capabilities.

    When ``CHROMA_HOST`` is set the client connects to the ChromaDB HTTP
    server (docker-compose service).  Otherwise it falls back to a local
    ``PersistentClient`` for development / testing.
    """

    # ------------------------------------------------------------------
    # Collection registry
    # Key  → ChromaDB collection name (no raw strings elsewhere in code)
    # ------------------------------------------------------------------
    COLLECTIONS: Dict[str, str] = {
        "constitution": "supreme_law",
        "ethos": "agent_ethos",
        "council_memory": "council_knowledge",
        # FIX: canonical key used everywhere (was "task_patterns" in some
        # places and "execution_patterns" in others — unified to one key)
        "task_patterns": "execution_patterns",
        "audit_semantic": "audit_history",
        "sovereign_prefs": "sovereign_memory",
        # Skill collections (used by SkillManager)
        "agent_skills": "agent_skills",
        "best_practices": "best_practices",
        "constitutional_skills": "constitutional_skills",
        "tool_skills": "tool_skills",
    }

    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
    ) -> None:
        # Allow callers (e.g. test fixtures) to override the module-level
        # globals so that a VectorStore pointed at the test ChromaDB instance
        # can be constructed without mutating global state.
        self._host: Optional[str] = host if host is not None else CHROMA_HOST
        self._port: int = port if port is not None else CHROMA_PORT
        self._client: Optional[chromadb.ClientAPI] = None
        self._v2_embedding_fn = BgeEmbeddingFunction()
        self._collections: Dict[str, chromadb.Collection] = {}
        self._collections_by_name: Dict[str, chromadb.Collection] = {}

    # ------------------------------------------------------------------
    # Initialisation
    # ------------------------------------------------------------------

    def initialize(self) -> chromadb.ClientAPI:
        """
        Initialize ChromaDB client.

        Connects to the HTTP server when ``CHROMA_HOST`` is configured
        (production / docker-compose), otherwise uses a local persistent
        client (development).
        """
        if self._client is not None:
            return self._client

        if self._host:
            # Production: connect to the dedicated ChromaDB container
            logger.info(
                "Connecting to ChromaDB HTTP server at %s:%d",
                self._host,
                self._port,
            )
            self._client = chromadb.HttpClient(
                host=self._host,
                port=self._port,
            )
        else:
            # Development / CI: local persistent storage
            os.makedirs(CHROMA_PERSIST_DIR, exist_ok=True)
            logger.info(
                "Using local ChromaDB persistent client at %s",
                CHROMA_PERSIST_DIR,
            )
            self._client = chromadb.PersistentClient(path=CHROMA_PERSIST_DIR)

        # Pre-create / get all v2 collections eagerly (v1 was retired).
        for key in self.COLLECTIONS:
            try:
                self._collections[key] = self.get_collection(key)
            except Exception:  # noqa: BLE001
                logger.exception("Could not initialise collection '%s'", key)

        return self._client

    @property
    def client(self) -> chromadb.ClientAPI:
        """Return (or lazily initialise) the ChromaDB client."""
        if self._client is None:
            self.initialize()
        return self._client

    # ------------------------------------------------------------------
    # Collection access
    # ------------------------------------------------------------------

    def _active_version(self, key: str) -> str:
        # v1 (MiniLM) was retired; the only supported version is now v2 (bge).
        # Kept for API compatibility — always returns "v2".
        return "v2"

    def _collection_name(self, key: str, version: Optional[str] = None) -> str:
        # v1 collections were retired; every collection now resolves to its v2
        # (bge, cosine) name regardless of the requested version.
        return COLLECTIONS_V2.get(key, f"{self.COLLECTIONS.get(key, key)}{V2_SUFFIX}")

    def get_collection(self, collection_key: str, version: Optional[str] = None):
        """
        Return a collection by its logical key.

        The v1 (MiniLM) embedding path was retired; all collections use the
        bge-base-en-v1.5 embedding function and a cosine HNSW space. The
        ``version`` argument is accepted for backwards compatibility but always
        resolves to the v2 collection.

        Raises ``ValueError`` for unknown keys so callers get an explicit
        error rather than a confusing ``KeyError``.
        """
        if collection_key not in self.COLLECTIONS:
            raise ValueError(
                f"Unknown collection key '{collection_key}'. "
                f"Valid keys: {list(self.COLLECTIONS)}"
            )

        name = self._collection_name(collection_key, version)
        ef = self._v2_embedding_fn
        if name not in self._collections_by_name:
            cfg = {"hnsw": {"space": "cosine"}}
            try:
                self._collections_by_name[name] = self.client.get_or_create_collection(
                    name=name, embedding_function=ef, configuration=cfg,
                )
            except TypeError:
                # Older chromadb: space passed via metadata instead of configuration=
                self._collections_by_name[name] = self.client.get_or_create_collection(
                    name=name, embedding_function=ef,
                    metadata={"hnsw:space": "cosine"},
                )

        return self._collections_by_name[name]

    # ------------------------------------------------------------------
    # Write helpers
    # ------------------------------------------------------------------

    def add_constitution_article(
        self,
        article_id: str,
        content: str,
        metadata: Dict[str, Any],
        db: Optional[Any] = None,
    ) -> None:
        """Store a constitutional article for RAG retrieval.

        When ``db`` is supplied the untruncated ``content`` is persisted in the
        ``knowledge_documents`` parent store (chunked vectors in ChromaDB).
        Without ``db`` the legacy single-document upsert is used for callers
        that do not hold a session (e.g. unit tests).
        """
        parent_id = f"const_{article_id}"
        rich_meta = {
            **metadata,
            "type": "constitution_article",
            "article_id": article_id,
            "document_type": "supreme_law",
            "immutable": True,
        }
        if db is not None:
            self.upsert_document("constitution", parent_id, content, rich_meta, db)
            return
        collection = self.get_collection("constitution")
        collection.upsert(
            documents=[content],
            metadatas=[rich_meta],
            ids=[parent_id],
        )

    def add_ethos(
        self,
        agentium_id: str,
        ethos_content: str,
        agent_type: str,
        verified_by: Optional[str] = None,
        db: Optional[Any] = None,
    ) -> None:
        """Store agent ethos for semantic retrieval."""
        parent_id = f"ethos_{agentium_id}"
        rich_meta = {
            "agentium_id": agentium_id,
            "agent_type": agent_type,
            "verified_by": verified_by or "",
            "type": "ethos",
            "document_type": "behavioral_rules",
        }
        if db is not None:
            self.upsert_document("ethos", parent_id, ethos_content, rich_meta, db)
            return
        collection = self.get_collection("ethos")
        collection.upsert(
            documents=[ethos_content],
            metadatas=[rich_meta],
            ids=[parent_id],
        )

    def add_execution_pattern(
        self,
        pattern_id: str,
        description: str,
        success_rate: float,
        task_type: str,
        tools_used: Optional[List[str]] = None,
        db: Optional[Any] = None,
    ) -> None:
        """Store a successful execution pattern for future RAG."""
        # FIX: use canonical key "task_patterns" (collection name is still
        # "execution_patterns" on the ChromaDB side — the key is internal)
        parent_id = f"pattern_{pattern_id}"
        rich_meta = {
            "pattern_id": pattern_id,
            "success_rate": success_rate,
            "task_type": task_type,
            "tools_used": json.dumps(tools_used or []),
            "type": "execution_pattern",
            "document_type": "learned_behavior",
        }
        if db is not None:
            self.upsert_document("task_patterns", parent_id, description, rich_meta, db)
            return
        collection = self.get_collection("task_patterns")
        collection.upsert(
            documents=[description],
            metadatas=[rich_meta],
            ids=[parent_id],
        )

    # ------------------------------------------------------------------
    # Chunk-aware parent-document storage
    # ------------------------------------------------------------------

    def upsert_document(self, collection_key, parent_id, text, metadata, db):
        """Chunk-aware write: full text -> Postgres, chunk vectors -> ChromaDB.

        Stores the untruncated *text* in the ``knowledge_documents`` table
        (keyed by collection_key + parent_id) and upserts one embedded chunk
        entry per chunk into the ChromaDB collection.  Chunk ids follow the
        scheme ``f"{parent_id}#chunk{i}"`` and carry ``parent_id``,
        ``chunk_index``, ``chunk_count`` and ``is_chunk`` metadata.
        """
        if not text or not text.strip():
            raise ValueError("text must be non-empty")
        metadata = dict(metadata or {})
        chunks = chunk_text(text)
        chunk_count = len(chunks)

        # 1) Upsert parent full text in Postgres
        row = (
            db.query(KnowledgeDocument)
            .filter_by(collection_key=collection_key, parent_id=parent_id)
            .first()
        )
        if row is None:
            row = KnowledgeDocument(
                collection_key=collection_key,
                parent_id=parent_id,
                full_text=text,
                doc_metadata=metadata,
                chunk_count=chunk_count,
            )
            db.add(row)
        else:
            row.full_text = text
            row.doc_metadata = metadata
            row.chunk_count = chunk_count
        db.commit()

        # 2) Replace chunk vectors in ChromaDB
        collection = self.get_collection(collection_key)
        try:
            collection.delete(where={"parent_id": parent_id})
        except Exception:  # noqa: BLE001
            logger.debug("No prior chunks to delete for %s", parent_id)

        ids = [f"{parent_id}#chunk{i}" for i in range(chunk_count)]
        metadatas = [
            {
                **metadata,
                "parent_id": parent_id,
                "chunk_index": i,
                "chunk_count": chunk_count,
                "is_chunk": True,
            }
            for i in range(chunk_count)
        ]
        embeddings = self._v2_embedding_fn.embed_documents(chunks)
        collection.upsert(
            ids=ids, documents=chunks, metadatas=metadatas, embeddings=embeddings
        )

        return {
            "parent_id": parent_id,
            "chunk_count": chunk_count,
            "collection_key": collection_key,
        }

    def get_parent_document(self, collection_key, parent_id, db):
        """Return the untruncated parent document, or ``None`` if absent."""
        row = (
            db.query(KnowledgeDocument)
            .filter_by(collection_key=collection_key, parent_id=parent_id)
            .first()
        )
        if row is None:
            return None
        return {
            "parent_id": parent_id,
            "full_text": row.full_text,
            "metadata": row.doc_metadata or {},
            "chunk_count": row.chunk_count,
        }

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------

    def query_knowledge(
        self,
        query: str,
        collection_keys: Optional[List[str]] = None,
        n_results: int = 5,
        filter_dict: Optional[Dict[str, Any]] = None,
        db: Optional[Any] = None,
    ) -> QueryResult:
        """
        Query across one or more knowledge collections.

        Defaults to searching all collections when ``collection_keys`` is
        not supplied.  Chunk vectors are queried and then deduplicated by
        ``parent_id`` (keeping the closest chunk per parent).  When ``db``
        is provided the untruncated full parent document is returned in
        place of the chunk text; otherwise the closest chunk text is used.
        Results are ranked by effective distance (decay + citation) and
        truncated to ``n_results``.
        """
        keys = collection_keys or list(self.COLLECTIONS.keys())

        # Query both chunk vectors (new parent-document store) and legacy
        # standalone documents.  Chunks carry ``parent_id`` + ``is_chunk`` and
        # are later resolved to full text; legacy docs are returned as-is.
        where = dict(filter_dict or {})

        raw_results: List[QueryResult] = []
        for key in keys:
            try:
                collection = self.get_collection(key)
                query_kwargs = {"query_texts": [query], "n_results": n_results}
                if where:
                    query_kwargs["where"] = where
                result = collection.query(**query_kwargs)
                raw_results.append(result)
            except Exception:  # noqa: BLE001
                logger.exception("Query failed for collection '%s'", key)

        # Deduplicate chunks by parent_id, keeping the best raw-distance chunk.
        best_by_parent: Dict[str, Dict[str, Any]] = {}
        for result in raw_results:
            if not result.get("ids"):
                continue
            for i, chunk_id in enumerate(result["ids"][0]):
                meta = (
                    result["metadatas"][0][i]
                    if result.get("metadatas")
                    else {}
                )
                parent_id = meta.get("parent_id") or chunk_id
                distance = (
                    result["distances"][0][i]
                    if result.get("distances")
                    else 0.0
                )
                prev = best_by_parent.get(parent_id)
                if prev is None or distance < prev["distance"]:
                    best_by_parent[parent_id] = {
                        "parent_id": parent_id,
                        "chunk_id": chunk_id,
                        "chunk_text": (
                            result["documents"][0][i]
                            if result.get("documents")
                            else ""
                        ),
                        "metadata": meta,
                        "distance": distance,
                    }

        entries: List[Dict[str, Any]] = []
        for parent_id, best in best_by_parent.items():
            full_text = best["chunk_text"]
            merged_meta = dict(best["metadata"])
            is_chunk = merged_meta.get("is_chunk") is True
            if is_chunk and db is not None:
                parent = None
                for ckey in (collection_keys or keys):
                    parent = self.get_parent_document(ckey, parent_id, db)
                    if parent is not None:
                        break
                if parent is not None:
                    full_text = parent["full_text"]
                    # Parent-level metadata takes precedence (keeps decay/citation).
                    merged_meta = {**merged_meta, **(parent["metadata"] or {})}
            merged_meta.pop("is_chunk", None)
            merged_meta.pop("chunk_index", None)
            merged_meta.pop("chunk_count", None)
            entries.append(
                {
                    "id": parent_id,
                    "document": full_text,
                    "metadata": merged_meta,
                    "distance": best["distance"],
                }
            )

        # Phase 16.2/16.3: decay + citation weighting on effective distance.
        for entry in entries:
            meta = entry.get("metadata") or {}
            decay_score = max(0.1, min(1.0, float(meta.get("decay_score", 1.0))))
            citation_boost = max(1.0, min(1.3, float(meta.get("citation_boost", 1.0))))
            entry["effective_distance"] = entry["distance"] / (
                decay_score * citation_boost
            )

        entries.sort(key=lambda e: e["effective_distance"])
        entries = entries[:n_results]

        return {
            "ids": [[e["id"] for e in entries]],
            "documents": [[e["document"] for e in entries]],
            "metadatas": [[e["metadata"] for e in entries]],
            "distances": [[e["distance"] for e in entries]],
        }

    def query_constitution(
        self,
        query: str,
        n_results: int = 3,
    ) -> QueryResult:
        """Query specifically constitutional content."""
        collection = self.get_collection("constitution")
        return collection.query(
            query_texts=[query],
            n_results=n_results,
            where={"document_type": "supreme_law"},
        )

    def query_hierarchical_context(
        self,
        agent_type: str,
        task_description: str,
        n_results: int = 5,
    ) -> Dict[str, QueryResult]:
        """
        Retrieve hierarchical RAG context based on agent tier.

        Tier mapping
        ------------
        head_of_council : constitution only
        council_member  : constitution + council deliberations
        lead_agent      : constitution + task patterns
        task_agent      : constitution + execution patterns (filtered)
        """
        context: Dict[str, QueryResult] = {}

        # All tiers are grounded in the Constitution
        context["constitution"] = self.query_constitution(
            task_description, n_results=2
        )

        if agent_type == "council_member":
            context["council_memory"] = self.get_collection(
                "council_memory"
            ).query(
                query_texts=[task_description],
                n_results=n_results,
            )
        elif agent_type == "lead_agent":
            context["task_patterns"] = self.get_collection(
                "task_patterns"
            ).query(
                query_texts=[task_description],
                n_results=n_results,
            )
        elif agent_type == "task_agent":
            context["task_patterns"] = self.get_collection(
                "task_patterns"
            ).query(
                query_texts=[task_description],
                n_results=n_results,
                where={"type": "execution_pattern"},
            )

        return context

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _merge_results(
        self,
        results: List[QueryResult],
        n_results: int,
    ) -> QueryResult:
        """
        Merge multiple query results.

        Deduplicates by ID and sorts by distance (ascending) so the
        highest-quality results survive truncation rather than the
        results that happen to appear first.
        """
        seen_ids: set = set()
        entries: List[Dict[str, Any]] = []

        for result in results:
            if not result.get("ids"):
                continue
            for i, doc_id in enumerate(result["ids"][0]):
                if doc_id in seen_ids:
                    continue
                seen_ids.add(doc_id)
                entries.append(
                    {
                        "id": doc_id,
                        "document": (
                            result["documents"][0][i]
                            if result.get("documents")
                            else ""
                        ),
                        "metadata": (
                            result["metadatas"][0][i]
                            if result.get("metadatas")
                            else {}
                        ),
                        "distance": (
                            result["distances"][0][i]
                            if result.get("distances")
                            else 0.0
                        ),
                    }
                )

        # Phase 16.2: Apply decay_score weighting — stale knowledge gets
        # a higher effective distance so it ranks below fresh knowledge.
        # Phase 16.3: Apply citation_boost — more-cited documents get lower
        # effective distance so they rank higher.
        for entry in entries:
            meta = entry.get("metadata") or {}
            decay_score = float(meta.get("decay_score", 1.0))
            # Clamp to [0.1, 1.0] to prevent division by near-zero
            decay_score = max(0.1, min(1.0, decay_score))

            citation_boost = float(meta.get("citation_boost", 1.0))
            citation_boost = max(1.0, min(1.3, citation_boost))

            entry["effective_distance"] = entry["distance"] / (
                decay_score * citation_boost
            )

        # Sort ascending by effective distance so best results survive truncation
        entries.sort(key=lambda e: e["effective_distance"])
        entries = entries[:n_results]

        merged: QueryResult = {
            "ids": [[e["id"] for e in entries]],
            "documents": [[e["document"] for e in entries]],
            "metadatas": [[e["metadata"] for e in entries]],
            "distances": [[e["distance"] for e in entries]],
        }
        return merged

    # ------------------------------------------------------------------
    # Confidence Decay on Stale Knowledge (Phase 10.2)
    # ------------------------------------------------------------------

    def decay_stale_entries(
        self,
        max_age_days: int = 30,
        decay_factor: float = 0.85,
        min_confidence: float = 0.1,
        target_collections: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Reduce confidence of stale knowledge entries.

        Scans entries in the specified collections for metadata containing
        ``extracted_at`` or ``confidence`` fields. Entries older than
        ``max_age_days`` have their confidence multiplied by ``decay_factor``.
        Entries whose confidence drops below ``min_confidence`` are pruned.

        Returns a summary dict with counts of decayed and pruned entries.
        """
        import json as _json
        from datetime import datetime, timedelta

        cutoff = datetime.utcnow() - timedelta(days=max_age_days)
        collections_to_scan = target_collections or [
            "task_patterns", "best_practices",
        ]

        decayed = 0
        pruned = 0

        for coll_key in collections_to_scan:
            try:
                coll = self.get_collection(coll_key)
                all_docs = coll.get(include=["metadatas"])
                if not all_docs or not all_docs.get("ids"):
                    continue

                ids_to_delete: List[str] = []
                ids_to_update: List[str] = []
                metas_to_update: List[Dict[str, Any]] = []

                for i, doc_id in enumerate(all_docs["ids"]):
                    meta = (all_docs.get("metadatas") or [])[i] if all_docs.get("metadatas") else {}
                    if not meta:
                        continue

                    # Check if entry has a timestamp
                    extracted_at = (meta or {}).get("extracted_at", "")
                    if not extracted_at:
                        continue

                    try:
                        entry_time = datetime.fromisoformat(extracted_at.replace("Z", "+00:00").replace("+00:00", ""))
                    except (ValueError, TypeError):
                        continue

                    if entry_time >= cutoff:
                        continue  # Not stale yet

                    # Decay the confidence
                    current_confidence = float(meta.get("confidence", 1.0))
                    new_confidence = current_confidence * decay_factor

                    if new_confidence < min_confidence:
                        ids_to_delete.append(doc_id)
                        pruned += 1
                    else:
                        updated_meta = dict(meta)
                        updated_meta["confidence"] = round(new_confidence, 4)
                        updated_meta["decay_applied"] = "true"
                        ids_to_update.append(doc_id)
                        metas_to_update.append(updated_meta)
                        decayed += 1

                # Apply deletions
                if ids_to_delete:
                    coll.delete(ids=ids_to_delete)

                # Apply updates
                if ids_to_update:
                    coll.update(ids=ids_to_update, metadatas=metas_to_update)

            except Exception as exc:
                logger.warning(
                    "Confidence decay skipped collection '%s': %s",
                    coll_key, exc,
                )

        if decayed > 0 or pruned > 0:
            logger.info(
                "Confidence decay: decayed %d entries, pruned %d entries",
                decayed, pruned,
            )

        return {"decayed": decayed, "pruned": pruned}

    # ------------------------------------------------------------------
    # Phase 16.2: Exponential Learning Decay & Validation Boost
    # ------------------------------------------------------------------

    def apply_learning_decay(
        self,
        grace_days: int = 30,
        decay_base: float = 0.95,
        min_decay_score: float = 0.1,
        target_collections: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Apply exponential time-based decay to knowledge entries.

        For each document older than ``grace_days`` since its
        ``last_validated_at`` timestamp, compute:

            decay_score = max(min_decay_score,
                              current_decay × decay_base ^ days_since_validation)

        Documents whose ``decay_score`` falls below ``min_decay_score``
        are pruned entirely.  Documents without ``last_validated_at`` are
        backfilled with ``extracted_at`` or ``created_at`` on first run.

        Returns a summary dict with counts of decayed, pruned, and
        backfilled entries.
        """
        from datetime import datetime, timedelta

        now = datetime.utcnow()
        cutoff = now - timedelta(days=grace_days)
        collections_to_scan = target_collections or [
            "task_patterns", "best_practices",
        ]

        decayed = 0
        pruned = 0
        backfilled = 0

        for coll_key in collections_to_scan:
            try:
                coll = self.get_collection(coll_key)
                all_docs = coll.get(include=["metadatas"])
                if not all_docs or not all_docs.get("ids"):
                    continue

                ids_to_delete: List[str] = []
                ids_to_update: List[str] = []
                metas_to_update: List[Dict[str, Any]] = []

                for i, doc_id in enumerate(all_docs["ids"]):
                    meta = (
                        (all_docs.get("metadatas") or [])[i]
                        if all_docs.get("metadatas")
                        else {}
                    )
                    if not meta:
                        continue

                    # ── Resolve last_validated_at (backfill if missing) ────
                    validated_at_str = meta.get("last_validated_at", "")
                    needs_backfill = False

                    if not validated_at_str:
                        # Backfill from extracted_at or created_at
                        validated_at_str = (
                            meta.get("extracted_at")
                            or meta.get("created_at")
                            or ""
                        )
                        if validated_at_str:
                            needs_backfill = True
                        else:
                            continue  # No timestamp at all — skip

                    try:
                        validated_at = datetime.fromisoformat(
                            validated_at_str.replace("Z", "+00:00")
                                           .replace("+00:00", "")
                        )
                    except (ValueError, TypeError):
                        continue

                    # ── Backfill defaults on first encounter ──────────────
                    current_decay = float(meta.get("decay_score", 1.0))
                    if needs_backfill:
                        updated_meta = dict(meta)
                        updated_meta["last_validated_at"] = validated_at_str
                        if "decay_score" not in meta:
                            updated_meta["decay_score"] = 1.0
                            current_decay = 1.0
                        ids_to_update.append(doc_id)
                        metas_to_update.append(updated_meta)
                        backfilled += 1
                        # Still check if this entry also needs decay below
                        # (it might be very old)

                    if validated_at >= cutoff:
                        continue  # Within grace period — no decay

                    # ── Exponential decay ─────────────────────────────────
                    days_since = (now - validated_at).days
                    new_decay = current_decay * (decay_base ** days_since)
                    new_decay = round(new_decay, 6)

                    if new_decay < min_decay_score:
                        ids_to_delete.append(doc_id)
                        # Remove from update list if already queued for backfill
                        if doc_id in ids_to_update:
                            idx = ids_to_update.index(doc_id)
                            ids_to_update.pop(idx)
                            metas_to_update.pop(idx)
                        pruned += 1
                    else:
                        # Check if already in update list (from backfill)
                        if doc_id in ids_to_update:
                            idx = ids_to_update.index(doc_id)
                            metas_to_update[idx]["decay_score"] = new_decay
                            metas_to_update[idx]["decay_applied_at"] = (
                                now.isoformat()
                            )
                        else:
                            updated_meta = dict(meta)
                            updated_meta["decay_score"] = new_decay
                            updated_meta["decay_applied_at"] = (
                                now.isoformat()
                            )
                            ids_to_update.append(doc_id)
                            metas_to_update.append(updated_meta)
                        decayed += 1

                # Apply deletions
                if ids_to_delete:
                    coll.delete(ids=ids_to_delete)

                # Apply updates
                if ids_to_update:
                    coll.update(
                        ids=ids_to_update, metadatas=metas_to_update
                    )

            except Exception as exc:
                logger.warning(
                    "Learning decay skipped collection '%s': %s",
                    coll_key, exc,
                )

        if decayed > 0 or pruned > 0 or backfilled > 0:
            logger.info(
                "Phase 16.2 learning decay: decayed %d, pruned %d, "
                "backfilled %d entries",
                decayed, pruned, backfilled,
            )

        return {
            "decayed": decayed,
            "pruned": pruned,
            "backfilled": backfilled,
        }

    def boost_validated_learning(
        self,
        doc_id: str,
        collection_key: str = "task_patterns",
        boost_increment: float = 0.1,
    ) -> Dict[str, Any]:
        """
        Validation boost: reset ``last_validated_at`` and increase
        ``decay_score`` for a knowledge entry that was successfully
        retrieved and used in a completed task.

        Called by KnowledgeService.boost_retrieved_learnings() after
        a task completes successfully.
        """
        from datetime import datetime

        try:
            coll = self.get_collection(collection_key)
            existing = coll.get(ids=[doc_id], include=["metadatas"])

            if not existing or not existing.get("ids") or not existing["ids"]:
                return {"boosted": False, "reason": "doc_not_found"}

            meta = (
                existing["metadatas"][0]
                if existing.get("metadatas")
                else {}
            )
            updated_meta = dict(meta)
            current_decay = float(updated_meta.get("decay_score", 1.0))
            updated_meta["decay_score"] = round(
                min(1.0, current_decay + boost_increment), 4
            )
            updated_meta["last_validated_at"] = (
                datetime.utcnow().isoformat()
            )
            updated_meta["validation_count"] = (
                int(updated_meta.get("validation_count", 0)) + 1
            )

            coll.update(ids=[doc_id], metadatas=[updated_meta])

            return {
                "boosted": True,
                "doc_id": doc_id,
                "new_decay_score": updated_meta["decay_score"],
            }

        except Exception as exc:
            logger.debug(
                "boost_validated_learning failed for %s: %s", doc_id, exc
            )
            return {"boosted": False, "error": str(exc)}

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------

    def health_check(self) -> Dict[str, Any]:
        """Return vector store health status."""
        try:
            heartbeat = self.client.heartbeat()
            return {
                "status": "healthy",
                "mode": "http" if self._host else "local",
                "host": self._host,
                "persist_directory": CHROMA_PERSIST_DIR,
                "collections": list(self._collections.keys()),
                "heartbeat": heartbeat,
            }
        except Exception as exc:  # noqa: BLE001
            return {
                "status": "unhealthy",
                "error": str(exc),
                "mode": "http" if self._host else "local",
                "persist_directory": CHROMA_PERSIST_DIR,
            }


# ---------------------------------------------------------------------------
# Module-level singleton — use get_vector_store() everywhere
# ---------------------------------------------------------------------------

# Module-level alias for the collection registry defined on VectorStore, so
# callers (e.g. reembed tooling) can import it without reaching into the class.
COLLECTIONS: Dict[str, str] = VectorStore.COLLECTIONS

_vector_store: Optional[VectorStore] = None


def get_vector_store() -> VectorStore:
    """
    Return the singleton VectorStore.

    Does NOT eagerly connect to ChromaDB. Construction only sets up the
    instance; the actual connection is deferred to ``VectorStore.client``
    (or ``initialize()`` called directly), which run on first real use.
    This keeps module-import time (e.g. ``skill_manager.py``'s module-level
    ``skill_manager = SkillManager()``) free of network calls, so importing
    the app doesn't hard-fail just because Chroma isn't reachable yet.
    """
    global _vector_store  # noqa: PLW0603
    if _vector_store is None:
        _vector_store = VectorStore()
    return _vector_store


# ---------------------------------------------------------------------------
# Lazy module-level alias — backward compatibility for message_bus and any
# other code that does:
#   from backend.core.vector_store import vector_store
#
# Python 3.7+ supports module __getattr__ so the singleton is only created
# on first *access*, never at import time.  This prevents the container from
# crashing during testing or startup races when ChromaDB isn't yet reachable.
# ---------------------------------------------------------------------------
def __getattr__(name: str):  # noqa: N807
    if name == "vector_store":
        return get_vector_store()
    raise AttributeError(f"module 'backend.core.vector_store' has no attribute {name!r}")


@contextmanager
def vector_db_session() -> Generator[VectorStore, None, None]:
    """Context manager for scoped vector DB operations."""
    store = get_vector_store()
    try:
        yield store
    except Exception:
        logger.exception("Vector DB session error")
        raise