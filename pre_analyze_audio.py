"""
Audio Analysis Utility
Pre-analyze audio files from the Big Flavor RSS feed to populate the cache.
"""

import asyncio
import logging
import argparse
from pathlib import Path
from typing import List
import xml.etree.ElementTree as ET

import httpx

from audio_analysis_cache import AudioAnalysisCache

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("audio-pre-analyzer")


class AudioPreAnalyzer:
    """Pre-analyze audio files to populate the cache."""
    
    def __init__(self, rss_url: str = "https://bigflavorband.com/rss"):
        self.rss_url = rss_url
        self.audio_cache = AudioAnalysisCache()
    
    async def fetch_rss_feed(self) -> str:
        """Fetch the RSS feed content."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(self.rss_url)
            response.raise_for_status()
            return response.text
    
    def extract_audio_urls(self, rss_content: str) -> List[dict]:
        """Extract audio URLs from RSS feed."""
        try:
            root = ET.fromstring(rss_content)
            audio_files = []
            
            for idx, item in enumerate(root.findall('.//item')):
                title = item.find('title')
                enclosure = item.find('enclosure')
                
                if enclosure is not None and enclosure.get('url'):
                    audio_url = enclosure.get('url')
                    song_title = title.text if title is not None and title.text else f"Untitled {idx+1}"
                    
                    audio_files.append({
                        'url': audio_url,
                        'title': song_title,
                        'id': f"song_{idx+1:04d}"
                    })
            
            return audio_files
        except Exception as e:
            logger.error(f"Error parsing RSS feed: {e}")
            return []
    
    async def download_file(self, url: str, output_path: Path) -> bool:
        """Download an audio file."""
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                logger.info(f"Downloading {url}...")
                response = await client.get(url)
                response.raise_for_status()
                
                with open(output_path, 'wb') as f:
                    f.write(response.content)
                
                logger.info(f"Downloaded to {output_path}")
                return True
        except Exception as e:
            logger.error(f"Error downloading {url}: {e}")
            return False
    
    async def analyze_from_rss(self, download_dir: str = "audio_library", max_files: int | None = None, keep_files: bool = True):
        """
        Fetch RSS feed, download audio files, and analyze them.
        
        Args:
            download_dir: Directory for downloaded files (default: audio_library)
            max_files: Maximum number of files to analyze (None for all)
            keep_files: Whether to keep the downloaded MP3 files (default: True)
        """
        # Create download directory
        download_path = Path(download_dir)
        download_path.mkdir(exist_ok=True)
        
        logger.info("Fetching RSS feed...")
        rss_content = await self.fetch_rss_feed()
        
        logger.info("Extracting audio URLs...")
        audio_files = self.extract_audio_urls(rss_content)
        
        if max_files:
            audio_files = audio_files[:max_files]
        
        logger.info(f"Found {len(audio_files)} audio files to analyze")
        
        analyzed_count = 0
        skipped_count = 0
        error_count = 0
        
        for idx, audio_info in enumerate(audio_files, 1):
            url = audio_info['url']
            title = audio_info['title']
            
            logger.info(f"\n[{idx}/{len(audio_files)}] Processing: {title}")
            
            # Check if already cached
            cached = self.audio_cache.get_cached_analysis(url)
            
            # Create filename from song ID
            filename = f"{audio_info['id']}.mp3"
            file_path = download_path / filename
            
            # Check if file already exists locally
            if file_path.exists() and cached:
                logger.info("  ✓ Already analyzed (cached) and file exists locally")
                skipped_count += 1
                continue
            
            # Download the file if it doesn't exist
            if not file_path.exists():
                if not await self.download_file(url, file_path):
                    error_count += 1
                    continue
            else:
                logger.info(f"  Using existing file: {file_path}")
            
            # Analyze the file if not cached
            if not cached:
                try:
                    logger.info("  Analyzing audio...")
                    analysis = self.audio_cache.analyze_audio_file(str(file_path), url)
                    
                    if 'error' in analysis:
                        logger.error(f"  ✗ Analysis failed: {analysis['error']}")
                        error_count += 1
                        # Delete failed file if we don't want to keep it
                        if not keep_files:
                            try:
                                file_path.unlink()
                            except Exception:
                                pass
                    else:
                        logger.info(f"  ✓ Analysis complete: BPM={analysis.get('bpm', 'N/A')}, "
                                  f"Key={analysis.get('key', 'N/A')}, Energy={analysis.get('energy', 'N/A')}")
                        if keep_files:
                            logger.info(f"  ✓ MP3 saved to: {file_path}")
                        analyzed_count += 1
                        
                        # Clean up file if not keeping
                        if not keep_files:
                            try:
                                file_path.unlink()
                            except Exception:
                                pass
                except Exception as e:
                    logger.error(f"  ✗ Error analyzing file: {e}")
                    error_count += 1
                    # Delete failed file if we don't want to keep it
                    if not keep_files:
                        try:
                            file_path.unlink()
                        except Exception:
                            pass
            else:
                logger.info("  ✓ Already analyzed (cached)")
                skipped_count += 1
        
        # Clean up download directory if empty and not keeping files
        if not keep_files:
            try:
                download_path.rmdir()
            except Exception:
                pass
        
        # Summary
        logger.info(f"\n{'='*60}")
        logger.info("Analysis Summary:")
        logger.info(f"  Total files: {len(audio_files)}")
        logger.info(f"  Analyzed: {analyzed_count}")
        logger.info(f"  Skipped (cached): {skipped_count}")
        logger.info(f"  Errors: {error_count}")
        logger.info(f"{'='*60}")
        
        # Cache stats
        stats = self.audio_cache.get_cache_stats()
        logger.info(f"\nCache statistics:")
        logger.info(f"  Total cached entries: {stats['total_entries']}")
        logger.info(f"  Cache file: {stats['cache_file']}")
        logger.info(f"  Cache size: {stats['cache_size_bytes']} bytes")
        
        # File storage info
        if keep_files:
            logger.info(f"\nMP3 files stored in: {download_path}")
            logger.info(f"  Files can be re-analyzed without re-downloading")
        else:
            logger.info(f"\nMP3 files were deleted after analysis")
    
    async def analyze_local_files(self, directory: str):
        """
        Analyze local audio files in a directory.
        
        Args:
            directory: Directory containing audio files
        """
        dir_path = Path(directory)
        
        if not dir_path.exists():
            logger.error(f"Directory not found: {directory}")
            return
        
        # Find audio files
        audio_extensions = ['.mp3', '.wav', '.flac', '.m4a', '.ogg']
        audio_files = []
        
        for ext in audio_extensions:
            audio_files.extend(dir_path.glob(f"**/*{ext}"))
        
        logger.info(f"Found {len(audio_files)} audio files in {directory}")
        
        analyzed_count = 0
        error_count = 0
        
        for idx, file_path in enumerate(audio_files, 1):
            logger.info(f"\n[{idx}/{len(audio_files)}] Analyzing: {file_path.name}")
            
            try:
                # Use file path as the "URL" for local files
                analysis = self.audio_cache.analyze_audio_file(str(file_path), audio_url=str(file_path))
                
                if 'error' in analysis:
                    logger.error(f"  ✗ Analysis failed: {analysis['error']}")
                    error_count += 1
                else:
                    logger.info(f"  ✓ Analysis complete: BPM={analysis.get('bpm', 'N/A')}, "
                              f"Key={analysis.get('key', 'N/A')}, Energy={analysis.get('energy', 'N/A')}")
                    analyzed_count += 1
            except Exception as e:
                logger.error(f"  ✗ Error analyzing file: {e}")
                error_count += 1
        
        logger.info(f"\n{'='*60}")
        logger.info("Analysis Summary:")
        logger.info(f"  Total files: {len(audio_files)}")
        logger.info(f"  Analyzed: {analyzed_count}")
        logger.info(f"  Errors: {error_count}")
        logger.info(f"{'='*60}")


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Pre-analyze audio files to populate the cache"
    )
    parser.add_argument(
        '--rss-url',
        default='https://bigflavorband.com/rss',
        help='RSS feed URL (default: https://bigflavorband.com/rss)'
    )
    parser.add_argument(
        '--local-dir',
        help='Analyze local audio files in this directory instead of fetching from RSS'
    )
    parser.add_argument(
        '--max-files',
        type=int,
        help='Maximum number of files to analyze (useful for testing)'
    )
    parser.add_argument(
        '--download-dir',
        default='audio_library',
        help='Directory for downloaded files (default: audio_library)'
    )
    parser.add_argument(
        '--no-keep-files',
        action='store_true',
        help='Delete MP3 files after analysis (default: keep files)'
    )
    
    args = parser.parse_args()
    
    analyzer = AudioPreAnalyzer(args.rss_url)
    
    if args.local_dir:
        await analyzer.analyze_local_files(args.local_dir)
    else:
        keep_files = not args.no_keep_files
        await analyzer.analyze_from_rss(args.download_dir, args.max_files, keep_files)


if __name__ == "__main__":
    asyncio.run(main())
