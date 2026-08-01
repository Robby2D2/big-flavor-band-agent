"""``analyze_audio`` — cached tempo/key/energy/spectral feature extraction."""

import logging

try:
    from ..toolkit import AudioTool, register
    from ..audio_io import LIBROSA_AVAILABLE
    from ..analysis import perform_audio_analysis
except ImportError:
    from toolkit import AudioTool, register
    from audio_io import LIBROSA_AVAILABLE
    from analysis import perform_audio_analysis

logger = logging.getLogger("big-flavor-mcp")


@register
class AnalyzeAudio(AudioTool):
    name = "analyze_audio"
    summary = "Extract tempo, key, beats, and other audio features."
    description = "Extract tempo, key, beats, and other audio features from an audio file"
    takes_output = False
    params = []

    async def apply(self, ctx, file_path: str) -> dict:
        """Analyze an audio file, using the PostgreSQL cache when available."""
        if not ctx.enable_audio_analysis or not LIBROSA_AVAILABLE:
            return {
                "error": "Audio analysis is disabled or librosa not available",
                "message": "Enable audio analysis and install librosa"
            }

        try:
            file_hash = ctx.file_hash(file_path)

            # Check database cache
            cached_analysis = await ctx.get_cached_analysis(file_path, file_hash)
            if cached_analysis:
                logger.info(f"Using cached analysis for {file_path}")
                return {
                    "file_path": file_path,
                    "analysis": cached_analysis,
                    "status": "success",
                    "cached": True
                }

            # Perform fresh analysis
            logger.info(f"Analyzing audio file: {file_path}")
            analysis = perform_audio_analysis(file_path)

            # Save to database cache
            await ctx.save_analysis_to_cache(file_path, file_hash, analysis)

            return {
                "file_path": file_path,
                "analysis": analysis,
                "status": "success",
                "cached": False
            }
        except Exception as e:
            logger.error(f"Error analyzing audio file: {e}")
            return {
                "error": str(e),
                "file_path": file_path,
                "status": "error"
            }

    # analyze_audio *is* the analysis; expose it under analyze() too so the
    # per-tool API surface is uniform.
    async def analyze(self, ctx, file_path: str, **params) -> dict:
        return await self.apply(ctx, file_path)
