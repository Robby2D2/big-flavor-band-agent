# Big Flavor Band Agent 🎸

An AI-powered agent and MCP (Model Context Protocol) server for managing Big Flavor Band's song library, providing intelligent recommendations, and offering sound engineering assistance.

## Overview

This project consists of two main components:

1. **MCP Server**: Provides tools and resources for accessing and managing the band's song library
2. **AI Agent**: An intelligent assistant that uses OpenAI's GPT models to provide personalized recommendations and advice

## Features

### Song Library Management
- Store and retrieve song metadata (title, genre, BPM, key, mood, etc.)
- Filter songs by genre, mood, or other criteria
- Get detailed information about specific songs

### Smart Recommendations
- Get song suggestions based on mood, genre, or similarity to other songs
- AI-powered explanations for why songs work well together
- Context-aware recommendations that understand the band's style

### Album Creation
- Suggest song arrangements that work well together
- Theme-based album curation
- Intelligent song ordering for optimal flow

### Audio Analysis & Sound Engineering
- Analyze tempo, key, and loudness characteristics
- Get frequency spectrum analysis
- Receive practical improvement suggestions
- Dad-friendly advice that's achievable for hobbyist musicians

## Installation

1. **Clone the repository**:
```bash
git clone <repository-url>
cd big-flavor-band-agent
```

2. **Install dependencies**:
```bash
npm install
```

3. **Set up environment variables**:
```bash
cp .env.example .env
```

Then edit `.env` and add your OpenAI API key:
```
OPENAI_API_KEY=your_api_key_here
```

4. **Build the project**:
```bash
npm run build
```

## Usage

### Running the MCP Server

The MCP server provides tools and resources that can be accessed via the Model Context Protocol:

```bash
npm run start:mcp
```

The server runs on stdio and can be integrated with MCP-compatible clients.

### Running the AI Agent

The AI agent provides an interactive interface for getting recommendations and advice:

```bash
npm run start:agent
```

### Available MCP Tools

The MCP server exposes the following tools:

- **get_songs**: Retrieve all songs (with optional genre filter)
- **get_song_details**: Get detailed information about a specific song
- **recommend_songs**: Get AI-powered song recommendations
- **create_album**: Generate album arrangements
- **analyze_audio**: Analyze audio characteristics
- **suggest_improvements**: Get sound engineering suggestions

### Available Resources

- **bigflavor://songs**: Complete song library
- **bigflavor://stats**: Library statistics

## Project Structure

```
big-flavor-band-agent/
├── src/
│   ├── mcp-server/
│   │   ├── index.ts              # MCP server implementation
│   │   ├── song-library.ts       # Song storage and retrieval
│   │   └── music-analyzer.ts     # Audio analysis logic
│   └── agent/
│       └── index.ts              # AI agent implementation
├── package.json
├── tsconfig.json
├── .env.example
└── README.md
```

## Example Use Cases

### 1. Get Song Recommendations

```typescript
import { BigFlavorAgent } from './src/agent';

const agent = new BigFlavorAgent();
const recommendations = await agent.recommendSongs({
  mood: 'upbeat',
  count: 5
});
```

### 2. Create an Album

```typescript
const album = await agent.suggestAlbum('Summer Vibes', 8);
```

### 3. Analyze a Song

```typescript
const analysis = await agent.analyzeSong('song-id-123');
```

## Development

### Watch Mode

For development with auto-recompilation:

```bash
npm run dev
```

### Adding New Songs

Edit `src/mcp-server/song-library.ts` and add songs to the `initializeSampleData()` method, or implement database integration for persistent storage.

## Integrating with Your Website

To integrate with your existing website at https://bigflavorband.com/, you can:

1. Export song data from your website
2. Import it into the song library
3. Use the MCP server as an API backend
4. Add the AI agent as a chatbot interface

## Future Enhancements

- [ ] Real audio file analysis using Web Audio API or librosa
- [ ] Integration with music streaming platforms
- [ ] Collaborative filtering for better recommendations
- [ ] Practice session scheduler
- [ ] Setlist generator for live performances
- [ ] Equipment and gear recommendations
- [ ] Lyrics analysis and songwriting assistance

## Contributing

This is a personal project for Big Flavor Band, but suggestions and improvements are welcome!

## License

MIT

## About Big Flavor

Big Flavor is a dad band - four friends who love making music together. We're not professional musicians, but we have a great time jamming and creating tunes. This AI agent helps us manage our growing song library and gives us helpful (and encouraging) advice to improve our sound.

Rock on! 🤘
