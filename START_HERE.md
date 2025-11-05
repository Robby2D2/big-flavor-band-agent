# 🚀 Get Started in 5 Minutes!

Want to try the Big Flavor AI Agent **right now**? Follow these quick steps!

## ⚡ Super Quick Start

### 1️⃣ Prerequisites (30 seconds)

Make sure you have:
- ✅ Node.js 18+ installed ([Download](https://nodejs.org))
- ✅ An OpenAI API key ([Get one](https://platform.openai.com/api-keys))

### 2️⃣ Setup (2 minutes)

Open PowerShell in this folder and run:

```powershell
# Install dependencies
npm install

# Build the project
npm run build
```

### 3️⃣ Configure (1 minute)

Edit the `.env` file and add your OpenAI API key:

```
OPENAI_API_KEY=sk-your-actual-api-key-here
```

💡 **Tip**: The `.env` file is already created for you!

### 4️⃣ Launch! (30 seconds)

```powershell
npm start
```

That's it! You should see:

```
🎸 Welcome to Big Flavor AI Agent! 🎸

I can help you with:
  - Song recommendations
  - Album creation
  - Audio analysis and improvement suggestions
  - General music advice

Commands:
  /songs    - List all songs
  /stats    - Show library statistics
  ...
```

### 5️⃣ Try These Commands (1 minute)

Type these in the CLI:

```
/songs
```
→ See your 5 sample songs

```
/recommend
```
→ Get AI-powered song recommendations

```
/analyze 1
```
→ Analyze "Weekend Warriors" and get improvement tips

```
What are your most energetic songs?
```
→ Chat naturally with the AI!

## 🎯 What Just Happened?

You now have:
- ✅ A working MCP server managing your song library
- ✅ An AI agent that understands music
- ✅ 5 sample Big Flavor songs to play with
- ✅ Smart recommendations and analysis tools

## 📚 Next Steps

### Learn More
- Read [VISUAL_GUIDE.md](VISUAL_GUIDE.md) for a visual overview
- Check [QUICKSTART.md](QUICKSTART.md) for command reference
- See [GETTING_STARTED.md](GETTING_STARTED.md) for detailed setup

### Customize
1. **Add your songs**: Edit `src/mcp-server/song-library.ts`
2. **Rebuild**: Run `npm run build`
3. **Try again**: Run `npm start`

### Explore
- Try `/album` to create an album
- Chat naturally: "How can we improve our sound?"
- Use `/stats` to see library statistics

## 🆘 Troubleshooting

**"npm install" fails?**
- Make sure you have Node.js 18+ installed
- Try `npm cache clean --force` then reinstall

**"Cannot find OpenAI API key" error?**
- Check your `.env` file has `OPENAI_API_KEY=sk-...`
- Make sure there are no spaces or quotes around the key

**Build errors?**
- Run `npm install` again
- Delete `node_modules` and `package-lock.json`, then reinstall

**Still stuck?**
- Check [TROUBLESHOOTING.md](ARCHITECTURE.md#troubleshooting-guide) (see Architecture doc)
- Review the error message carefully
- Make sure all prerequisites are installed

## 💡 Pro Tips

1. **Type `/help`** anytime to see available commands
2. **Chat naturally** - the AI understands conversational English
3. **Use Tab** to autocomplete (in most terminals)
4. **Press Ctrl+C** to cancel long-running AI responses
5. **Type `/quit`** to exit gracefully

## 🎸 Sample Interactions

Here's what you can do right away:

### Get Recommendations
```
You: I want something upbeat for our next practice
Agent: Based on your library, I recommend...
```

### Create an Album
```
You: /album
Agent: Here's a 10-song album arrangement...
```

### Analyze a Song
```
You: /analyze 1
Agent: Analyzing "Weekend Warriors"...
Here's what I found:
- Tempo: 120 BPM (stable)
- Key: E Major
...
```

### Get Advice
```
You: How can we make our recordings sound more professional?
Agent: Great question! Here are some practical tips...
```

## ⏱️ Time Estimate

- **First time**: ~5 minutes
- **Next time**: 10 seconds (just run `npm start`)
- **Adding your songs**: ~10 minutes
- **Building web UI**: See [ROADMAP.md](ROADMAP.md)!

## 🎉 You're Ready!

You've successfully set up an AI-powered music management system with an MCP server in just 5 minutes!

Now go make some music! 🎸🎵

---

**Need more help?** Check out:
- 📖 [Full README](README.md)
- 🎨 [Visual Guide](VISUAL_GUIDE.md)  
- 🗺️ [Roadmap](ROADMAP.md)
- 🏗️ [Architecture](ARCHITECTURE.md)

**Rock on! 🤘**
