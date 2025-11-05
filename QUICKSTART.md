# Big Flavor AI Agent - Quick Reference

## Setup Checklist

✅ 1. Install dependencies: `npm install`
✅ 2. Copy `.env.example` to `.env` and add your OpenAI API key
✅ 3. Build the project: `npm run build`
✅ 4. Start using: `npm start`

## Quick Commands

```powershell
# Interactive CLI (recommended for first time)
npm start

# Run examples
npm run examples

# Start MCP server only
npm run start:mcp

# Development mode (auto-rebuild)
npm run dev
```

## CLI Quick Commands

Once in the interactive CLI:

- `/songs` - See all songs
- `/stats` - Library stats
- `/analyze 1` - Analyze song #1
- `/recommend` - Get recommendations
- `/album` - Create album
- `/help` - Show help
- `/quit` - Exit

## Environment Variables

Required in `.env`:
```
OPENAI_API_KEY=your_key_here
```

Optional:
```
MCP_SERVER_PORT=3000
MCP_SERVER_HOST=localhost
```

## Project Structure

```
src/
├── mcp-server/          # MCP Server implementation
│   ├── index.ts         # Server entry point
│   ├── song-library.ts  # Song data management
│   └── music-analyzer.ts # Audio analysis
├── agent/
│   └── index.ts         # AI Agent
├── cli.ts               # Interactive CLI
└── examples.ts          # Usage examples
```

## Adding Your Songs

Edit `src/mcp-server/song-library.ts`:

```typescript
{
  id: 'unique-id',
  title: 'Song Title',
  artist: 'Big Flavor',
  genre: 'Rock',
  duration: 240,  // seconds
  bpm: 120,
  key: 'E',
  mood: ['upbeat', 'energetic'],
  tags: ['original'],
}
```

## Troubleshooting

**"Cannot find module" errors:**
```powershell
npm install
npm run build
```

**OpenAI errors:**
- Check `.env` has correct API key
- Verify API key has credits

**TypeScript errors:**
```powershell
npm run build
```

## Next Steps

1. 🎵 Add your actual songs to the library
2. 🤖 Try the interactive CLI
3. 🔧 Customize recommendations
4. 🌐 Build a web interface
5. 💾 Add database persistence

Rock on! 🎸
