# twim

Voice dictation settings web app (FastAPI + static JS): models, preferences, and dictation context.

## Features

- **Multi-user authentication** - Login, registration, per-user data isolation
- **Provider architecture** - Ollama, LM Studio, with scaffolding for cloud providers
- **Real-time streaming** - SSE-based streaming responses
- **Debug logging system** - Frontend/backend debug flags, log to server
- **Push notifications** - Per-user notifications with banner UI
- **Modern UI** - Clean, responsive interface with dark/light themes

## Quick Start

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Run the server** (from repo root `voice-dictation-mvp/`):
   ```bash
   ./start.sh
   ```
   API-only / reload: `./start.sh --skip-hotkey-agent`

3. **Open in browser:**
   ```
   http://localhost:8000
   ```

4. **Create your first account** and start chatting!

## Requirements

- Python 3.11+
- Ollama or LM Studio running locally (for LLM inference)

## Project Structure

```
twim/
├── app/
│   ├── main.py              # FastAPI app entry
│   ├── routers/             # API endpoints
│   │   ├── auth.py          # Authentication
│   │   ├── chat.py          # Chat + streaming
│   │   ├── models.py        # Model listing
│   │   ├── settings.py      # User settings
│   │   ├── client_log.py    # Frontend log receiver
│   │   └── notifications.py # Push notifications
│   ├── services/            # Business logic
│   │   ├── users.py         # User management
│   │   ├── storage.py       # File-based persistence
│   │   ├── ollama.py        # Ollama client
│   │   ├── lm_studio.py     # LM Studio client
│   │   └── providers.py     # Provider router
│   └── static/              # Frontend files
│       ├── index.html
│       ├── styles.css
│       └── js/
├── users/                   # Per-user data (gitignored)
├── logs/                    # Server logs (gitignored)
└── requirements.txt
```

## Configuration

### LLM Providers

Configure in Settings > Models:

- **Ollama**: Default URL `http://localhost:11434`
- **LM Studio**: Default URL `http://localhost:1234`

### Debug Flags

Enable/disable logging for specific features in Settings > Debug.

Logs are:
- Printed to server console with `[CLIENT]` prefix
- Written to `logs/twim_YYYYMMDD.log`

## API Endpoints

| Endpoint | Description |
|----------|-------------|
| `POST /api/auth/login` | User login |
| `POST /api/auth/register` | User registration |
| `GET /api/auth/me` | Current user info |
| `POST /api/chat` | Send message (SSE streaming) |
| `GET /api/models` | List available models |
| `GET /api/settings` | Get user settings |
| `PATCH /api/settings` | Update settings |
| `GET /api/notifications` | List notifications |
| `POST /api/notifications` | Add notification |
| `POST /api/log` | Receive frontend logs |

## Extending

This skeleton is designed to be extended. Key extension points:

1. **Add providers**: Extend `app/services/providers.py`
2. **Add features**: Create new routers in `app/routers/`
3. **Add UI components**: Extend `app/static/js/` and `index.html`

## License

MIT
