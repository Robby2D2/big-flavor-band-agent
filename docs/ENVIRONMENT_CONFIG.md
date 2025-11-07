# Environment Configuration

This project uses environment variables for configuration, including API keys and database credentials.

## Setup

1. **Copy the example file:**
   ```powershell
   Copy-Item .env.example .env
   ```

2. **Edit `.env` with your actual credentials:**
   - Add your API keys (OpenAI, Anthropic, Voyage)
   - Update database credentials if different from defaults

## Environment Variables

### API Keys
- `OPENAI_API_KEY` - Your OpenAI API key
- `ANTHROPIC_API_KEY` - Your Anthropic (Claude) API key
- `VOYAGE_API_KEY` - Your Voyage AI API key for embeddings

### Database Configuration
- `DB_HOST` - Database host (default: localhost)
- `DB_PORT` - Database port (default: 5432)
- `DB_NAME` - Database name (default: bigflavor)
- `DB_USER` - Database user (default: bigflavor)
- `DB_PASSWORD` - Database password

## Security Notes

⚠️ **Important:**
- Never commit your `.env` file to version control
- The `.env` file is already in `.gitignore`
- Use `.env.example` as a template for other developers
- Use different credentials for production environments

## Usage in Code

The application automatically loads environment variables using `python-dotenv`:

```python
from dotenv import load_dotenv
import os

load_dotenv()

# Access variables
api_key = os.getenv("OPENAI_API_KEY")
db_host = os.getenv("DB_HOST", "localhost")  # with default fallback
```

The `DatabaseManager` class automatically reads database credentials from environment variables, with sensible defaults for local development.
