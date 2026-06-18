# IXOPE Server — VPS Deployment Guide

## Server: 118.139.167.201 (Ubuntu/Debian Linux)

---

## Step 1: SSH into VPS

```bash
ssh root@118.139.167.201
```

---

## Step 2: Install Docker & Docker Compose

```bash
# Update system
apt update && apt upgrade -y

# Install Docker
curl -fsSL https://get.docker.com | sh

# Start Docker
systemctl enable docker
systemctl start docker

# Verify
docker --version
docker compose version
```

---

## Step 3: Install Git & Clone Repo

```bash
# Install git
apt install git -y

# Create project directory
mkdir -p /opt/ixope && cd /opt/ixope

# Clone the server repo
git clone https://github.com/infiniti-ixope/ixope-server.git .
```

Or copy files manually via SCP from your local machine:
```bash
scp -r d:\infiniti\medical\ixope_server\* root@118.139.167.201:/opt/ixope/
```

---

## Step 4: Configure Environment

```bash
cd /opt/ixope

# Edit .env for production
nano .env
```

Set these values:
```env
DATABASE_URL=postgresql+asyncpg://ixope:ixope123@db:5432/ixope_db
API_HOST=0.0.0.0
API_PORT=8001
DEBUG=false
UPLOAD_DIR=/app/uploads
MAX_FILE_SIZE_MB=100
CORS_ORIGINS=https://ixope-hub.com,https://api.ixope-hub.com
SECRET_KEY=generate-a-strong-random-key-here
REDIS_URL=redis://redis:6379/1
```

Generate a strong secret key:
```bash
openssl rand -hex 32
```

---

## Step 5: Update Docker Compose for Production

The `docker-compose.yml` is already configured. Verify the port mapping:
- PostgreSQL: internal only (no external port exposed)
- Redis: internal only
- API: port 8001
- Nginx: port 80

---

## Step 6: Start All Services

```bash
cd /opt/ixope
docker compose up -d
```

Check status:
```bash
docker compose ps
docker compose logs -f api
```

---

## Step 7: Verify

```bash
# Health check
curl http://localhost:8001/health

# Should return: {"status":"ok","service":"ixope-server"}

# Test from outside
curl https://api.ixope-hub.com/health
```

---

## Step 8: Install ffmpeg (for video thumbnails)

```bash
# Install ffmpeg inside the API container
docker exec ixope_api apt-get update && docker exec ixope_api apt-get install -y ffmpeg
```

Or add to Dockerfile (already included):
```dockerfile
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg
```

---

## Step 9: Setup Firewall

```bash
# Allow only necessary ports
ufw allow 22      # SSH
ufw allow 80      # Nginx (Cloudflare connects here)
ufw allow 443     # HTTPS (if needed)
ufw enable

# Block direct access to API port from outside (Cloudflare handles it)
# Port 8001 should only be accessible via Nginx
```

---

## Step 10: Auto-restart on Reboot

Docker compose with `restart: unless-stopped` handles this automatically.
Verify:
```bash
docker update --restart unless-stopped ixope_api ixope_db ixope_redis ixope_nginx
```

---

## Useful Commands

```bash
# View logs
docker compose logs -f api
docker compose logs -f db

# Restart all services
docker compose restart

# Rebuild after code change
docker compose build api
docker compose up -d api

# Database shell
docker exec -it ixope_db psql -U ixope -d ixope_db

# Redis shell
docker exec -it ixope_redis redis-cli

# Check disk usage
df -h
du -sh /opt/ixope/uploads/

# Backup database
docker exec ixope_db pg_dump -U ixope ixope_db > backup_$(date +%Y%m%d).sql
```

---

## Update Deployment

```bash
cd /opt/ixope
git pull origin main
docker compose build api
docker compose up -d api
```

---

## Architecture on VPS

```
Internet → Cloudflare (SSL) → VPS:80 (Nginx) → API:8001 (FastAPI)
                                                    ↓
                                              PostgreSQL:5432
                                              Redis:6379
                                              /uploads/ (files)
```
