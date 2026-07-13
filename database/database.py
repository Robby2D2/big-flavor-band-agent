"""
Database manager for PostgreSQL with pgvector
"""

import logging
import os
from typing import List, Dict, Any, Optional
from datetime import datetime, date
import asyncpg
import json
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

logger = logging.getLogger("database")

# The dev-only password default is intentionally NOT used outside an explicit dev
# context, so a real deploy that forgets DB_PASSWORD fails loudly instead of
# silently connecting with a known dev credential.
_DEV_PASSWORD_DEFAULT = "bigflavor_dev_pass"


def _is_dev_environment() -> bool:
    return os.getenv("APP_ENV", "production").strip().lower() in {"dev", "development"}


def _resolve_db_password() -> str:
    """Resolve the DB password from env, failing fast when it is missing in a
    non-dev environment instead of falling back to a hardcoded dev credential."""
    password = os.getenv("DB_PASSWORD")
    if password:
        return password
    if _is_dev_environment():
        return _DEV_PASSWORD_DEFAULT
    raise RuntimeError(
        "DB_PASSWORD is not set. Refusing to start with the hardcoded dev "
        "default outside a development environment. Set DB_PASSWORD, or set "
        "APP_ENV=development to allow the dev default."
    )


def _parse_recorded_on(value: Any) -> Optional[date]:
    """Coerce a scraped recorded-on value into a date for the DATE column.

    Accepts a date/datetime, an ISO 'YYYY-MM-DD' string, or the scraper's
    'M/D/YY' format (interpreted as 20YY). Returns None for empty or
    unparseable input so a bad value never blocks a song insert.
    """
    if not value:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        pass
    parts = text.split("/")
    if len(parts) == 3:
        try:
            month, day, yy = (int(p) for p in parts)
            return date(2000 + yy, month, day)
        except ValueError:
            pass
    logger.warning(f"Unparseable recorded_on value, storing NULL: {value!r}")
    return None


class DatabaseManager:
    """Manage PostgreSQL database connections and operations."""
    
    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        database: Optional[str] = None,
        user: Optional[str] = None,
        password: Optional[str] = None
    ):
        # Use environment variables as defaults, fall back to provided values
        self.host = host or os.getenv("DB_HOST", "localhost")
        self.port = port or int(os.getenv("DB_PORT", "5432"))
        self.database = database or os.getenv("DB_NAME", "bigflavor")
        self.user = user or os.getenv("DB_USER", "bigflavor")
        self.password = password or _resolve_db_password()
        self.pool: Optional[asyncpg.Pool] = None
    
    async def connect(self):
        """Create database connection pool."""
        self.pool = await asyncpg.create_pool(
            host=self.host,
            port=self.port,
            database=self.database,
            user=self.user,
            password=self.password,
            min_size=2,
            max_size=10
        )
        logger.info("Database connection pool created")
    
    async def close(self):
        """Close database connection pool."""
        if self.pool:
            await self.pool.close()
            logger.info("Database connection pool closed")
    
    # Song operations
    async def insert_song(self, song: Dict[str, Any]) -> int:
        """Insert or update a song. Returns song ID as integer."""
        query = """
            INSERT INTO songs (
                id, title, genre, tempo_bpm, key, duration_seconds,
                energy, mood, recording_date, audio_quality, audio_url,
                session, recorded_on
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
            ON CONFLICT (id) DO UPDATE SET
                title = EXCLUDED.title,
                genre = EXCLUDED.genre,
                tempo_bpm = EXCLUDED.tempo_bpm,
                key = EXCLUDED.key,
                duration_seconds = EXCLUDED.duration_seconds,
                energy = EXCLUDED.energy,
                mood = EXCLUDED.mood,
                recording_date = EXCLUDED.recording_date,
                audio_quality = EXCLUDED.audio_quality,
                audio_url = EXCLUDED.audio_url,
                -- COALESCE so a re-scrape that lacks these doesn't wipe values
                -- already present (e.g. the back-filled session/recorded_on).
                session = COALESCE(EXCLUDED.session, songs.session),
                recorded_on = COALESCE(EXCLUDED.recorded_on, songs.recorded_on),
                updated_at = CURRENT_TIMESTAMP
            RETURNING id
        """
        
        # Convert song ID to integer if it's a string
        song_id = song['id']
        if isinstance(song_id, str):
            try:
                song_id = int(song_id)
            except ValueError:
                raise ValueError(f"Song ID must be numeric, got: {song_id}")
        
        async with self.pool.acquire() as conn:
            song_id = await conn.fetchval(
                query,
                song_id,
                song['title'],
                song.get('genre'),
                song.get('tempo_bpm'),
                song.get('key'),
                song.get('duration_seconds'),
                song.get('energy'),
                song.get('mood'),
                song.get('recording_date'),
                song.get('audio_quality'),
                song.get('audio_url'),
                song.get('session'),
                _parse_recorded_on(song.get('recorded_on'))
            )
        
        logger.info(f"Inserted/updated song: {song_id}")
        return song_id
    
    async def get_song(self, song_id: int) -> Optional[Dict[str, Any]]:
        """Get a song by ID (integer)."""
        query = "SELECT * FROM songs WHERE id = $1"
        
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, song_id)
        
        return dict(row) if row else None
    
    async def get_all_songs(self) -> List[Dict[str, Any]]:
        """Get all songs."""
        query = "SELECT * FROM songs ORDER BY title"
        
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query)
        
        return [dict(row) for row in rows]
    
    async def get_all_song_ids(self) -> set:
        """Get all song IDs in the database."""
        query = "SELECT id FROM songs"
        
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query)
        
        return {row['id'] for row in rows}
    
    async def search_songs(
        self,
        genre: Optional[str] = None,
        min_tempo: Optional[float] = None,
        max_tempo: Optional[float] = None,
        energy: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Search songs with filters."""
        conditions = []
        params = []
        param_idx = 1
        
        if genre:
            conditions.append(f"genre = ${param_idx}")
            params.append(genre)
            param_idx += 1
        
        if min_tempo is not None:
            conditions.append(f"tempo_bpm >= ${param_idx}")
            params.append(min_tempo)
            param_idx += 1
        
        if max_tempo is not None:
            conditions.append(f"tempo_bpm <= ${param_idx}")
            params.append(max_tempo)
            param_idx += 1
        
        if energy:
            conditions.append(f"energy = ${param_idx}")
            params.append(energy)
            param_idx += 1
        
        where_clause = " AND ".join(conditions) if conditions else "1=1"
        query = f"SELECT * FROM songs WHERE {where_clause} ORDER BY title"
        
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, *params)
        
        return [dict(row) for row in rows]
    
    # User operations
    async def upsert_user(
        self,
        user_id: str,
        email: str,
        name: str,
        picture: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Create a user (default role 'listener') or update an existing one.

        Returns the resulting user row, or None if no row was returned.
        """
        query = """
            INSERT INTO users (id, email, name, picture, role, created_at, updated_at)
            VALUES ($1, $2, $3, $4, 'listener', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT (id) DO UPDATE
            SET email = EXCLUDED.email,
                name = EXCLUDED.name,
                picture = EXCLUDED.picture,
                updated_at = CURRENT_TIMESTAMP
            RETURNING id, email, name, picture, role, created_at, updated_at
        """

        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, user_id, email, name, picture)

        return dict(row) if row else None

    async def get_user_role(self, user_id: str) -> Optional[str]:
        """Get a user's role, or None if the user does not exist."""
        query = "SELECT role FROM users WHERE id = $1"

        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, user_id)

        return row['role'] if row else None

    async def list_users(self) -> List[Dict[str, Any]]:
        """List all users, newest first."""
        query = """
            SELECT id, email, name, picture, role, created_at, updated_at
            FROM users
            ORDER BY created_at DESC
        """

        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query)

        return [dict(row) for row in rows]

    async def set_user_role(
        self,
        user_id: str,
        role: str
    ) -> Optional[Dict[str, Any]]:
        """Update a user's role.

        Returns the updated user row, or None if the user does not exist.
        """
        query = """
            UPDATE users
            SET role = $1, updated_at = CURRENT_TIMESTAMP
            WHERE id = $2
            RETURNING id, email, name, role, updated_at
        """

        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, role, user_id)

        return dict(row) if row else None

    async def get_song_lyrics(self, song_id: int) -> Optional[str]:
        """Get the transcribed lyrics for a song, or None if not available."""
        query = """
            SELECT content as lyrics
            FROM text_embeddings
            WHERE song_id = $1 AND content_type = 'lyrics'
        """

        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, song_id)

        return row['lyrics'] if row else None

    # Song version operations (issue #30 — cleanup audition/publish loop)
    async def ensure_song_versions_table(self) -> None:
        """Create the song_versions table if missing. Idempotent.

        Mirrors how radio_state is ensured at startup: the canonical schema lives
        in database/sql/migrations/07-create-song-versions-table.sql, and this
        method applies the same idempotent DDL so the table exists without a
        manual migration step.
        """
        ddl = """
            CREATE TABLE IF NOT EXISTS song_versions (
                id SERIAL PRIMARY KEY,
                song_id INTEGER NOT NULL REFERENCES songs(id) ON DELETE CASCADE,
                audio_path TEXT NOT NULL,
                label VARCHAR(32) NOT NULL DEFAULT 'cleaned',
                name VARCHAR(120),
                is_published BOOLEAN NOT NULL DEFAULT FALSE,
                metrics JSONB,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (audio_path)
            );
            -- Older deployments created the table before the name column existed
            -- (issue #43); add it idempotently so this stays a single source of DDL.
            ALTER TABLE song_versions ADD COLUMN IF NOT EXISTS name VARCHAR(120);
            CREATE UNIQUE INDEX IF NOT EXISTS idx_song_versions_one_published
                ON song_versions (song_id) WHERE is_published;
            CREATE INDEX IF NOT EXISTS idx_song_versions_song_id
                ON song_versions (song_id);
        """
        async with self.pool.acquire() as conn:
            await conn.execute(ddl)
        logger.info("song_versions table ensured")

    async def ensure_original_version(
        self, song_id: int, audio_path: str
    ) -> Dict[str, Any]:
        """Seed the song's 'original' version row (published) if it has none yet.

        Idempotent: returns the existing original if present, otherwise inserts a
        published 'original' row pointing at the catalog audio file. This is the
        baseline every later cleaned version is auditioned against.
        """
        async with self.pool.acquire() as conn:
            existing = await conn.fetchrow(
                "SELECT * FROM song_versions WHERE song_id = $1 AND label = 'original'",
                song_id,
            )
            if existing:
                return dict(existing)

            # Only make the original the published version if nothing else is.
            has_published = await conn.fetchval(
                "SELECT EXISTS(SELECT 1 FROM song_versions WHERE song_id = $1 AND is_published)",
                song_id,
            )
            row = await conn.fetchrow(
                """
                INSERT INTO song_versions (song_id, audio_path, label, is_published)
                VALUES ($1, $2, 'original', $3)
                ON CONFLICT (audio_path) DO UPDATE SET song_id = EXCLUDED.song_id
                RETURNING *
                """,
                song_id,
                audio_path,
                not has_published,
            )
        return dict(row)

    async def list_song_versions(self, song_id: int) -> List[Dict[str, Any]]:
        """Return all versions for a song, newest first."""
        query = """
            SELECT id, song_id, audio_path, label, name, is_published, metrics, created_at
            FROM song_versions
            WHERE song_id = $1
            ORDER BY created_at DESC
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, song_id)
        return [dict(row) for row in rows]

    async def get_song_version(self, version_id: int) -> Optional[Dict[str, Any]]:
        """Return a single version by id, or None."""
        query = "SELECT * FROM song_versions WHERE id = $1"
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, version_id)
        return dict(row) if row else None

    async def rename_song_version(
        self, version_id: int, name: str
    ) -> Optional[Dict[str, Any]]:
        """Set a version's display name. Returns the updated row, or None if absent."""
        query = "UPDATE song_versions SET name = $2 WHERE id = $1 RETURNING *"
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, version_id, name)
        return dict(row) if row else None

    async def count_song_versions(self, song_id: int) -> int:
        """Return how many versions a song has."""
        query = "SELECT COUNT(*) FROM song_versions WHERE song_id = $1"
        async with self.pool.acquire() as conn:
            return int(await conn.fetchval(query, song_id))

    async def pick_fallback_version(
        self, song_id: int, exclude_version_id: int
    ) -> Optional[Dict[str, Any]]:
        """Choose which version should become default after the current one is deleted.

        Prefers the 'original' (so deleting a cleaned default reverts to the
        source); otherwise the most recently created remaining version. Returns
        None if no other version exists.
        """
        query = """
            SELECT * FROM song_versions
            WHERE song_id = $1 AND id <> $2
            ORDER BY (label = 'original') DESC, created_at DESC
            LIMIT 1
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, song_id, exclude_version_id)
        return dict(row) if row else None

    async def add_song_version(
        self,
        song_id: int,
        audio_path: str,
        label: str = "cleaned",
        metrics: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Insert a new (unpublished) version. Returns the inserted row."""
        query = """
            INSERT INTO song_versions (song_id, audio_path, label, is_published, metrics)
            VALUES ($1, $2, $3, FALSE, $4)
            ON CONFLICT (audio_path) DO UPDATE SET
                song_id = EXCLUDED.song_id,
                label = EXCLUDED.label,
                metrics = EXCLUDED.metrics
            RETURNING *
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                query,
                song_id,
                audio_path,
                label,
                json.dumps(metrics) if metrics is not None else None,
            )
        return dict(row)

    async def find_cleaned_version_by_dedup_key(
        self, song_id: int, dedup_key: str
    ) -> Optional[Dict[str, Any]]:
        """Find an existing auto-clean candidate matching a dedup key, or None.

        Used to replace (rather than duplicate) a prior auto-clean candidate when a
        producer re-runs Auto-Clean with identical steps/intensity for the same song
        (issue #47). The key is stored in the version's ``metrics`` JSON as
        ``dedup_key`` when the candidate is created.
        """
        query = """
            SELECT * FROM song_versions
            WHERE song_id = $1 AND label = 'cleaned' AND metrics ->> 'dedup_key' = $2
            ORDER BY created_at DESC
            LIMIT 1
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, song_id, dedup_key)
        return dict(row) if row else None

    async def replace_song_version_audio(
        self,
        version_id: int,
        audio_path: str,
        metrics: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Point an existing version at a freshly rendered file + refreshed metrics.

        Replaces an identical auto-clean candidate in place (issue #47): keeps the
        row id and publish state, only swapping its audio path and metrics. Returns
        the updated row, or None if the version no longer exists.
        """
        query = """
            UPDATE song_versions
            SET audio_path = $2, metrics = $3
            WHERE id = $1
            RETURNING *
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                query,
                version_id,
                audio_path,
                json.dumps(metrics) if metrics is not None else None,
            )
        return dict(row) if row else None

    async def publish_song_version(
        self, song_id: int, version_id: int
    ) -> Optional[Dict[str, Any]]:
        """Mark exactly one version published for a song (unpublishing the rest).

        Runs in a transaction so there is never a moment with zero or two
        published versions. Returns the newly published row, or None if the
        version doesn't belong to the song.
        """
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                owned = await conn.fetchval(
                    "SELECT EXISTS(SELECT 1 FROM song_versions WHERE id = $1 AND song_id = $2)",
                    version_id,
                    song_id,
                )
                if not owned:
                    return None
                await conn.execute(
                    "UPDATE song_versions SET is_published = FALSE WHERE song_id = $1 AND is_published",
                    song_id,
                )
                row = await conn.fetchrow(
                    "UPDATE song_versions SET is_published = TRUE WHERE id = $1 RETURNING *",
                    version_id,
                )
        return dict(row) if row else None

    async def get_published_version(self, song_id: int) -> Optional[Dict[str, Any]]:
        """Return the published version for a song, or None if none is published."""
        query = "SELECT * FROM song_versions WHERE song_id = $1 AND is_published"
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, song_id)
        return dict(row) if row else None

    async def get_song_ids_with_cleaned_versions(self) -> set:
        """Return the set of song_ids that already have a cleaned version.

        A song is "already cleaned" when it has any ``song_versions`` row whose
        label is not 'original' (i.e. a produced/cleaned take exists). The batch
        runner (issue #29) uses this in one bulk read to skip already-cleaned
        songs by default, instead of N+1 per-song lookups.
        """
        query = "SELECT DISTINCT song_id FROM song_versions WHERE label <> 'original'"
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query)
        return {row["song_id"] for row in rows}

    async def get_published_audio_paths(self) -> Dict[int, str]:
        """Return {song_id: audio_path} for every song that has a published version.

        Used to seed the published-version path override the radio/stream consult
        when resolving which file to serve.
        """
        query = "SELECT song_id, audio_path FROM song_versions WHERE is_published"
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query)
        return {row["song_id"]: row["audio_path"] for row in rows}

    async def delete_song_version(self, version_id: int) -> Optional[Dict[str, Any]]:
        """Delete a version by id. Returns the deleted row, or None if absent."""
        query = "DELETE FROM song_versions WHERE id = $1 RETURNING *"
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, version_id)
        return dict(row) if row else None

    # Stem separation operations (issue #67 — Demucs stem separation)
    async def ensure_song_stems_tables(self) -> None:
        """Create the song_stem_sets / song_stems tables if missing. Idempotent.

        Mirrors ensure_song_versions_table: the canonical schema lives in
        database/sql/migrations/09-create-song-stems-tables.sql, and this method
        applies the same idempotent DDL so the tables exist without a manual
        migration step.
        """
        ddl = """
            CREATE TABLE IF NOT EXISTS song_stem_sets (
                id SERIAL PRIMARY KEY,
                song_id INTEGER NOT NULL REFERENCES songs(id) ON DELETE CASCADE,
                source_version_id INTEGER REFERENCES song_versions(id) ON DELETE SET NULL,
                model VARCHAR(64) NOT NULL,
                status VARCHAR(16) NOT NULL DEFAULT 'queued',
                error TEXT,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_song_stem_sets_song_id
                ON song_stem_sets (song_id);
            CREATE TABLE IF NOT EXISTS song_stems (
                id SERIAL PRIMARY KEY,
                stem_set_id INTEGER NOT NULL REFERENCES song_stem_sets(id) ON DELETE CASCADE,
                name VARCHAR(32) NOT NULL,
                path TEXT NOT NULL,
                UNIQUE (stem_set_id, name)
            );
            CREATE INDEX IF NOT EXISTS idx_song_stems_stem_set_id
                ON song_stems (stem_set_id);
        """
        async with self.pool.acquire() as conn:
            await conn.execute(ddl)
        logger.info("song_stem_sets / song_stems tables ensured")

    async def create_stem_set(
        self, song_id: int, model: str, source_version_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """Insert a new stem set in the 'queued' state. Returns the inserted row."""
        query = """
            INSERT INTO song_stem_sets (song_id, source_version_id, model, status)
            VALUES ($1, $2, $3, 'queued')
            RETURNING *
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, song_id, source_version_id, model)
        return dict(row)

    async def set_stem_set_status(
        self, stem_set_id: int, status: str, error: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Update a stem set's job status (and failure reason). Returns the row."""
        query = """
            UPDATE song_stem_sets SET status = $2, error = $3
            WHERE id = $1 RETURNING *
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, stem_set_id, status, error)
        return dict(row) if row else None

    async def get_stem_set(self, stem_set_id: int) -> Optional[Dict[str, Any]]:
        """Return a single stem set by id, or None."""
        query = "SELECT * FROM song_stem_sets WHERE id = $1"
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, stem_set_id)
        return dict(row) if row else None

    async def list_stem_sets(self, song_id: int) -> List[Dict[str, Any]]:
        """Return all stem sets for a song, newest first."""
        query = """
            SELECT * FROM song_stem_sets
            WHERE song_id = $1
            ORDER BY created_at DESC
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, song_id)
        return [dict(row) for row in rows]

    async def add_stem(
        self, stem_set_id: int, name: str, path: str
    ) -> Dict[str, Any]:
        """Record one separated stem file for a stem set. Returns the inserted row."""
        query = """
            INSERT INTO song_stems (stem_set_id, name, path)
            VALUES ($1, $2, $3)
            ON CONFLICT (stem_set_id, name) DO UPDATE SET path = EXCLUDED.path
            RETURNING *
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, stem_set_id, name, path)
        return dict(row)

    async def list_stems(self, stem_set_id: int) -> List[Dict[str, Any]]:
        """Return all stems for a stem set, ordered by name."""
        query = "SELECT * FROM song_stems WHERE stem_set_id = $1 ORDER BY name"
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, stem_set_id)
        return [dict(row) for row in rows]

    async def get_stem(self, stem_id: int) -> Optional[Dict[str, Any]]:
        """Return a single stem by id, or None."""
        query = "SELECT * FROM song_stems WHERE id = $1"
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, stem_id)
        return dict(row) if row else None

    # Audio analysis operations
    async def insert_audio_analysis(self, analysis: Dict[str, Any]) -> int:
        """Insert or update audio analysis."""
        query = """
            INSERT INTO audio_analysis (
                song_id, audio_url, bpm, key, energy, danceability,
                valence, acousticness, instrumentalness, liveness, speechiness
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
            ON CONFLICT (audio_url) DO UPDATE SET
                song_id = EXCLUDED.song_id,
                bpm = EXCLUDED.bpm,
                key = EXCLUDED.key,
                energy = EXCLUDED.energy,
                danceability = EXCLUDED.danceability,
                valence = EXCLUDED.valence,
                acousticness = EXCLUDED.acousticness,
                instrumentalness = EXCLUDED.instrumentalness,
                liveness = EXCLUDED.liveness,
                speechiness = EXCLUDED.speechiness,
                analyzed_at = CURRENT_TIMESTAMP
            RETURNING id
        """
        
        async with self.pool.acquire() as conn:
            analysis_id = await conn.fetchval(
                query,
                analysis.get('song_id'),
                analysis['audio_url'],
                analysis.get('bpm'),
                analysis.get('key'),
                analysis.get('energy'),
                analysis.get('danceability'),
                analysis.get('valence'),
                analysis.get('acousticness'),
                analysis.get('instrumentalness'),
                analysis.get('liveness'),
                analysis.get('speechiness')
            )
        
        logger.info(f"Inserted/updated audio analysis: {analysis_id}")
        return analysis_id
    
    async def get_audio_analysis(self, song_id: int) -> Optional[Dict[str, Any]]:
        """Get audio analysis for a song."""
        query = "SELECT * FROM audio_analysis WHERE song_id = $1"
        
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, song_id)
        
        return dict(row) if row else None
    
    # Vector operations for RAG
    async def insert_embedding(
        self,
        song_id: int,
        content_type: str,
        content: str,
        embedding: List[float]
    ) -> int:
        """Insert a song embedding."""
        query = """
            INSERT INTO song_embeddings (song_id, content_type, content, embedding)
            VALUES ($1, $2, $3, $4)
            RETURNING id
        """
        
        async with self.pool.acquire() as conn:
            embedding_id = await conn.fetchval(
                query,
                song_id,
                content_type,
                content,
                embedding
            )
        
        return embedding_id
    
    async def search_similar_songs(
        self,
        query_embedding: List[float],
        limit: int = 5,
        content_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Search for similar songs using vector similarity."""
        type_filter = "AND content_type = $3" if content_type else ""
        query = f"""
            SELECT 
                se.song_id,
                se.content_type,
                se.content,
                s.title,
                s.genre,
                1 - (se.embedding <=> $1) as similarity
            FROM song_embeddings se
            JOIN songs s ON se.song_id = s.id
            WHERE 1=1 {type_filter}
            ORDER BY se.embedding <=> $1
            LIMIT $2
        """
        
        params = [query_embedding, limit]
        if content_type:
            params.append(content_type)
        
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, *params)
        
        return [dict(row) for row in rows]
    
    async def insert_document(
        self,
        source: str,
        content: str,
        metadata: Dict[str, Any],
        embedding: List[float]
    ) -> int:
        """Insert a document for RAG."""
        query = """
            INSERT INTO documents (source, content, metadata, embedding)
            VALUES ($1, $2, $3, $4)
            RETURNING id
        """
        
        async with self.pool.acquire() as conn:
            doc_id = await conn.fetchval(
                query,
                source,
                content,
                json.dumps(metadata),
                embedding
            )
        
        return doc_id
    
    async def search_documents(
        self,
        query_embedding: List[float],
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """Search documents using vector similarity."""
        query = """
            SELECT 
                id,
                source,
                content,
                metadata,
                1 - (embedding <=> $1) as similarity
            FROM documents
            ORDER BY embedding <=> $1
            LIMIT $2
        """
        
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, query_embedding, limit)
        
        return [dict(row) for row in rows]
