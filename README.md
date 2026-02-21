# DineQR

Real-time QR code-based restaurant ordering system.

## Features

- QR code generation for table ordering
- Real-time order updates via WebSockets
- Menu management
- Order tracking and management
- Bill generation and payment tracking
- Admin dashboard support

## Tech Stack

- **Backend**: FastAPI (Python)
- **Database**: PostgreSQL with SQLAlchemy (async)
- **Real-time**: WebSockets
- **Migrations**: Alembic

## Project Structure

```
dineQR/
├── backend/
│   ├── app/
│   │   ├── main.py          # FastAPI application entry point
│   │   ├── config.py        # Application settings
│   │   ├── database.py      # Database connection
│   │   ├── models/          # SQLAlchemy models
│   │   ├── schemas/         # Pydantic schemas
│   │   ├── routes/          # API routes
│   │   ├── websocket/       # WebSocket manager
│   │   └── utils/           # Utilities (logger, etc.)
│   ├── alembic/             # Database migrations
│   ├── requirements.txt
│   └── .env.example
└── README.md
```

## Setup

### Prerequisites

- Python 3.11+
- PostgreSQL

### Installation

1. Clone the repository:
   ```bash
   git clone <repository-url>
   cd dineQR
   ```

2. Create virtual environment and install dependencies:
   ```bash
   cd backend
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. Configure environment variables:
   ```bash
   cp .env.example .env
   ```
   Edit `.env` with your database credentials and secret key.

4. Run database migrations:
   ```bash
   alembic upgrade head
   ```

5. Start the server:
   ```bash
   uvicorn app.main:app --reload
   ```

## API Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /` | API status |
| `GET /health` | Health check |
| `WS /ws/admin` | Admin WebSocket connection |
| `WS /ws/table/{table_id}` | Table WebSocket connection |

## Environment Variables

| Variable | Description |
|----------|-------------|
| `DATABASE_URL` | PostgreSQL connection string |
| `SECRET_KEY` | Application secret key |
| `CORS_ORIGINS` | Allowed CORS origins (comma-separated) |

## License

MIT
