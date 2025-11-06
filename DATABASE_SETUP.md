# PostgreSQL with pgvector Setup

This directory contains the configuration for running PostgreSQL with the pgvector extension for vector similarity search and RAG (Retrieval-Augmented Generation).

## Prerequisites

### Install Docker Desktop

1. **Download Docker Desktop for Windows:**
   - Visit: https://www.docker.com/products/docker-desktop/
   - Download and install Docker Desktop

2. **Start Docker Desktop:**
   - Launch Docker Desktop from the Start menu
   - Wait for Docker to fully start (the whale icon in the system tray should be stable)

3. **Verify Docker is running:**
   ```powershell
   docker --version
   docker compose version
   ```

## Quick Start

Once Docker is installed and running:

```powershell
# Run the automated setup script
.\setup-database.ps1
```

This script will:
- Start PostgreSQL with pgvector in Docker
- Wait for the database to be ready
- Install the Python `asyncpg` dependency
- Display connection details

## Manual Setup

If you prefer to run commands manually:

```powershell
# Start the database
docker compose up -d

# Wait 10 seconds for database to initialize
Start-Sleep -Seconds 10

# Check status
docker compose ps

# Install Python dependency
pip install asyncpg
```

## Database Connection Details

- **Host:** localhost
- **Port:** 5432
- **Database:** bigflavor
- **User:** bigflavor
- **Password:** bigflavor_dev_pass

## Testing the Connection

```powershell
python db_example.py
```

## Database Schema

The database includes:

### Tables
- **songs** - Song metadata (title, genre, tempo, key, etc.)
- **audio_analysis** - Detailed audio analysis results
- **song_embeddings** - Vector embeddings for song similarity search
- **documents** - Document chunks with embeddings for RAG

### Features
- **pgvector extension** - For vector similarity search
- **IVFFlat indexes** - For fast similarity queries
- **Automatic timestamps** - created_at/updated_at tracking
- **Foreign key constraints** - Data integrity

## Common Commands

```powershell
# View logs
docker compose logs -f postgres

# Stop database
docker compose down

# Stop and remove volumes (delete all data)
docker compose down -v

# Restart database
docker compose restart

# Connect with psql
docker compose exec postgres psql -U bigflavor -d bigflavor
```

## Using the Database in Python

```python
from database import DatabaseManager
import asyncio

async def main():
    db = DatabaseManager()
    await db.connect()
    
    try:
        # Insert a song
        song = {
            'id': 'song_001',
            'title': 'Summer Groove',
            'genre': 'Rock',
            'tempo_bpm': 128.0,
            'key': 'C Major',
            'duration_seconds': 245,
            'energy': 'high',
            'mood': 'upbeat',
            'audio_quality': 'good',
            'audio_url': 'https://example.com/song.mp3'
        }
        await db.insert_song(song)
        
        # Get all songs
        songs = await db.get_all_songs()
        print(f"Found {len(songs)} songs")
        
        # Search songs
        rock_songs = await db.search_songs(genre='Rock')
        print(f"Found {len(rock_songs)} rock songs")
        
    finally:
        await db.close()

asyncio.run(main())
```

## Vector Search (RAG)

```python
# Search for similar songs using embeddings
similar_songs = await db.search_similar_songs(
    query_embedding=[0.1, 0.2, ...],  # Your embedding vector
    limit=5
)

# Search documents
similar_docs = await db.search_documents(
    query_embedding=[0.1, 0.2, ...],
    limit=5
)
```

## Troubleshooting

### Docker not found
- Install Docker Desktop: https://www.docker.com/products/docker-desktop/
- Make sure Docker Desktop is running

### Port 5432 already in use
- Another PostgreSQL instance is running
- Stop it or change the port in `docker-compose.yml`

### Database connection refused
- Wait a few more seconds for the database to start
- Check logs: `docker compose logs postgres`

### Permission errors on Windows
- Make sure Docker Desktop has permission to access your drive
- Check Docker Desktop Settings → Resources → File Sharing

## Next Steps

1. **Migrate existing cache data** - Import your `audio_analysis_cache.json` into the database
2. **Update audio analyzer** - Modify `pre_analyze_audio.py` to store results in PostgreSQL
3. **Implement RAG** - Add embedding generation and vector search
4. **Add authentication** - Secure the database connection

## Files

- `docker-compose.yml` - Docker Compose configuration
- `sql/init/01-init-schema.sql` - Database schema initialization
- `database.py` - Python database manager class
- `db_example.py` - Example usage script
- `setup-database.ps1` - Automated setup script
