"""``get_audio_cache_stats`` — stats about the audio-analysis cache table."""

import logging

try:
    from ..toolkit import AudioTool, register
except ImportError:
    from toolkit import AudioTool, register

logger = logging.getLogger("big-flavor-mcp")


@register
class GetAudioCacheStats(AudioTool):
    name = "get_audio_cache_stats"
    summary = "Get statistics about the audio analysis cache."
    description = "Get statistics about the audio analysis cache"
    takes_file = False
    takes_output = False
    params = []

    async def apply(self, ctx) -> dict:
        if not ctx.enable_audio_analysis:
            return {
                "error": "Audio analysis is disabled",
                "message": "Enable audio analysis when initializing the server"
            }

        if not ctx.db_manager:
            return {"error": "Database not initialized"}

        try:
            query = """
                SELECT
                    COUNT(*) as total_cached,
                    MAX(analyzed_at) as last_analysis
                FROM audio_analysis_cache
            """
            async with ctx.db_manager.pool.acquire() as conn:
                row = await conn.fetchrow(query)
                return {
                    "total_cached_analyses": row['total_cached'],
                    "last_analysis": row['last_analysis'].isoformat() if row['last_analysis'] else None,
                    "cache_type": "postgresql"
                }
        except Exception as e:
            logger.error(f"Error getting cache stats: {e}")
            return {"error": str(e)}
