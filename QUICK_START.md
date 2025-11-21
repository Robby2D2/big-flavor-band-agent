# BigFlavor Band Agent - Quick Start Guide

Get your BigFlavor web app running in just a few steps!

## ✅ Prerequisites (Already Done!)

- [x] Dependencies installed (pip and npm)
- [x] PostgreSQL database running
- [x] Audio library with 1,415 songs
- [x] Python agent working

## 🚀 Quick Start (3 Steps)

### Step 1: Set Up Google OAuth (10 minutes)

Follow the detailed guide in **GOOGLE_OAUTH_SETUP_GUIDE.md**, or here's the ultra-quick version:

1. **Go to Google Cloud Console**: https://console.cloud.google.com/
2. **Create project**: New Project → "BigFlavor Band Agent"
3. **Configure OAuth consent screen**:
   - APIs & Services → OAuth consent screen
   - Select External → Create
   - Fill in app name and emails
   - Add scopes: openid, email, profile
4. **Create credentials**:
   - APIs & Services → Credentials → Create Credentials → OAuth client ID
   - Application type: Web application
   - Authorized JavaScript origins: `http://localhost:3000`
   - Authorized redirect URIs: `http://localhost:3000/api/auth/callback`
5. **Copy credentials**: Client ID and Client Secret
6. **Update `.env.local`**: Edit `frontend/.env.local` with your Google credentials

### Step 2: Run Database Migration (30 seconds)

```powershell
psql -U bigflavor -d bigflavor -f database/sql/migrations/05-create-users-table.sql
```

This creates the users table for authentication.

### Step 3: Start the Servers (1 minute)

**Terminal 1 - Start Backend API:**
```powershell
python backend_api.py
```
Wait for: `INFO: Uvicorn running on http://0.0.0.0:8000`

**Terminal 2 - Start Frontend:**
```powershell
cd frontend
npm run dev
```
Wait for: `Ready on http://localhost:3000`

### Step 4: Open Your Browser

Go to **http://localhost:3000** and enjoy! 🎉

## 🎵 What You Can Do

### 1. Search for Songs
- Navigate to **/search**
- Try: "upbeat songs about love" or "slow acoustic ballads"
- Click "Play" on any song to stream it

### 2. BigFlavor Radio (DJ Mode)
- Navigate to **/radio**
- Chat with the AI DJ: "Play something upbeat"
- Request specific songs: "Play Here Comes A Regular"
- Create playlists: "Make me a workout playlist"

### 3. Admin Tools (Editor Role Only)
- Navigate to **/admin**
- Access to MCP tools for audio processing
- To grant yourself editor access:
  ```sql
  -- After first login, run this in psql:
  UPDATE users SET role = 'editor' WHERE email = 'your@email.com';
  ```

## 📁 What Was Created

```
big-flavor-band-agent/
├── backend_api.py              ← FastAPI server (port 8000)
├── requirements-api.txt        ← API dependencies (installed ✓)
├── start-backend.ps1          ← Helper script to start backend
├── start-frontend.ps1         ← Helper script to start frontend
├── GOOGLE_OAUTH_SETUP_GUIDE.md ← Detailed Google OAuth instructions
├── FRONTEND_SETUP.md          ← Complete technical documentation
└── frontend/                   ← Next.js application
    ├── app/                    ← Pages and API routes
    ├── components/            ← React components
    ├── lib/                   ← Database & auth utilities
    └── .env.local            ← Configuration (add Auth0 here!)
```

## 🔑 Environment Variables You Need to Set

Edit `frontend/.env.local` and replace these:

```env
# Get these from Google Cloud Console → APIs & Services → Credentials
GOOGLE_CLIENT_ID='your-client-id.apps.googleusercontent.com'
GOOGLE_CLIENT_SECRET='your-client-secret'
```

The other variables (database, API keys) are already configured from your existing `.env` file!

## 🛠️ Helper Scripts

I created two PowerShell scripts to make starting the servers easier:

### Start Backend
```powershell
.\start-backend.ps1
```
This will:
- Activate Python virtual environment
- Install dependencies if needed
- Start the FastAPI server

### Start Frontend
```powershell
.\start-frontend.ps1
```
This will:
- Install npm dependencies if needed
- Check for `.env.local`
- Start the Next.js dev server

## ❗ Common Issues

### Issue: "Backend API error"
**Solution**: Make sure backend is running in another terminal with `python backend_api.py`

### Issue: "Unauthorized" or login doesn't work
**Solution**:
1. Check Google OAuth configuration in `.env.local`
2. Make sure redirect URIs are correct in Google Console
3. Run the database migration (Step 2)

### Issue: Audio won't play
**Solution**: Make sure audio files exist in `../audio_library/` and match pattern `{id}_{title}.mp3`

### Issue: Can't access /admin
**Solution**: You need editor role. After first login, run:
```sql
psql -U bigflavor -d bigflavor
UPDATE users SET role = 'editor' WHERE email = 'your@email.com';
```

## 📊 Architecture Overview

```
┌─────────────────────────────────────────────────┐
│  Browser (http://localhost:3000)                │
│  ├─ Search Page                                 │
│  ├─ Radio Page (DJ Chat)                        │
│  └─ Admin Page (MCP Tools)                      │
└─────────────────┬───────────────────────────────┘
                  │
        ┌─────────┴─────────┐
        │   Next.js API     │  ← Google OAuth handles login
        │   Routes          │
        └─────────┬─────────┘
                  │
        ┌─────────┴─────────┐
        │  FastAPI Backend  │  ← You: python backend_api.py
        │  (Port 8000)      │
        └─────────┬─────────┘
                  │
        ┌─────────┴─────────┐
        │ BigFlavorAgent    │  ← Your existing agent
        │ (Claude AI)       │
        └─────────┬─────────┘
                  │
        ┌─────────┴─────────┬──────────────────┐
        │                   │                  │
   ┌────┴────┐      ┌──────┴──────┐   ┌──────┴──────┐
   │   RAG   │      │     MCP     │   │ PostgreSQL  │
   │ System  │      │   Server    │   │  Database   │
   └─────────┘      └─────────────┘   └─────────────┘
```

## 🎯 Next Steps

After getting it running:

1. **Try searching**: Test different natural language queries
2. **Chat with DJ**: See how the agent responds to requests
3. **Grant editor access**: Update your user role to access admin tools
4. **Customize**: Edit components in `frontend/components/` to customize the UI
5. **Deploy**: When ready, follow FRONTEND_SETUP.md for production deployment

## 📚 Documentation

- **GOOGLE_OAUTH_SETUP_GUIDE.md** - Step-by-step Google OAuth setup with troubleshooting
- **FRONTEND_SETUP.md** - Complete technical documentation
- **frontend/README.md** - Frontend-specific documentation

## 🎉 That's It!

You now have a full web application for BigFlavor Band Agent with:
- ✅ Natural language search
- ✅ AI DJ radio station
- ✅ Audio streaming
- ✅ Google authentication
- ✅ Role-based access control
- ✅ MCP tools for audio processing

Enjoy exploring your music library with AI! 🎵
