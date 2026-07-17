"""
Vector DB Tool — read from and write to the Agentium ChromaDB vector store.

Wraps the singleton VectorStore (backend.core.vector_store). Available to
every agent tier (0xxxx–6xxxx). Reads are allowed against all collections;
writes are restricted to WRITABLE_COLLECTIONS so immutable collections
(constitution, ethos, constitutional_skills, …) can never be mutated by an
agent.

A companion skill at backend/.agentium/skills/vector_db/SKILL.md documents
this tool and is indexed into ChromaDB by `make seed-skills`; the `help`
action and the tool description both point agents at that skill file.
"""

from typing import Any, Dict, List, Optional

from backend.core.vector_store import get_vector_store


SKILL_PATH = "backend/.agentium/skills/vector_db/SKILL.md"


class VectorDBTool:
    """Agent-facing interface to the shared ChromaDB vector store."""

    TOOL_NAME = "vector_db"

    # Collections an agent may upsert into. Immutable / governance-critical
    # collections are deliberately excluded.
    WRITABLE_COLLECTIONS: List[str] = [
        "council_memory",
        "task_patterns",
        "best_practices",
        "domain_knowledge",
        "sovereign_prefs",
        "audit_semantic",
    ]

    def __init__(self) -> None:
        self._store = None

    @property
    def store(self):
        if self._store is None:
            self._store = get_vector_store()
        return self._store

    async def execute(
        self,
        action: str,
        query: Optional[str] = None,
        collection: Optional[str] = None,
        collection_keys: Optional[List[str]] = None,
        n_results: int = 5,
        doc_id: Optional[str] = None,
        documents: Optional[List[str]] = None,
        metadatas: Optional[List[Dict[str, Any]]] = None,
        ids: Optional[List[str]] = None,
        filter_dict: Optional[Dict[str, Any]] = None,
        **_kwargs,
    ) -> Dict[str, Any]:
        """Dispatch a vector-store operation.

        Actions: query, get, add, list_collections, help.
        """
        if action == "query":
            return self._query(query, collection_keys or ([collection] if collection else None), n_results, filter_dict)
        if action == "get":
            return self._get(doc_id, collection)
        if action == "add":
            return self._add(collection, documents, metadatas, ids)
        if action == "list_collections":
            return self._list_collections()
        if action == "help":
            return self._help()
        return {"success": False, "error": f"Unknown action: {action}"}

    # ── Read ──────────────────────────────────────────────────────────────────

    def _query(self, query, collection_keys, n_results, filter_dict):
        if not query:
            return {"success": False, "error": "query is required for action 'query'"}
        keys = collection_keys or list(self.store.COLLECTIONS.keys())
        result = self.store.query_knowledge(
            query=query,
            collection_keys=keys,
            n_results=n_results,
            filter_dict=filter_dict,
        )
        matches = []
        if result and result.get("ids"):
            for i, doc_id in enumerate(result["ids"][0]):
                matches.append({
                    "id": doc_id,
                    "document": (result["documents"][0][i] if result.get("documents") else ""),
                    "metadata": (result["metadatas"][0][i] if result.get("metadatas") else {}),
                    "distance": (result["distances"][0][i] if result.get("distances") else 0.0),
                    "relevance_score": round(
                        max(0.0, 1.0 - (result["distances"][0][i] if result.get("distances") else 1.0)), 6
                    ),
                })
        return {"success": True, "query": query, "count": len(matches), "matches": matches}

    def _get(self, doc_id, collection):
        if not doc_id:
            return {"success": False, "error": "doc_id is required for action 'get'"}
        if not collection:
            return {"success": False, "error": "collection is required for action 'get'"}
        if collection not in self.store.COLLECTIONS:
            return {"success": False, "error": f"Unknown collection '{collection}'"}
        coll = self.store.get_collection(collection)
        got = coll.get(ids=[doc_id], include=["documents", "metadatas"])
        if not got or not got.get("ids"):
            return {"success": False, "error": f"doc_id '{doc_id}' not found in '{collection}'"}
        return {
            "success": True,
            "id": got["ids"][0],
            "document": got["documents"][0] if got.get("documents") else "",
            "metadata": got["metadatas"][0] if got.get("metadatas") else {},
        }

    def _list_collections(self):
        collections = dict(self.store.COLLECTIONS)
        paths = {k: SKILL_PATH for k in collections}
        writable = set(self.WRITABLE_COLLECTIONS)
        return {
            "success": True,
            "collections": collections,
            "writable_collections": [k for k in collections if k in writable],
            "paths": paths,
        }

    def _help(self):
        return {
            "success": True,
            "tool": self.TOOL_NAME,
            "skill_file": SKILL_PATH,
            "actions": {
                "query": "Semantic search. Params: query (str), collection (str|optional), collection_keys (list|optional), n_results (int=5), filter_dict (dict|optional).",
                "get": "Fetch one document by id. Params: doc_id (str), collection (str).",
                "add": "Upsert documents (writable collections only). Params: collection (str), documents (list[str]), metadatas (list[dict]|optional), ids (list[str]).",
                "list_collections": "List every collection key and which are agent-writable.",
                "help": "Show this message.",
            },
            "help": (
                "The 'vector_db' tool reads from and writes to the shared ChromaDB "
                "vector store used for collective agent memory (RAG). Full usage, "
                "worked examples, and the writable-collection allow-list are in the "
                "skill file at backend/.agentium/skills/vector_db/SKILL.md. That skill "
                "is indexed into ChromaDB via `make seed-skills`, so you can also "
                "retrieve it semantically by asking 'how do I use the vector DB tool'."
            ),
        }

    # ── Write ─────────────────────────────────────────────────────────────────

    def _add(self, collection, documents, metadatas, ids):
        if not collection:
            return {"success": False, "error": "collection is required for action 'add'"}
        if not documents:
            return {"success": False, "error": "documents (list[str]) is required for action 'add'"}
        if collection not in self.store.COLLECTIONS:
            return {"success": False, "error": f"Unknown collection '{collection}'"}
        if collection not in self.WRITABLE_COLLECTIONS:
            return {
                "success": False,
                "error": (
                    f"Collection '{collection}' is not writable by agents. "
                    f"Writable collections: {self.WRITABLE_COLLECTIONS}"
                ),
            }
        docs = documents if isinstance(documents, list) else [documents]
        if not ids:
            ids = [f"{collection}_{i}" for i in range(len(docs))]
        if metadatas is None:
            metadatas = [{} for _ in docs]
        coll = self.store.get_collection(collection)
        coll.upsert(documents=docs, metadatas=metadatas, ids=ids)
        return {
            "success": True,
            "collection": collection,
            "count": len(docs),
            "ids": ids,
        }


vector_db_tool = VectorDBTool()
