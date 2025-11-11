"""Quick test for text embedding model initialization"""
import asyncio
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.rag.big_flavor_rag import SongRAGSystem
from database import DatabaseManager

async def test():
    db = DatabaseManager()
    await db.connect()
    
    print("Initializing RAG system...")
    rag = SongRAGSystem(db)
    
    print(f"Text embedding model loaded: {rag.text_embedding_model is not None}")
    
    if rag.text_embedding_model:
        # Test encoding a query
        test_query = "songs about hippies"
        print(f"\nTesting query: '{test_query}'")
        embedding = rag.text_embedding_model.encode(test_query)
        print(f"Embedding shape: {embedding.shape}")
        print(f"Embedding type: {type(embedding)}")
        print(f"First 5 values: {embedding[:5]}")
    
    await db.disconnect()
    print("\nTest complete!")

if __name__ == "__main__":
    asyncio.run(test())
