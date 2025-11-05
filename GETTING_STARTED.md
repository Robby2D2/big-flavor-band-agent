# Getting Started with Big Flavor AI Agent

This guide will help you set up and use the Big Flavor AI Agent system.

## Prerequisites

- Node.js 18 or higher
- npm or yarn
- An OpenAI API key (get one at https://platform.openai.com/)

## Step-by-Step Setup

### 1. Install Dependencies

First, install all required packages:

```powershell
npm install
```

### 2. Configure Environment

Create a `.env` file from the example:

```powershell
Copy-Item .env.example .env
```

Then edit the `.env` file and add your OpenAI API key:

```
OPENAI_API_KEY=sk-your-actual-api-key-here
```

### 3. Build the Project

Compile the TypeScript code:

```powershell
npm run build
```

### 4. Run Examples

Try the example script to see the agent in action:

```powershell
npm run start:agent
```

## Understanding the Components

### MCP Server

The MCP (Model Context Protocol) server provides structured access to your song library. It exposes:

- **Tools**: Functions that can be called to interact with the library
- **Resources**: Data endpoints that can be read

To start the MCP server standalone:

```powershell
npm run start:mcp
```

### AI Agent

The AI Agent uses OpenAI's GPT models to provide intelligent, conversational interactions. It can:

- Answer questions about your songs
- Provide personalized recommendations
- Suggest album arrangements
- Offer sound engineering advice

## Common Use Cases

### 1. Getting Song Recommendations

```typescript
import { BigFlavorAgent } from './src/agent/index.js';

const agent = new BigFlavorAgent();

// Get recommendations by mood
const response = await agent.recommendSongs({
  mood: 'upbeat',
  count: 5
});

// Get recommendations similar to a specific song
const similar = await agent.recommendSongs({
  seedSongId: '1',
  count: 3
});
```

### 2. Creating an Album

```typescript
// Create a themed album
const album = await agent.suggestAlbum('Summer Road Trip', 8);

// Create a general best-of collection
const bestOf = await agent.suggestAlbum();
```

### 3. Analyzing Songs

```typescript
// Get detailed analysis and improvement suggestions
const analysis = await agent.analyzeSong('1');
```

### 4. Conversational Mode

```typescript
// The agent maintains conversation context
const agent = new BigFlavorAgent();

await agent.chat("What's the most energetic song you have?");
await agent.chat("Can you recommend similar songs?");
await agent.chat("How can we make them sound better?");

// Reset conversation when starting a new topic
agent.resetConversation();
```

## Customizing the Song Library

To add your own songs, edit `src/mcp-server/song-library.ts`:

```typescript
private initializeSampleData() {
  this.songs = [
    {
      id: '1',
      title: 'Your Song Title',
      artist: 'Big Flavor',
      genre: 'Rock',
      duration: 240, // seconds
      bpm: 120,
      key: 'E',
      mood: ['upbeat', 'energetic'],
      tags: ['original', 'live-favorite'],
      releaseDate: '2024-11-01',
    },
    // Add more songs...
  ];
}
```

## Integrating with Your Website

### Option 1: REST API

You can expose the MCP server as a REST API by creating an Express wrapper:

```typescript
import express from 'express';
import { SongLibrary } from './mcp-server/song-library.js';

const app = express();
const library = new SongLibrary();

app.get('/api/songs', async (req, res) => {
  const songs = await library.getAllSongs();
  res.json(songs);
});

app.listen(3000);
```

### Option 2: Direct Integration

Import the components directly into your existing Node.js application:

```typescript
import { BigFlavorAgent } from './agent/index.js';
import { SongLibrary } from './mcp-server/song-library.js';
```

## Troubleshooting

### "Cannot find module" errors

Make sure you've installed dependencies:
```powershell
npm install
```

### TypeScript compilation errors

Rebuild the project:
```powershell
npm run build
```

### OpenAI API errors

- Check that your API key is correctly set in `.env`
- Verify your API key has available credits
- Ensure you're using a compatible model (GPT-4 or GPT-3.5)

### MCP Server not responding

- Ensure the server is running before connecting clients
- Check that stdio communication is properly configured
- Verify no other process is using the same communication channel

## Next Steps

1. **Populate your library**: Add your actual songs to the library
2. **Customize analysis**: Adjust the audio analysis parameters for your needs
3. **Build a UI**: Create a web interface for easier interaction
4. **Add persistence**: Connect to a database for permanent storage
5. **Enhance recommendations**: Integrate with music APIs like Spotify for better analysis

## Getting Help

- Check the main README.md for project overview
- Review the code comments for implementation details
- Modify the example scripts to test different scenarios

Happy jamming! 🎸🎵
