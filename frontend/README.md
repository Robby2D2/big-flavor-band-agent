# BigFlavor Band Agent - Frontend

A Next.js web application for discovering and streaming music from the BigFlavor Band library, powered by AI.

## Features

### 1. Search Interface
- Natural language search using Claude AI agent
- Agent interprets queries and uses appropriate search tools
- Search by mood, tempo, genre, lyrics, or any combination
- Display search results with song metadata and similarity scores

### 2. Authentication (Auth0)
- Google OAuth integration
- Role-based access control (Listener, Editor, Admin)
- Secure user sessions

### 3. Audio Streaming
- Stream MP3 files directly from the audio library
- Full-featured audio player with play/pause, seek, and volume controls
- Support for range requests (partial content streaming)

### 4. BigFlavor Radio (DJ Mode)
- Chat with AI DJ to request songs
- Create custom playlists based on mood or criteria
- Real-time playlist management
- Interactive conversational interface

### 5. Admin Tools (Editor Access)
- Access to MCP tools for audio processing
- Tools include:
  - Audio analysis (tempo, key detection)
  - Audio editing (trim, noise reduction, pitch correction)
  - Mastering and effects
  - DJ transitions
- Real-time tool execution and results

## Tech Stack

- **Framework**: Next.js 16 (App Router)
- **Language**: TypeScript
- **Styling**: Tailwind CSS
- **Authentication**: Auth0 (with Google provider)
- **Database**: PostgreSQL with pg driver
- **State Management**: React hooks + Zustand (optional)
- **HTTP Client**: Fetch API + Axios

## Project Structure

```
frontend/
├── app/
│   ├── api/              # API routes (proxy to Python backend)
│   │   ├── auth/         # Auth0 authentication
│   │   ├── search/       # Search endpoints
│   │   ├── audio/        # Audio streaming
│   │   ├── agent/        # Agent chat
│   │   └── tools/        # MCP tools for editors
│   ├── search/           # Search page
│   ├── radio/            # DJ Radio page
│   ├── admin/            # Admin tools page
│   ├── layout.tsx        # Root layout
│   ├── page.tsx          # Home page
│   └── globals.css       # Global styles
├── components/           # Reusable React components
│   ├── SearchBar.tsx
│   ├── SongList.tsx
│   └── AudioPlayer.tsx
├── lib/                  # Utility libraries
│   ├── db.ts            # PostgreSQL connection
│   └── auth.ts          # Auth helpers and role checking
├── public/              # Static assets
└── package.json
```

## Setup Instructions

### Prerequisites

1. Node.js 18+ installed
2. PostgreSQL database running (see parent README)
3. Python backend API running (see backend_api.py)
4. Auth0 account with Google social connection

### 1. Install Dependencies

```bash
cd frontend
npm install
```

### 2. Configure Environment Variables

Copy `.env.example` to `.env.local` and fill in the values:

```bash
cp .env.example .env.local
```

Required environment variables:

```env
# Auth0 Configuration
AUTH0_SECRET='generate with: openssl rand -hex 32'
AUTH0_BASE_URL='http://localhost:3000'
AUTH0_ISSUER_BASE_URL='https://YOUR_DOMAIN.auth0.com'
AUTH0_CLIENT_ID='your_client_id'
AUTH0_CLIENT_SECRET='your_client_secret'

# Database
DB_HOST=localhost
DB_PORT=5432
DB_NAME=bigflavor
DB_USER=bigflavor
DB_PASSWORD=your_password

# API Keys
ANTHROPIC_API_KEY=your_anthropic_api_key

# Backend API
AGENT_API_URL=http://localhost:8000

# Audio Library
AUDIO_LIBRARY_PATH=../audio_library
```

### 3. Set Up Auth0

1. Create an Auth0 account at https://auth0.com
2. Create a new Application (Regular Web Application)
3. Configure allowed callback URLs:
   - `http://localhost:3000/api/auth/callback`
4. Configure allowed logout URLs:
   - `http://localhost:3000`
5. Enable Google Social Connection in Auth0 dashboard
6. Copy the Domain, Client ID, and Client Secret to `.env.local`

### 4. Run Database Migrations

Run the user tables migration:

```bash
cd ..
psql -U bigflavor -d bigflavor -f database/sql/migrations/05-create-users-table.sql
```

### 5. Start the Backend API

In a separate terminal, start the Python FastAPI backend:

```bash
cd ..
python backend_api.py
```

The backend API will run on http://localhost:8000

### 6. Start the Development Server

```bash
npm run dev
```

The frontend will be available at http://localhost:3000

## Usage

### For Listeners (Default Role)

1. **Home Page**: Navigate to `/` to see the overview
2. **Search**: Go to `/search` to search for songs using natural language
3. **Radio**: Go to `/radio` to chat with the AI DJ and create playlists

### For Editors

1. **Admin Tools**: Go to `/admin` to access MCP tools for audio processing
2. All listener features are also available

### For Admins

- All features available
- Can manage user roles in the database

## API Endpoints

### Authentication
- `GET /api/auth/login` - Login with Auth0
- `GET /api/auth/logout` - Logout
- `GET /api/auth/callback` - Auth0 callback
- `GET /api/auth/me` - Get current user

### Search
- `POST /api/search` - Natural language search (requires auth)

### Audio
- `GET /api/audio/[songId]` - Stream audio file (requires auth)

### Agent
- `POST /api/agent/chat` - Chat with agent (requires auth)

### Tools (Editor only)
- `GET /api/tools` - List available MCP tools
- `POST /api/tools` - Execute an MCP tool

## Role-Based Access Control

### Roles
- **Listener**: Can search, stream music, and use radio
- **Editor**: All listener permissions + access to MCP tools
- **Admin**: All permissions + user management

### Updating User Roles

Connect to the database and update the user's role:

```sql
UPDATE users SET role = 'editor' WHERE email = 'user@example.com';
```

## Development

### Running Tests
```bash
npm run test
```

### Building for Production
```bash
npm run build
npm start
```

### Linting
```bash
npm run lint
```

## Architecture

### Frontend → Backend Flow

1. User interacts with Next.js frontend
2. Frontend API routes authenticate user (Auth0)
3. Frontend API routes proxy requests to Python FastAPI backend
4. Python backend uses BigFlavorAgent to process requests
5. Agent uses RAG system and MCP tools to fulfill requests
6. Results returned through the chain back to user

### Authentication Flow

1. User clicks login → redirected to Auth0
2. User authenticates with Google
3. Auth0 redirects back to app with session
4. App creates/updates user record in PostgreSQL
5. User's role determines access permissions

## Troubleshooting

### "Unauthorized" errors
- Make sure you're logged in
- Check that Auth0 is configured correctly
- Verify `.env.local` has correct Auth0 credentials

### "Backend API error"
- Ensure Python backend is running on port 8000
- Check `AGENT_API_URL` in `.env.local`
- Verify Python dependencies are installed

### Audio not playing
- Check that audio files exist in `../audio_library`
- Verify `AUDIO_LIBRARY_PATH` in `.env.local`
- Check browser console for errors

### Database connection errors
- Ensure PostgreSQL is running
- Verify database credentials in `.env.local`
- Run migrations if user table doesn't exist

## Contributing

1. Create a feature branch
2. Make your changes
3. Test thoroughly
4. Submit a pull request

## License

See parent project LICENSE file.
