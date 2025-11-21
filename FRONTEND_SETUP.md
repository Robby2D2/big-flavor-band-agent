# BigFlavor Band Agent - Frontend Setup Guide

This guide will walk you through setting up the complete BigFlavor Band Agent web application.

## Overview

The BigFlavor Band Agent now has a web frontend that includes:

1. **Search Interface** - Natural language search for songs
2. **Google OAuth Authentication** - Direct Google sign-in with role-based access
3. **BigFlavor Radio** - AI DJ that creates playlists and takes requests
4. **Audio Streaming** - Stream music directly from the library
5. **Admin Tools** - MCP tools for audio processing (Editor role required)

## Architecture

```
┌─────────────────┐
│   Next.js       │
│   Frontend      │
│  (Port 3000)    │
└────────┬────────┘
         │
         ├─── Google OAuth (Authentication)
         │
         ├─── PostgreSQL (User data, songs)
         │
         └─── FastAPI Backend ───┐
              (Port 8000)         │
                                  ├─── BigFlavorAgent (Claude AI)
                                  ├─── RAG System (Search)
                                  └─── MCP Server (Audio processing)
```

## Quick Start

### 1. Database Setup

Run the user tables migration:

```bash
# From project root
psql -U bigflavor -d bigflavor -f database/sql/migrations/05-create-users-table.sql
```

### 2. Install Frontend Dependencies

```bash
cd frontend
npm install
```

### 3. Install Backend API Dependencies

```bash
cd ..
pip install -r requirements-api.txt
```

### 4. Configure Google OAuth

#### Create Google OAuth Credentials

1. Go to https://console.cloud.google.com/
2. Create a new project or select existing one
3. Navigate to **APIs & Services** → **OAuth consent screen**:
   - Select External user type
   - Fill in app name and emails
   - Add scopes: openid, email, profile
4. Navigate to **APIs & Services** → **Credentials**:
   - Click **Create Credentials** → **OAuth client ID**
   - Application type: Web application
   - Authorized JavaScript origins: `http://localhost:3000`
   - Authorized redirect URIs: `http://localhost:3000/api/auth/callback`
5. Copy the Client ID and Client Secret

#### Configure Environment

Update `frontend/.env.local` with your Google credentials:

```env
GOOGLE_CLIENT_ID='your-client-id.apps.googleusercontent.com'
GOOGLE_CLIENT_SECRET='your-client-secret'
```

### 5. Start the Application

#### Terminal 1: Start Python Backend API

```bash
# From project root
python backend_api.py
```

Backend will run on http://localhost:8000

#### Terminal 2: Start Next.js Frontend

```bash
cd frontend
npm run dev
```

Frontend will run on http://localhost:3000

### 6. Access the Application

Open http://localhost:3000 in your browser.

## User Roles

### Default Role: Listener
- Search for songs
- Stream music
- Use BigFlavor Radio (DJ)

### Editor Role
- All Listener features
- Access to Admin Tools (MCP tools for audio processing)

### Admin Role
- All features
- User management capabilities

### Granting Editor Access

To grant a user editor access, update their role in the database:

```sql
-- After user logs in for the first time
UPDATE users SET role = 'editor' WHERE email = 'user@example.com';
```

## Features Guide

### 1. Natural Language Search

Navigate to **/search** and try queries like:
- "upbeat songs about love"
- "slow acoustic ballads"
- "songs with guitar solos in A minor"
- "fast tempo rock songs from 2023"

The agent will interpret your query and use the appropriate search tools.

### 2. BigFlavor Radio (DJ Mode)

Navigate to **/radio** to:
- Chat with the AI DJ
- Request specific songs
- Ask for playlist recommendations
- Get song suggestions based on mood

Example requests:
- "Play something upbeat"
- "I want a chill playlist"
- "Play 'Here Comes A Regular'"
- "Create a workout playlist"

### 3. Audio Player

Click "Play" on any song to:
- Stream the song
- Control playback (play/pause, seek)
- Adjust volume
- See song information

### 4. Admin Tools (Editors Only)

Navigate to **/admin** to access MCP tools:
- **Search Tools**: Audio similarity, text search, lyrics search
- **Audio Analysis**: Tempo, key, beat detection
- **Audio Editing**: Trim, noise reduction, pitch correction
- **Mastering**: Normalization, EQ, compression
- **DJ Tools**: Beat-matched transitions, tempo matching

## API Documentation

### Backend API (Python FastAPI)

The backend API runs on port 8000 and provides:

- `GET /` - Health check
- `POST /api/search/natural` - Natural language search
- `POST /api/search/text` - Text-based semantic search
- `POST /api/search/lyrics` - Lyrics keyword search
- `POST /api/agent/chat` - Chat with agent
- `POST /api/agent/dj/request` - DJ song request
- `POST /api/agent/dj/playlist` - Create playlist
- `GET /api/audio/stream/{song_id}` - Stream audio file
- `GET /api/tools/list` - List MCP tools
- `POST /api/tools/execute` - Execute MCP tool

API documentation available at: http://localhost:8000/docs

### Frontend API Routes (Next.js)

The frontend provides authenticated API routes:

- `GET /api/auth/*` - Auth0 authentication
- `POST /api/search` - Search songs (requires auth)
- `GET /api/audio/[songId]` - Stream audio (requires auth)
- `POST /api/agent/chat` - Chat with agent (requires auth)
- `GET /api/tools` - List tools (requires editor role)
- `POST /api/tools` - Execute tool (requires editor role)

## Database Schema

### Users Table

```sql
CREATE TABLE users (
    id VARCHAR(255) PRIMARY KEY,  -- Google user ID
    email VARCHAR(255) NOT NULL UNIQUE,
    name VARCHAR(255),
    picture TEXT,
    role VARCHAR(50) NOT NULL DEFAULT 'listener',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
```

### User Activity

```sql
CREATE TABLE user_activity (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) REFERENCES users(id),
    activity_type VARCHAR(100) NOT NULL,
    activity_data JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
```

### User Favorites

```sql
CREATE TABLE user_favorites (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) REFERENCES users(id),
    song_id INTEGER REFERENCES songs(id),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
```

## Troubleshooting

### Google OAuth Issues

**Problem**: "Access denied" after login
- Verify redirect URIs are correctly configured in Google Console
- If app is in testing mode, ensure your email is added as a test user
- Ensure `.env.local` has correct Google credentials

**Problem**: Login redirect loop
- Clear browser cookies and cache
- Verify redirect URI matches exactly (including trailing slashes)
- Check for CORS issues in browser console

### Backend Connection Issues

**Problem**: "Backend API error"
- Ensure Python backend is running: `python backend_api.py`
- Check `AGENT_API_URL` in `frontend/.env.local`
- Verify CORS is allowing localhost:3000

### Audio Streaming Issues

**Problem**: Songs won't play
- Verify audio files exist in `audio_library/`
- Check file naming: `{song_id}_{title}.mp3`
- Check browser console for 404 errors
- Ensure `AUDIO_LIBRARY_PATH` is correct in `.env.local`

### Database Issues

**Problem**: "User not found" errors
- Run user migration: `psql -U bigflavor -d bigflavor -f database/sql/migrations/05-create-users-table.sql`
- Verify database connection in `.env.local`
- Check PostgreSQL is running

### Performance Issues

**Problem**: Slow search results
- The agent needs time to process natural language queries
- Consider adding caching for common searches
- Ensure database indexes are created

## Development Tips

### Hot Reload

Both the frontend and backend support hot reload:
- Frontend: Automatic with Next.js
- Backend: Use `uvicorn backend_api:app --reload`

### Debugging

**Frontend**:
- Check browser console (F12)
- Use React DevTools
- Check Network tab for API calls

**Backend**:
- Check terminal output where `backend_api.py` is running
- Visit http://localhost:8000/docs for interactive API testing
- Enable debug logging in FastAPI

### Testing Auth Without Auth0

For development, you can temporarily bypass auth by modifying `lib/auth.ts`:

```typescript
// Development mode - bypass auth (REMOVE IN PRODUCTION!)
export async function getCurrentUser(): Promise<User | null> {
  return {
    id: 'dev-user',
    email: 'dev@example.com',
    name: 'Dev User',
    role: UserRole.ADMIN,
    created_at: new Date(),
  };
}
```

**WARNING**: Remove this before deploying to production!

## Production Deployment

### Environment Variables

For production, update:

```env
AGENT_API_URL='https://your-api-domain.com'
```

And in Google Console, add your production URLs:
- Authorized JavaScript origins: `https://your-domain.com`
- Authorized redirect URIs: `https://your-domain.com/api/auth/callback`

### Security Checklist

- [ ] Enable HTTPS for both frontend and backend
- [ ] Update CORS settings in backend to only allow your domain
- [ ] Set up proper database credentials (not default dev password)
- [ ] Enable rate limiting on API endpoints
- [ ] Set up monitoring and logging
- [ ] Publish Google OAuth app (if allowing any Google user to sign in)

### Deployment Options

**Frontend (Next.js)**:
- Vercel (recommended for Next.js)
- Netlify
- Docker container

**Backend (FastAPI)**:
- Docker container
- AWS ECS/Fargate
- Google Cloud Run
- Heroku

**Database**:
- AWS RDS
- Google Cloud SQL
- DigitalOcean Managed PostgreSQL

## Next Steps

### Potential Enhancements

1. **User Features**:
   - Save favorite songs
   - Create and share playlists
   - Listening history
   - Song ratings and reviews

2. **DJ Features**:
   - Queue management
   - Skip/previous track controls
   - Auto-play next song
   - Shuffle mode

3. **Social Features**:
   - Share playlists with other users
   - Collaborative playlists
   - Comments on songs
   - User profiles

4. **Admin Features**:
   - User management UI
   - Analytics dashboard
   - Batch audio processing
   - Upload new songs

5. **Performance**:
   - Redis caching
   - CDN for audio files
   - Server-side pagination
   - Optimistic UI updates

## Support

For issues or questions:
1. Check this documentation
2. Review the code comments
3. Check Google OAuth documentation: https://developers.google.com/identity/protocols/oauth2
4. Check Next.js documentation: https://nextjs.org/docs

## License

See parent project LICENSE file.
