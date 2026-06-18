# IXOPE Server

FastAPI backend for the IXOPE medical imaging system.

## Architecture

```
IXOPE Device → FastAPI (/api/upload, /api/upload1) → PostgreSQL + File Storage
React Portal → FastAPI (/api/images, /api/videos, /api/patients) → PostgreSQL
```

## Quick Start (Development)

### 1. Start PostgreSQL with Docker

```bash
docker compose up db -d
```

### 2. Install Python deps

```bash
pip install -r requirements.txt
```

### 3. Run the server

```bash
python run.py
```

Server starts at http://localhost:8000  
API docs at http://localhost:8000/docs

## Production (Docker Compose)

```bash
docker compose up -d
```

This starts:
- **PostgreSQL** on port 5432
- **FastAPI** on port 8000 (4 workers)
- **Nginx** on port 80 (serves React build + proxies API)

## API Endpoints

### Upload (from IXOPE device)
- `POST /api/upload?id=1001&scope=derm` — Upload image
- `POST /api/upload1?id=1001&scope=derm` — Upload video

### Images
- `GET /api/images?device_id=1001&scope=derm&date_from=2025-01-01&date_to=2025-12-31`
- `GET /api/images?patient_id=P001`
- `GET /api/images/{id}/file` — Serve image file
- `DELETE /api/images/{id}`

### Videos
- `GET /api/videos?device_id=1001&scope=opth`
- `GET /api/videos/{id}/file` — Serve video file
- `DELETE /api/videos/{id}`

### Patients
- `POST /api/patients` — Create patient
- `GET /api/patients?search=John`
- `GET /api/patients/{patient_id}`
- `PATCH /api/patients/{patient_id}`
- `DELETE /api/patients/{patient_id}`

### Devices
- `POST /api/devices/heartbeat` — Device reports online
- `GET /api/devices` — List all devices
- `GET /api/devices/{device_id}` — Device status + stats

### Health
- `GET /health` — Server health check

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| DATABASE_URL | postgresql+asyncpg://ixope:ixope123@localhost:5432/ixope_db | PostgreSQL connection |
| API_PORT | 8000 | Server port |
| UPLOAD_DIR | ./uploads | File storage path |
| MAX_FILE_SIZE_MB | 100 | Max upload size |
| CORS_ORIGINS | http://localhost:3000 | Allowed origins |
