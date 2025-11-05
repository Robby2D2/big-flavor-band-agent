import { Server } from '@modelcontextprotocol/sdk/server/index.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
  ListResourcesRequestSchema,
  ReadResourceRequestSchema,
} from '@modelcontextprotocol/sdk/types.js';
import { SongLibrary } from './song-library.js';
import { MusicAnalyzer } from './music-analyzer.js';

/**
 * MCP Server for Big Flavor Band
 * Provides tools and resources for managing the band's song library
 */
class BigFlavorMCPServer {
  private server: Server;
  private songLibrary: SongLibrary;
  private musicAnalyzer: MusicAnalyzer;

  constructor() {
    this.server = new Server(
      {
        name: 'big-flavor-mcp-server',
        version: '1.0.0',
      },
      {
        capabilities: {
          tools: {},
          resources: {},
        },
      }
    );

    this.songLibrary = new SongLibrary();
    this.musicAnalyzer = new MusicAnalyzer();

    this.setupHandlers();
  }

  private setupHandlers() {
    // List available tools
    this.server.setRequestHandler(ListToolsRequestSchema, async () => ({
      tools: [
        {
          name: 'get_songs',
          description: 'Get all songs from the Big Flavor library',
          inputSchema: {
            type: 'object',
            properties: {
              genre: {
                type: 'string',
                description: 'Filter by genre (optional)',
              },
              limit: {
                type: 'number',
                description: 'Maximum number of songs to return',
              },
            },
          },
        },
        {
          name: 'get_song_details',
          description: 'Get detailed information about a specific song',
          inputSchema: {
            type: 'object',
            properties: {
              songId: {
                type: 'string',
                description: 'The unique identifier of the song',
              },
            },
            required: ['songId'],
          },
        },
        {
          name: 'recommend_songs',
          description: 'Get song recommendations based on a seed song or preferences',
          inputSchema: {
            type: 'object',
            properties: {
              seedSongId: {
                type: 'string',
                description: 'Song ID to base recommendations on',
              },
              mood: {
                type: 'string',
                description: 'Desired mood (e.g., upbeat, mellow, energetic)',
              },
              count: {
                type: 'number',
                description: 'Number of recommendations to return',
              },
            },
          },
        },
        {
          name: 'create_album',
          description: 'Suggest songs that would work well together as an album',
          inputSchema: {
            type: 'object',
            properties: {
              theme: {
                type: 'string',
                description: 'Album theme or concept',
              },
              songCount: {
                type: 'number',
                description: 'Number of songs for the album',
              },
            },
          },
        },
        {
          name: 'analyze_audio',
          description: 'Analyze audio characteristics of a song',
          inputSchema: {
            type: 'object',
            properties: {
              songId: {
                type: 'string',
                description: 'Song ID to analyze',
              },
              analysisType: {
                type: 'string',
                enum: ['tempo', 'key', 'loudness', 'full'],
                description: 'Type of analysis to perform',
              },
            },
            required: ['songId'],
          },
        },
        {
          name: 'suggest_improvements',
          description: 'Suggest sound engineering improvements for a song',
          inputSchema: {
            type: 'object',
            properties: {
              songId: {
                type: 'string',
                description: 'Song ID to analyze for improvements',
              },
            },
            required: ['songId'],
          },
        },
      ],
    }));

    // List available resources
    this.server.setRequestHandler(ListResourcesRequestSchema, async () => ({
      resources: [
        {
          uri: 'bigflavor://songs',
          name: 'Song Library',
          description: 'Complete Big Flavor song library',
          mimeType: 'application/json',
        },
        {
          uri: 'bigflavor://stats',
          name: 'Library Statistics',
          description: 'Statistics about the song library',
          mimeType: 'application/json',
        },
      ],
    }));

    // Read resources
    this.server.setRequestHandler(ReadResourceRequestSchema, async (request) => {
      const uri = request.params.uri;

      if (uri === 'bigflavor://songs') {
        const songs = await this.songLibrary.getAllSongs();
        return {
          contents: [
            {
              uri,
              mimeType: 'application/json',
              text: JSON.stringify(songs, null, 2),
            },
          ],
        };
      }

      if (uri === 'bigflavor://stats') {
        const stats = await this.songLibrary.getStatistics();
        return {
          contents: [
            {
              uri,
              mimeType: 'application/json',
              text: JSON.stringify(stats, null, 2),
            },
          ],
        };
      }

      throw new Error(`Unknown resource: ${uri}`);
    });

    // Handle tool calls
    this.server.setRequestHandler(CallToolRequestSchema, async (request) => {
      const { name, arguments: args } = request.params;

      switch (name) {
        case 'get_songs':
          return {
            content: [
              {
                type: 'text',
                text: JSON.stringify(
                  await this.songLibrary.getSongs(
                    args?.genre as string | undefined,
                    args?.limit as number | undefined
                  ),
                  null,
                  2
                ),
              },
            ],
          };

        case 'get_song_details':
          if (!args?.songId) {
            throw new Error('songId is required');
          }
          return {
            content: [
              {
                type: 'text',
                text: JSON.stringify(
                  await this.songLibrary.getSongDetails(args.songId as string),
                  null,
                  2
                ),
              },
            ],
          };

        case 'recommend_songs':
          return {
            content: [
              {
                type: 'text',
                text: JSON.stringify(
                  await this.songLibrary.recommendSongs(
                    args?.seedSongId as string | undefined,
                    args?.mood as string | undefined,
                    (args?.count as number) || 5
                  ),
                  null,
                  2
                ),
              },
            ],
          };

        case 'create_album':
          return {
            content: [
              {
                type: 'text',
                text: JSON.stringify(
                  await this.songLibrary.createAlbum(
                    args?.theme as string | undefined,
                    (args?.songCount as number) || 10
                  ),
                  null,
                  2
                ),
              },
            ],
          };

        case 'analyze_audio':
          if (!args?.songId) {
            throw new Error('songId is required');
          }
          return {
            content: [
              {
                type: 'text',
                text: JSON.stringify(
                  await this.musicAnalyzer.analyzeAudio(
                    args.songId as string,
                    (args?.analysisType as string) || 'full'
                  ),
                  null,
                  2
                ),
              },
            ],
          };

        case 'suggest_improvements':
          if (!args?.songId) {
            throw new Error('songId is required');
          }
          return {
            content: [
              {
                type: 'text',
                text: JSON.stringify(
                  await this.musicAnalyzer.suggestImprovements(
                    args.songId as string
                  ),
                  null,
                  2
                ),
              },
            ],
          };

        default:
          throw new Error(`Unknown tool: ${name}`);
      }
    });
  }

  async start() {
    const transport = new StdioServerTransport();
    await this.server.connect(transport);
    console.error('Big Flavor MCP Server running on stdio');
  }
}

// Start the server
const server = new BigFlavorMCPServer();
server.start().catch(console.error);
