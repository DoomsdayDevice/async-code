# Flask Backend (Async Code)

Flask API with CORS and Postgres persistence.

## Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Configure database (Postgres):
   Set environment variables in `.env` (see below). Defaults for docker-compose:
   ```bash
   DB_HOST=postgres
   DB_PORT=5432
   DB_NAME=asynccode
   DB_USER=asynccode
   DB_PASSWORD=asynccode
   ```

3. Run the application:
```bash
python main.py
```

The app will run on `http://localhost:5000`

## API Endpoints

- **GET /**: Root endpoint with app info
- **GET /ping**: Health check endpoint that returns "pong"

## Environment

Create `.env` from `.env.example` and set:
```bash
ANTHROPIC_API_KEY=...
FLASK_ENV=development
FLASK_DEBUG=True
PORT=8000
DOCKER_HOST=unix:///var/run/docker.sock

# Postgres
DB_HOST=postgres
DB_PORT=5432
DB_NAME=asynccode
DB_USER=asynccode
DB_PASSWORD=asynccode
# Or DATABASE_URL=postgresql://asynccode:asynccode@postgres:5432/asynccode
```