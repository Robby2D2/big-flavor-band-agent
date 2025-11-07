"""
Big Flavor Band Search MCP Server
A Model Context Protocol server for search and retrieval operations.
This server exposes the RAG system's search capabilities as MCP tools.
WRITE/PRODUCTION operations are handled by the production MCP server.
"""

import asyncio
import json
import logging
from typing import Any, Optional, List
from pathlib import Path

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from database import DatabaseManager
from rag_system import SongRAGSystem

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("big-flavor-search-mcp")


class BigFlavorSearchMCPServer:
    """
    MCP Server that exposes RAG system search capabilities as tools.
    
    This server is a thin wrapper around the SongRAGSystem library,
    exposing its methods as MCP tools for the agent to use.
    """
    
    def __init__(self, use_clap: bool = True):
        self.app = Server("big-flavor-search-server")
        self.use_clap = use_clap
        self.db_manager = None
        self.rag_system = None  # The actual RAG system library
        self.setup_handlers()
    
    async def initialize(self):
        """Initialize database connection and RAG system library."""
        try:
            # Initialize database
            self.db_manager = DatabaseManager()
            await self.db_manager.connect()
            
            # Initialize the RAG system library
            self.rag_system = SongRAGSystem(self.db_manager, use_clap=self.use_clap)
            logger.info("RAG system library initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize RAG system: {e}")
            raise
    
    def setup_handlers(self):
        """Set up MCP request handlers for search/retrieval operations."""
        
        @self.app.list_tools()
        async def list_tools() -> list[Tool]:
            """List available search and retrieval tools."""
            return [
                Tool(
                    name="search_by_audio_file",
                    description="Find songs similar to an uploaded audio file by comparing audio characteristics using AI embeddings",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "audio_path": {
                                "type": "string",
                                "description": "Path to the reference audio file"
                            },
                            "limit": {
                                "type": "number",
                                "description": "Maximum number of results to return (default: 10)"
                            },
                            "similarity_threshold": {
                                "type": "number",
                                "description": "Minimum similarity score 0-1 (default: 0.5)"
                            }
                        },
                        "required": ["audio_path"]
                    }
                ),
                Tool(
                    name="search_by_text_description",
                    description="Find songs matching a text description like 'ambient sleep music' or 'energetic workout beats'",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "description": {
                                "type": "string",
                                "description": "Text description of desired music (e.g., 'calm piano', 'upbeat rock')"
                            },
                            "limit": {
                                "type": "number",
                                "description": "Maximum number of results to return (default: 10)"
                            }
                        },
                        "required": ["description"]
                    }
                ),
                Tool(
                    name="search_by_tempo_range",
                    description="Find songs within a specific tempo range (BPM)",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "min_tempo": {
                                "type": "number",
                                "description": "Minimum tempo in BPM (optional)"
                            },
                            "max_tempo": {
                                "type": "number",
                                "description": "Maximum tempo in BPM (optional)"
                            },
                            "limit": {
                                "type": "number",
                                "description": "Maximum number of results (default: 10)"
                            }
                        },
                        "required": []
                    }
                ),
                Tool(
                    name="search_hybrid",
                    description="Search with multiple criteria: audio similarity, text description, tempo, key. Provides most flexible search.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "audio_path": {
                                "type": "string",
                                "description": "Optional: path to reference audio file for sonic similarity"
                            },
                            "description": {
                                "type": "string",
                                "description": "Optional: text description of desired music"
                            },
                            "min_tempo": {
                                "type": "number",
                                "description": "Optional: minimum tempo in BPM"
                            },
                            "max_tempo": {
                                "type": "number",
                                "description": "Optional: maximum tempo in BPM"
                            },
                            "audio_weight": {
                                "type": "number",
                                "description": "Weight for audio similarity 0-1 (default: 0.6)"
                            },
                            "text_weight": {
                                "type": "number",
                                "description": "Weight for text similarity 0-1 (default: 0.4)"
                            },
                            "limit": {
                                "type": "number",
                                "description": "Maximum number of results (default: 10)"
                            }
                        },
                        "required": []
                    }
                ),
                Tool(
                    name="get_embedding_stats",
                    description="Get statistics about the RAG system - how many songs are indexed, coverage, etc.",
                    inputSchema={
                        "type": "object",
                        "properties": {},
                    }
                ),
                Tool(
                    name="find_songs_without_embeddings",
                    description="Find songs that haven't been indexed yet in the RAG system",
                    inputSchema={
                        "type": "object",
                        "properties": {},
                    }
                ),
            ]
        
        @self.app.call_tool()
        async def call_tool(name: str, arguments: Any) -> list[TextContent]:
            """Handle tool execution requests."""
            try:
                if name == "search_by_audio_file":
                    result = await self.search_by_audio_file(
                        arguments["audio_path"],
                        arguments.get("limit", 10),
                        arguments.get("similarity_threshold", 0.5)
                    )
                elif name == "search_by_text_description":
                    result = await self.search_by_text_description(
                        arguments["description"],
                        arguments.get("limit", 10)
                    )
                elif name == "search_by_tempo_range":
                    result = await self.search_by_tempo_range(
                        arguments.get("min_tempo"),
                        arguments.get("max_tempo"),
                        arguments.get("limit", 10)
                    )
                elif name == "search_hybrid":
                    result = await self.search_hybrid(
                        arguments.get("audio_path"),
                        arguments.get("description"),
                        arguments.get("min_tempo"),
                        arguments.get("max_tempo"),
                        arguments.get("audio_weight", 0.6),
                        arguments.get("text_weight", 0.4),
                        arguments.get("limit", 10)
                    )
                elif name == "get_embedding_stats":
                    result = await self.get_embedding_stats()
                elif name == "find_songs_without_embeddings":
                    result = await self.find_songs_without_embeddings()
                else:
                    result = {"error": f"Unknown tool: {name}"}
                
                return [TextContent(
                    type="text",
                    text=json.dumps(result, indent=2)
                )]
            except Exception as e:
                logger.error(f"Error executing tool {name}: {e}")
                return [TextContent(
                    type="text",
                    text=json.dumps({"error": str(e)})
                )]
    
    async def search_by_audio_file(
        self, 
        audio_path: str, 
        limit: int = 10,
        similarity_threshold: float = 0.5
    ) -> dict:
        """
        Find songs similar to a reference audio file.
        
        Args:
            audio_path: Path to reference audio file
            limit: Maximum number of results
            similarity_threshold: Minimum similarity score (0-1)
            
        Returns:
            Search results with similar songs
        """
        try:
            results = await self.rag_system.search_by_audio_similarity(
                audio_path,
                limit=limit,
                similarity_threshold=similarity_threshold
            )
            
            return {
                "status": "success",
                "query_audio": audio_path,
                "results_count": len(results),
                "songs": results
            }
            
        except Exception as e:
            logger.error(f"Error in audio similarity search: {e}")
            return {
                "status": "error",
                "error": str(e)
            }
    
    async def search_by_text_description(
        self, 
        description: str, 
        limit: int = 10
    ) -> dict:
        """
        Find songs matching a text description.
        
        Args:
            description: Text description of desired music
            limit: Maximum number of results
            
        Returns:
            Search results with matching songs
        """
        try:
            results = await self.rag_system.search_by_text_description(
                description,
                limit=limit
            )
            
            return {
                "status": "success",
                "query": description,
                "results_count": len(results),
                "songs": results
            }
            
        except Exception as e:
            logger.error(f"Error in text description search: {e}")
            return {
                "status": "error",
                "error": str(e)
            }
    
    async def search_by_tempo_range(
        self,
        min_tempo: Optional[float] = None,
        max_tempo: Optional[float] = None,
        limit: int = 10
    ) -> dict:
        """
        Find songs within a tempo range.
        
        Args:
            min_tempo: Minimum tempo in BPM (optional)
            max_tempo: Maximum tempo in BPM (optional)
            limit: Maximum number of results
            
        Returns:
            Search results with songs in tempo range
        """
        try:
            results = await self.rag_system.search_by_tempo_range(
                min_tempo=min_tempo,
                max_tempo=max_tempo,
                limit=limit
            )
            
            return {
                "status": "success",
                "min_tempo": min_tempo,
                "max_tempo": max_tempo,
                "results_count": len(results),
                "songs": results
            }
            
        except Exception as e:
            logger.error(f"Error in tempo range search: {e}")
            return {
                "status": "error",
                "error": str(e)
            }
    
    async def search_hybrid(
        self,
        audio_path: Optional[str] = None,
        description: Optional[str] = None,
        min_tempo: Optional[float] = None,
        max_tempo: Optional[float] = None,
        audio_weight: float = 0.6,
        text_weight: float = 0.4,
        limit: int = 10
    ) -> dict:
        """
        Hybrid search combining multiple criteria.
        
        Args:
            audio_path: Optional path to reference audio
            description: Optional text description
            min_tempo: Optional minimum BPM
            max_tempo: Optional maximum BPM
            audio_weight: Weight for audio similarity (0-1)
            text_weight: Weight for text similarity (0-1)
            limit: Maximum number of results
            
        Returns:
            Search results combining multiple criteria
        """
        try:
            # Start with all results
            results = []
            
            # If we have audio similarity
            if audio_path:
                audio_results = await self.rag_system.search_by_audio_similarity(
                    audio_path,
                    limit=limit * 2,  # Get more for filtering
                    similarity_threshold=0.3
                )
                results.extend(audio_results)
            
            # If we have text description
            if description:
                text_results = await self.rag_system.search_by_text_description(
                    description,
                    limit=limit * 2
                )
                
                # Merge with audio results if we have both
                if audio_path:
                    # Combine scores with weights
                    song_scores = {}
                    for song in results:
                        song_scores[song['id']] = {
                            'song': song,
                            'audio_score': song.get('similarity', 0.5) * audio_weight
                        }
                    
                    for song in text_results:
                        if song['id'] in song_scores:
                            song_scores[song['id']]['text_score'] = 0.8 * text_weight
                        else:
                            song_scores[song['id']] = {
                                'song': song,
                                'audio_score': 0,
                                'text_score': 0.8 * text_weight
                            }
                    
                    # Calculate combined scores
                    combined_results = []
                    for song_id, data in song_scores.items():
                        song = data['song']
                        combined_score = data.get('audio_score', 0) + data.get('text_score', 0)
                        song['combined_score'] = combined_score
                        combined_results.append(song)
                    
                    results = sorted(combined_results, key=lambda x: x['combined_score'], reverse=True)
                else:
                    results = text_results
            
            # Filter by tempo if specified
            if min_tempo is not None or max_tempo is not None:
                filtered_results = []
                for song in results:
                    tempo = song.get('tempo_bpm', 0)
                    if min_tempo is not None and tempo < min_tempo:
                        continue
                    if max_tempo is not None and tempo > max_tempo:
                        continue
                    filtered_results.append(song)
                results = filtered_results
            
            # Limit results
            results = results[:limit]
            
            return {
                "status": "success",
                "search_criteria": {
                    "audio_path": audio_path,
                    "description": description,
                    "min_tempo": min_tempo,
                    "max_tempo": max_tempo,
                    "audio_weight": audio_weight if audio_path else 0,
                    "text_weight": text_weight if description else 0
                },
                "results_count": len(results),
                "songs": results
            }
            
        except Exception as e:
            logger.error(f"Error in hybrid search: {e}")
            return {
                "status": "error",
                "error": str(e)
            }
    
    async def get_embedding_stats(self) -> dict:
        """Get statistics about the RAG system."""
        try:
            stats = await self.rag_system.get_embedding_stats()
            return {
                "status": "success",
                "stats": stats
            }
        except Exception as e:
            logger.error(f"Error getting embedding stats: {e}")
            return {
                "status": "error",
                "error": str(e)
            }
    
    async def find_songs_without_embeddings(self) -> dict:
        """Find songs not yet indexed in the RAG system."""
        try:
            songs = await self.rag_system.find_songs_without_embeddings()
            return {
                "status": "success",
                "count": len(songs),
                "songs": songs
            }
        except Exception as e:
            logger.error(f"Error finding songs without embeddings: {e}")
            return {
                "status": "error",
                "error": str(e)
            }
    
    async def run(self):
        """Run the MCP server."""
        await self.initialize()
        
        async with stdio_server() as (read_stream, write_stream):
            await self.app.run(
                read_stream,
                write_stream,
                self.app.create_initialization_options()
            )


async def main():
    """Main entry point for the Search MCP server."""
    server = BigFlavorSearchMCPServer(use_clap=True)
    await server.run()


if __name__ == "__main__":
    asyncio.run(main())
