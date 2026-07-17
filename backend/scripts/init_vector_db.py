#!/usr/bin/env python3
"""
Initialize ChromaDB with baseline knowledge.
Run once on system setup or after schema changes.
"""

import sys
import os

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.models.database import get_db_context
from backend.services.knowledge_service import get_knowledge_service
from backend.core.vector_store import get_vector_store

def main():
    """Initialize vector database from PostgreSQL."""
    print("🧠 Initializing Agentium Vector Database...")
    
    # Ensure vector store directory exists
    vector_store = get_vector_store()
    vector_store.initialize()
    
    print(f"✅ ChromaDB initialized at: {vector_store.client.settings.persist_directory}")
    
    # Embed existing knowledge
    with get_db_context() as db:
        knowledge_svc = get_knowledge_service()
        stats = knowledge_svc.initialize_knowledge_base(db)
        
        print(f"\\n📚 Knowledge Base Stats:")
        print(f"   Constitution: {stats['constitution_embedded']}")
    
    # Health check
    health = vector_store.health_check()
    print(f"\\n💚 Vector Store Health: {health['status']}")
    print(f"   Collections: {health['collections']}")
    
    print("\\n✅ Initialization complete!")
    return 0

if __name__ == "__main__":
    sys.exit(main())