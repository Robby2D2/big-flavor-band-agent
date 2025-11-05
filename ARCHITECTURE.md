# Big Flavor Band Agent - Architecture & Technical Documentation

## System Overview

The Big Flavor Band Agent is a modular system consisting of three main components that work together to provide intelligent music management and recommendations.

```
┌─────────────────────────────────────────────────────────────┐
│                     Big Flavor System                        │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌─────────────┐      ┌──────────────┐      ┌────────────┐ │
│  │             │      │              │      │            │ │
│  │  CLI/User   │─────▶│  AI Agent    │─────▶│  OpenAI    │ │
│  │  Interface  │      │              │      │    API     │ │
│  │             │      └──────────────┘      └────────────┘ │
│  └─────────────┘              │                             │
│        │                      │                             │
│        │                      ▼                             │
│        │              ┌──────────────┐                      │
│        └─────────────▶│              │                      │
│                       │  MCP Server  │                      │
│                       │              │                      │
│                       └──────────────┘                      │
│                              │                              │
│                    ┌─────────┴─────────┐                   │
│                    │                   │                   │
│            ┌───────▼────────┐  ┌──────▼────────┐          │
│            │                │  │               │          │
│            │ Song Library   │  │    Music      │          │
│            │                │  │   Analyzer    │          │
│            └────────────────┘  └───────────────┘          │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

## Component Details

### 1. MCP Server (`src/mcp-server/`)

The Model Context Protocol (MCP) server provides a standardized interface for accessing the band's song library and music analysis tools.

#### Key Features:
- **Tools**: Executable functions that can be called by MCP clients
- **Resources**: Data endpoints that can be read
- **Standardized Communication**: Uses stdio for IPC

#### Exposed Tools:

| Tool Name | Description | Parameters |
|-----------|-------------|------------|
| `get_songs` | Retrieve songs with optional filtering | `genre?`, `limit?` |
| `get_song_details` | Get detailed info about a song | `songId` |
| `recommend_songs` | AI-powered recommendations | `seedSongId?`, `mood?`, `count?` |
| `create_album` | Generate album arrangements | `theme?`, `songCount?` |
| `analyze_audio` | Analyze audio characteristics | `songId`, `analysisType?` |
| `suggest_improvements` | Get sound engineering tips | `songId` |

#### Exposed Resources:

| Resource URI | Description | Format |
|--------------|-------------|--------|
| `bigflavor://songs` | Complete song library | JSON |
| `bigflavor://stats` | Library statistics | JSON |

### 2. Song Library (`src/mcp-server/song-library.ts`)

Manages the band's song collection with metadata and provides recommendation logic.

#### Data Model:

```typescript
interface Song {
  id: string;              // Unique identifier
  title: string;           // Song title
  artist: string;          // Artist name (typically "Big Flavor")
  genre: string;           // Music genre
  duration: number;        // Length in seconds
  bpm?: number;            // Beats per minute
  key?: string;            // Musical key (e.g., "E", "G")
  mood: string[];          // Mood tags
  tags: string[];          // Additional tags
  audioUrl?: string;       // URL to audio file
  releaseDate?: string;    // Release date
  lyrics?: string;         // Song lyrics
  metadata?: {             // Additional metadata
    recordedDate?: string;
    location?: string;
    equipment?: string[];
  };
}
```

#### Recommendation Algorithm:

1. **Seed-based**: Finds songs with similar genre, mood, or BPM
2. **Mood-based**: Filters by mood tags
3. **Fallback**: Random selection if no criteria match

### 3. Music Analyzer (`src/mcp-server/music-analyzer.ts`)

Provides audio analysis and sound engineering suggestions.

#### Analysis Capabilities:

- **Tempo Analysis**: BPM detection and stability
- **Key Detection**: Musical key and scale identification
- **Loudness Analysis**: Peak, RMS, LUFS measurements
- **Frequency Spectrum**: Bass, mid, and treble energy distribution
- **Quality Assessment**: Sample rate, bit depth, format

#### Improvement Suggestions:

The analyzer provides practical, dad-friendly advice in these categories:

1. **Mastering**: Overall loudness and level optimization
2. **Dynamics**: Compression and dynamic range
3. **EQ/Frequency Balance**: Frequency distribution and tone
4. **Technical Quality**: Recording/export settings
5. **Performance**: Timing and execution tips

### 4. AI Agent (`src/agent/index.ts`)

The intelligent conversational interface powered by OpenAI's GPT models.

#### Features:

- **Conversation Memory**: Maintains context across interactions
- **Natural Language**: Understands queries in plain English
- **Personalized Responses**: Tailored to dad musicians
- **Tool Integration**: Can call MCP server tools (in future versions)

#### Key Methods:

- `chat(message)`: General conversation
- `recommendSongs(criteria)`: Get recommendations
- `suggestAlbum(theme, count)`: Create album arrangements
- `analyzeSong(songId)`: Analyze and improve songs
- `getMusicAdvice(question)`: General music advice

### 5. Interactive CLI (`src/cli.ts`)

A user-friendly command-line interface for interacting with the system.

## Data Flow Examples

### Example 1: Getting Song Recommendations

```
User → CLI → Agent → OpenAI API
                ↓
            MCP Server → Song Library
                ↓
            Agent (formats response)
                ↓
            CLI → User
```

### Example 2: Analyzing a Song

```
User → CLI → Agent → OpenAI API
                ↓
            MCP Server → Music Analyzer
                ↓
            Agent (interprets & explains)
                ↓
            CLI → User
```

## Configuration

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `OPENAI_API_KEY` | Yes | - | OpenAI API key |
| `MCP_SERVER_PORT` | No | 3000 | MCP server port |
| `MCP_SERVER_HOST` | No | localhost | MCP server host |
| `BIGFLAVOR_URL` | No | https://bigflavorband.com | Band website URL |
| `SONG_LIBRARY_PATH` | No | ./data/songs | Local song storage path |

### TypeScript Configuration

The project uses modern TypeScript with ES2020 modules:

- **Target**: ES2020
- **Module**: ES2020 (native ESM)
- **Strict Mode**: Enabled
- **Source Maps**: Enabled for debugging

## Extension Points

### Adding New Songs

1. Edit `src/mcp-server/song-library.ts`
2. Add songs to the `initializeSampleData()` method
3. Or implement database integration for persistence

### Adding New Tools

1. Define tool schema in `ListToolsRequestSchema` handler
2. Implement tool logic in `CallToolRequestSchema` handler
3. Add corresponding methods to Song Library or Music Analyzer

### Customizing Analysis

Modify `src/mcp-server/music-analyzer.ts`:
- Adjust analysis parameters
- Add new analysis types
- Customize improvement suggestions

### Enhancing AI Behavior

Modify `src/agent/index.ts`:
- Update system prompt
- Adjust temperature/parameters
- Add function calling capabilities

## Future Enhancements

### Phase 1: Foundation (✅ Complete)
- [x] MCP server implementation
- [x] Song library management
- [x] Basic music analyzer
- [x] AI agent integration
- [x] Interactive CLI

### Phase 2: Data Integration
- [ ] Database persistence (SQLite/PostgreSQL)
- [ ] Real audio file analysis (Web Audio API)
- [ ] Integration with band website
- [ ] Import from music streaming services

### Phase 3: Advanced Features
- [ ] Collaborative filtering recommendations
- [ ] Machine learning for audio analysis
- [ ] Automated mixing suggestions
- [ ] Practice session scheduler
- [ ] Setlist generator

### Phase 4: User Interface
- [ ] Web-based UI
- [ ] Mobile app
- [ ] VS Code extension
- [ ] Slack/Discord bot

## Performance Considerations

### Current Scale
- Suitable for: 1-1000 songs
- Response time: < 2s for most operations
- Memory usage: Minimal (in-memory storage)

### Scaling Options
- **Database**: For >100 songs, use persistent storage
- **Caching**: Cache AI responses for common queries
- **Async Processing**: Queue heavy audio analysis tasks
- **CDN**: Serve audio files from CDN

## Security Notes

### API Keys
- Never commit `.env` file
- Use environment variables in production
- Rotate keys regularly

### Data Privacy
- Song data is local by default
- No external tracking or analytics
- OpenAI API: Review their data usage policy

## Testing

### Manual Testing
```powershell
# Test CLI
npm start

# Test examples
npm run examples

# Test MCP server
npm run start:mcp
```

### Future: Automated Tests
- Unit tests for song library
- Integration tests for MCP server
- E2E tests for agent interactions

## Deployment

### Local Development
```powershell
npm install
npm run build
npm start
```

### Production Options

1. **Docker Container**
```dockerfile
FROM node:20-alpine
WORKDIR /app
COPY . .
RUN npm install && npm run build
CMD ["npm", "start"]
```

2. **Cloud Functions**
- Deploy individual components as serverless functions
- MCP server as API endpoint
- Agent as webhook handler

3. **Desktop App**
- Package with Electron
- Bundle MCP server and agent
- Include local database

## Troubleshooting Guide

### Common Issues

**Build Errors**
- Ensure Node.js 18+ is installed
- Clear `node_modules` and reinstall: `rm -rf node_modules; npm install`
- Check TypeScript version: `npx tsc --version`

**API Errors**
- Verify `.env` file exists and has valid `OPENAI_API_KEY`
- Check API key permissions and credits
- Review OpenAI status page for outages

**MCP Server Issues**
- Ensure only one instance is running
- Check stdio configuration
- Verify no port conflicts (if using HTTP mode)

## Contributing

### Code Style
- TypeScript strict mode
- ES2020+ features
- Functional programming preferred
- Clear, descriptive naming

### Commit Guidelines
- Use conventional commits
- Include tests for new features
- Update documentation

## License

MIT License - See LICENSE file

## Support

For issues or questions:
1. Check documentation (README.md, GETTING_STARTED.md)
2. Review code comments
3. Open an issue on GitHub

---

**Built with ❤️ for Big Flavor Band** 🎸
