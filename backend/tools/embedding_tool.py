"""
Embedding Tool — Generate and compare text embeddings.

Provides:
- Text embedding generation (multiple providers)
- Similarity comparison
- Semantic search over texts
- Clustering suggestions
"""

from typing import Dict, Any, List, Optional, Union
import numpy as np


class EmbeddingTool:
    """
    Generate and work with text embeddings.
    """
    
    TOOL_NAME = "embedding"
    TOOL_DESCRIPTION = """
    Generate vector embeddings for text and compute similarities.
    
    Providers:
    - local: sentence-transformers (default, no API cost)
    - openai: text-embedding-ada-002
    - cohere: embed models
    
    Operations:
    - embed: Convert text(s) to vectors
    - similarity: Compare two texts (cosine similarity)
    - search: Find most similar in a list
    - cluster: Group similar texts together
    
    Use for:
    - Semantic search in documents
    - Duplicate detection
    - Content recommendation
    - RAG (Retrieval Augmented Generation) pipelines
    """
    
    AUTHORIZED_TIERS = ["0xxxx", "1xxxx", "2xxxx", "3xxxx"]
    
    def __init__(self):
        self._local_model = None
        self._cache = {}  # Simple embedding cache
    
    async def execute(
        self,
        action: str,
        texts: Optional[Union[str, List[str]]] = None,
        text_a: Optional[str] = None,
        text_b: Optional[str] = None,
        query: Optional[str] = None,
        candidates: Optional[List[str]] = None,
        provider: str = "local",
        model: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """Execute embedding operation."""
        
        if action == "embed":
            if not texts:
                return {"success": False, "error": "texts required"}
            embeddings = await self._embed(texts if isinstance(texts, list) else [texts], provider, model)
            return {
                "success": True,
                "embeddings": embeddings,
                "dimensions": len(embeddings[0]) if embeddings else 0,
                "provider": provider
            }
        
        elif action == "similarity":
            if not text_a or not text_b:
                return {"success": False, "error": "text_a and text_b required"}
            sim = await self._similarity(text_a, text_b, provider, model)
            return {
                "success": True,
                "similarity": sim,
                "similarity_percent": round(sim * 100, 2)
            }
        
        elif action == "search":
            if not query or not candidates:
                return {"success": False, "error": "query and candidates required"}
            results = await self._search(query, candidates, provider, model, top_k=kwargs.get("top_k", 5))
            return {
                "success": True,
                "query": query,
                "results": results
            }
        
        elif action == "cluster":
            if not texts or not isinstance(texts, list):
                return {"success": False, "error": "texts list required"}
            clusters = await self._cluster(texts, provider, model, n_clusters=kwargs.get("n_clusters", 3))
            return {
                "success": True,
                "clusters": clusters
            }
        
        else:
            return {"success": False, "error": f"Unknown action: {action}"}
    
    async def _embed(self, texts: List[str], provider: str, model: Optional[str]) -> List[List[float]]:
        """Generate embeddings."""
        cache_key = f"{provider}:{model or 'default'}"
        
        # Check cache
        cached = []
        to_embed = []
        for text in texts:
            key = f"{cache_key}:{hash(text)}"
            if key in self._cache:
                cached.append((text, self._cache[key]))
            else:
                to_embed.append(text)
        
        # Generate new embeddings
        if to_embed:
            if provider == "local":
                new_embeddings = await self._embed_local(to_embed, model)
            elif provider == "openai":
                new_embeddings = await self._embed_openai(to_embed, model)
            else:
                raise ValueError(f"Unknown provider: {provider}")
            
            # Cache and combine
            for text, emb in zip(to_embed, new_embeddings):
                key = f"{cache_key}:{hash(text)}"
                self._cache[key] = emb
                cached.append((text, emb))
        
        # Return in original order
        result_map = {text: emb for text, emb in cached}
        return [result_map[text] for text in texts]
    
    async def _embed_local(self, texts: List[str], model: Optional[str]) -> List[List[float]]:
        """Generate embeddings using sentence-transformers."""
        try:
            from sentence_transformers import SentenceTransformer
            
            if self._local_model is None:
                from backend.core.config import settings
                model_name = model or settings.EMBEDDING_MODEL
                self._local_model = SentenceTransformer(model_name)
            
            embeddings = self._local_model.encode(texts, convert_to_numpy=True)
            return embeddings.tolist()
        except ImportError:
            raise RuntimeError("sentence-transformers not installed. Run: pip install sentence-transformers")
    
    async def _embed_openai(self, texts: List[str], model: Optional[str]) -> List[List[float]]:
        """Generate embeddings using OpenAI API."""
        import openai
        
        model = model or "text-embedding-ada-002"
        
        # Batch in chunks of 100
        all_embeddings = []
        for i in range(0, len(texts), 100):
            batch = texts[i:i+100]
            response = await openai.Embedding.acreate(
                input=batch,
                model=model
            )
            all_embeddings.extend([d["embedding"] for d in response["data"]])
        
        return all_embeddings
    
    async def _similarity(self, text_a: str, text_b: str, provider: str, model: Optional[str]) -> float:
        """Compute cosine similarity."""
        embeddings = await self._embed([text_a, text_b], provider, model)
        vec_a = np.array(embeddings[0])
        vec_b = np.array(embeddings[1])
        
        # Cosine similarity
        dot = np.dot(vec_a, vec_b)
        norm_a = np.linalg.norm(vec_a)
        norm_b = np.linalg.norm(vec_b)
        
        return float(dot / (norm_a * norm_b)) if norm_a > 0 and norm_b > 0 else 0.0
    
    async def _search(
        self,
        query: str,
        candidates: List[str],
        provider: str,
        model: Optional[str],
        top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """Semantic search."""
        # Embed query and candidates
        all_texts = [query] + candidates
        embeddings = await self._embed(all_texts, provider, model)
        
        query_vec = np.array(embeddings[0])
        candidate_vecs = [np.array(e) for e in embeddings[1:]]
        
        # Compute similarities
        similarities = []
        for i, vec in enumerate(candidate_vecs):
            dot = np.dot(query_vec, vec)
            norm_q = np.linalg.norm(query_vec)
            norm_c = np.linalg.norm(vec)
            sim = dot / (norm_q * norm_c) if norm_q > 0 and norm_c > 0 else 0.0
            similarities.append((candidates[i], float(sim)))
        
        # Sort and return top_k
        similarities.sort(key=lambda x: x[1], reverse=True)
        
        return [
            {"text": text, "score": score, "rank": i+1}
            for i, (text, score) in enumerate(similarities[:top_k])
        ]
    
    async def _cluster(
        self,
        texts: List[str],
        provider: str,
        model: Optional[str],
        n_clusters: int = 3
    ) -> List[Dict[str, Any]]:
        """Cluster texts by similarity."""
        from sklearn.cluster import KMeans
        
        embeddings = await self._embed(texts, provider, model)
        X = np.array(embeddings)
        
        # Cluster
        kmeans = KMeans(n_clusters=min(n_clusters, len(texts)), random_state=42)
        labels = kmeans.fit_predict(X)
        
        # Organize results
        clusters = {}
        for i, label in enumerate(labels):
            if label not in clusters:
                clusters[label] = []
            clusters[label].append({
                "text": texts[i],
                "index": i
            })
        
        return [
            {
                "cluster_id": int(k),
                "size": len(v),
                "items": v,
                "centroid": kmeans.cluster_centers_[k].tolist()[:10]  # Truncated
            }
            for k, v in sorted(clusters.items())
        ]


embedding_tool = EmbeddingTool()