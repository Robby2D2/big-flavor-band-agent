"""
Reindex existing lyrics with real text embeddings.
Updates all text_embeddings entries that have placeholder embeddings ([0.0] * 384).
"""

import asyncio
import logging
from pathlib import Path
import sys

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from database import DatabaseManager
from src.rag.big_flavor_rag import SongRAGSystem

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("reindex-lyrics")


async def main():
    """Reindex all existing lyrics with real text embeddings."""
    
    db = DatabaseManager()
    await db.connect()
    
    # Initialize RAG system with text embedding model
    logger.info("Initializing RAG system with text embedding model...")
    rag = SongRAGSystem(db)
    
    if not rag.text_embedding_model:
        logger.error("Text embedding model not available. Cannot reindex lyrics.")
        return
    
    logger.info("Text embedding model loaded successfully")
    
    # Get all lyrics that need reindexing
    query = """
        SELECT 
            id,
            song_id,
            content,
            embedding
        FROM text_embeddings
        WHERE content_type = 'lyrics'
        ORDER BY song_id
    """
    
    async with db.pool.acquire() as conn:
        rows = await conn.fetch(query)
    
    total = len(rows)
    logger.info(f"Found {total} lyrics entries to check")
    
    if total == 0:
        logger.info("No lyrics found to reindex")
        return
    
    # Check how many have placeholder embeddings
    placeholder_count = 0
    to_reindex = []
    
    for row in rows:
        embedding_str = row['embedding']
        # Check if it's a placeholder (all zeros or contains only zeros/commas/brackets)
        # The placeholder looks like "[0,0,0,0,0,...]" or "[0.0,0.0,0.0,...]"
        if embedding_str:
            # Simple heuristic: if the string only contains [0.,] characters, it's likely a placeholder
            cleaned = embedding_str.replace('[', '').replace(']', '').replace(',', '').replace('0', '').replace('.', '').replace(' ', '')
            if len(cleaned) == 0:  # Only had brackets, zeros, dots, commas, spaces
                placeholder_count += 1
                to_reindex.append((row['id'], row['song_id'], row['content']))
    
    logger.info(f"Found {placeholder_count} lyrics with placeholder embeddings")
    
    if placeholder_count == 0:
        logger.info("All lyrics already have real embeddings!")
        return
    
    # Confirm before proceeding
    response = input(f"\nReindex {placeholder_count} lyrics entries? (y/n): ")
    if response.lower() != 'y':
        logger.info("Cancelled")
        return
    
    # Reindex each entry
    logger.info(f"\nStarting reindexing of {placeholder_count} lyrics...")
    success_count = 0
    failed_count = 0
    
    for idx, (entry_id, song_id, content) in enumerate(to_reindex, 1):
        try:
            # Generate real embedding
            embedding = rag.text_embedding_model.encode(content).tolist()
            
            # Update in database
            update_query = """
                UPDATE text_embeddings
                SET embedding = $1,
                    created_at = CURRENT_TIMESTAMP
                WHERE id = $2
            """
            
            async with db.pool.acquire() as conn:
                await conn.execute(update_query, str(embedding), entry_id)
            
            success_count += 1
            
            if idx % 10 == 0:
                logger.info(f"Progress: {idx}/{placeholder_count} ({idx/placeholder_count*100:.1f}%)")
                
        except Exception as e:
            logger.error(f"Failed to reindex song {song_id}: {e}")
            failed_count += 1
    
    # Summary
    logger.info("\n" + "="*70)
    logger.info("Reindexing Complete")
    logger.info("="*70)
    logger.info(f"Total processed: {placeholder_count}")
    logger.info(f"✓ Successful: {success_count}")
    logger.info(f"✗ Failed: {failed_count}")
    logger.info("\nLyrics embeddings are now ready for semantic search!")


if __name__ == "__main__":
    asyncio.run(main())
