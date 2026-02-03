"""
Vector Store configuration for Agentium.
ChromaDB-backed RAG infrastructure for collective agent memory.
"""

import os
from typing import Optional, List, Dict, Any, Generator
from contextlib import contextmanager
import chromadb
from chromadb.config import Settings
from chromadb.api.types import QueryResult, EmbeddingFunction
import numpy as np
from sentence_transformers import SentenceTransformer

# Configuration
CHROMA_PERSIST_DIR = os.getenv("CHROMA_PERSIST_DIR", "./chroma_data")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
CHROMA_HOST = os.getenv("CHROMA_HOST", None)  # For server mode
CHROMA_PORT = int(os.getenv("CHROMA_PORT", "8000"))

class AgentiumEmbeddingFunction(EmbeddingFunction):
    """Custom embedding function using sentence-transformers."""
    
    def __init__(self, model_name: str = None):
        self.model_name = model_name or EMBEDDING_MODEL
        self._model = None
    
    @property
    def model(self):
        """Lazy load model."""
        if self._model is None:
            self._model = SentenceTransformer(self.model_name)
        return self._model
    
    def __call__(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for texts."""
        embeddings = self.model.encode(texts, convert_to_numpy=True)
        return embeddings.tolist()

class VectorStore:
    """
    ChromaDB wrapper for Agentium.
    Provides tiered collections for different knowledge types.
    """
    
    # Collection names match agent hierarchy
    COLLECTIONS = {
        "constitution": "supreme_law",           # Constitutional articles
        "ethos": "agent_ethos",                  # Individual agent ethos
        "council_memory": "council_knowledge",   # Council deliberations
        "task_patterns": "execution_patterns",   # Successful execution patterns
        "audit_semantic": "audit_history",       # Semantic search of audits
        "sovereign_prefs": "sovereign_memory",   # User preferences/memories
    }
    
    def __init__(self):
        self._client: Optional[chromadb.Client] = None
        self._embedding_fn = AgentiumEmbeddingFunction()
        self._collections: Dict[str, chromadb.Collection] = {}
    
    def initialize(self) -> chromadb.Client:
        """Initialize ChromaDB client (persistent mode)."""
        if self._client is None:
            # Ensure directory exists
            os.makedirs(CHROMA_PERSIST_DIR, exist_ok=True)
            
            settings = Settings(
                chroma_db_impl="duckdb+parquet",
                persist_directory=CHROMA_PERSIST_DIR,
                anonymized_telemetry=False
            )
            
            self._client = chromadb.Client(settings)
            
            # Pre-create or get collections
            for key, name in self.COLLECTIONS.items():
                try:
                    self._collections[key] = self._client.get_or_create_collection(
                        name=name,
                        embedding_function=self._embedding_fn
                    )
                except Exception as e:
                    print(f"Warning: Could not create collection {name}: {e}")
        
        return self._client
    
    @property
    def client(self) -> chromadb.Client:
        """Get or initialize client."""
        if self._client is None:
            self.initialize()
        return self._client
    
    def get_collection(self, collection_key: str) -> chromadb.Collection:
        """Get a collection by key."""
        if collection_key not in self.COLLECTIONS:
            raise ValueError(f"Unknown collection: {collection_key}")
        
        if collection_key not in self._collections:
            name = self.COLLECTIONS[collection_key]
            self._collections[collection_key] = self.client.get_or_create_collection(
                name=name,
                embedding_function=self._embedding_fn
            )
        
        return self._collections[collection_key]
    
    def add_constitution_article(self, 
                                  article_id: str, 
                                  content: str, 
                                  metadata: Dict[str, Any]):
        """Store constitutional article for RAG retrieval."""
        collection = self.get_collection("constitution")
        collection.add(
            documents=[content],
            metadatas=[{
                **metadata,
                "type": "constitution_article",
                "article_id": article_id,
                "document_type": "supreme_law",
                "immutable": True
            }],
            ids=[f"const_{article_id}"]
        )
    
    def add_ethos(self,
                  agentium_id: str,
                  ethos_content: str,
                  agent_type: str,
                  verified_by: str = None):
        """Store agent ethos semantics."""
        collection = self.get_collection("ethos")
        collection.add(
            documents=[ethos_content],
            metadatas=[{
                "agentium_id": agentium_id,
                "agent_type": agent_type,
                "verified_by": verified_by,
                "type": "ethos",
                "document_type": "behavioral_rules"
            }],
            ids=[f"ethos_{agentium_id}"]
        )
    
    def add_execution_pattern(self,
                             pattern_id: str,
                             description: str,
                             success_rate: float,
                             task_type: str,
                             tools_used: List[str] = None):
        """Store successful execution patterns for future RAG."""
        collection = self.get_collection("task_patterns")
        collection.add(
            documents=[description],
            metadatas=[{
                "pattern_id": pattern_id,
                "success_rate": success_rate,
                "task_type": task_type,
                "tools_used": json.dumps(tools_used or []),
                "type": "execution_pattern",
                "document_type": "learned_behavior"
            }],
            ids=[f"pattern_{pattern_id}"]
        )
    
    def query_knowledge(self,
                       query: str,
                       collection_keys: List[str] = None,
                       n_results: int = 5,
                       filter_dict: Dict[str, Any] = None) -> QueryResult:
        """
        Query across knowledge collections.
        If no collections specified, searches all.
        """
        collection_keys = collection_keys or list(self.COLLECTIONS.keys())
        
        results = []
        for key in collection_keys:
            try:
                collection = self.get_collection(key)
                result = collection.query(
                    query_texts=[query],
                    n_results=n_results,
                    where=filter_dict
                )
                results.append(result)
            except Exception as e:
                # Log but don't fail if one collection is down
                print(f"Query failed for {key}: {e}")
        
        # Merge results (simple concatenation for now, could be smarter)
        return self._merge_results(results, n_results)
    
    def query_constitution(self, query: str, n_results: int = 3) -> QueryResult:
        """Query specifically constitutional content."""
        collection = self.get_collection("constitution")
        return collection.query(
            query_texts=[query],
            n_results=n_results,
            where={"document_type": "supreme_law"}
        )
    
    def query_hierarchical_context(self,
                                   agent_type: str,
                                   task_description: str,
                                   n_results: int = 5) -> Dict[str, QueryResult]:
        """
        Get hierarchical context: Constitution + relevant Ethos + patterns.
        
        Tier 0 (Head): Constitution only
        Tier 1 (Council): Constitution + their specific ethos  
        Tier 2 (Lead): Constitution + Council deliberations + their ethos
        Tier 3 (Task): Task patterns + Lead coordination + basic constraints
        """
        context = {}
        
        # All tiers get Constitution as grounding
        context["constitution"] = self.query_constitution(task_description, n_results=2)
        
        if agent_type == "head_of_council":
            # Head needs supreme law only
            pass
        elif agent_type == "council_member":
            # Council needs deliberation history
            context["council_memory"] = self.get_collection("council_memory").query(
                query_texts=[task_description],
                n_results=n_results
            )
        elif agent_type == "lead_agent":
            # Leads need patterns
            context["task_patterns"] = self.get_collection("task_patterns").query(
                query_texts=[task_description],
                n_results=n_results
            )
        elif agent_type == "task_agent":
            # Task agents need execution patterns
            context["task_patterns"] = self.get_collection("task_patterns").query(
                query_texts=[task_description],
                n_results=n_results,
                where={"type": "execution_pattern"}
            )
        
        return context
    
    def _merge_results(self, results: List[QueryResult], n_results: int) -> QueryResult:
        """Merge multiple query results, deduplicate by ID."""
        seen_ids = set()
        merged = {
            "documents": [[]],
            "metadatas": [[]],
            "distances": [[]],
            "ids": [[]]
        }
        
        for result in results:
            if not result['ids']:
                continue
            for i, doc_id in enumerate(result['ids'][0]):
                if doc_id not in seen_ids:
                    seen_ids.add(doc_id)
                    merged["ids"][0].append(doc_id)
                    merged["documents"][0].append(result["documents"][0][i] if result["documents"] else "")
                    merged["metadatas"][0].append(result["metadatas"][0][i] if result["metadatas"] else {})
                    merged["distances"][0].append(result["distances"][0][i] if result["distances"] else 0.0)
                    
                    if len(seen_ids) >= n_results:
                        break
        
        return merged
    
    def health_check(self) -> Dict[str, Any]:
        """Check vector store health."""
        try:
            heartbeat = self.client.heartbeat()
            return {
                "status": "healthy",
                "persist_directory": CHROMA_PERSIST_DIR,
                "collections": list(self._collections.keys()),
                "heartbeat": heartbeat
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e),
                "persist_directory": CHROMA_PERSIST_DIR
            }


# Global singleton instance
vector_store = VectorStore()


def get_vector_store() -> VectorStore:
    """Get initialized vector store instance."""
    if vector_store._client is None:
        vector_store.initialize()
    return vector_store


@contextmanager
def vector_db_session() -> Generator[VectorStore, None, None]:
    """Context manager for vector DB operations."""
    store = get_vector_store()
    try:
        yield store
    except Exception as e:
        # Log error but don't close (persistent connection)
        print(f"Vector DB session error: {e}")
        raise