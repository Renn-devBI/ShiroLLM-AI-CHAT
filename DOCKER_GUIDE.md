# SHIRO Docker Guide

## Quick Start (Recommended)

### 1. Install Docker & Docker Compose
- **Windows:** Download [Docker Desktop](https://www.docker.com/products/docker-desktop)
- **After install:** Restart komputer

### 2. Run dengan Docker Compose (Simplest)
```powershell
cd D:\Shiro-LLMA
docker-compose up -d
```

That's it! ✅

**Akses:** http://localhost:7474

### 3. Stop Server
```powershell
docker-compose down
```

---

## Method 1: Docker Compose (RECOMMENDED)

### Start
```powershell
docker-compose up -d
```

### View Logs
```powershell
docker-compose logs -f shiro
```

### Stop
```powershell
docker-compose down
```

### Restart
```powershell
docker-compose restart
```

### Full Rebuild (jika ada perubahan code)
```powershell
docker-compose up --build -d
```

---

## Method 2: Manual Docker Build

### 1. Build Image
```powershell
docker build -t shiro-llma:latest .
```

### 2. Run Container
```powershell
docker run -d `
  -p 7474:7474 `
  -v "D:\Shiro-LLMA\model:/app/model" `
  -v "D:\Shiro-LLMA\ingatan_shiro.json:/app/ingatan_shiro.json" `
  -v "D:\Shiro-LLMA\isekai_world.json:/app/isekai_world.json" `
  -v "D:\Shiro-LLMA\profile:/app/profile" `
  --name shiro-llma `
  shiro-llma:latest
```

### 3. View Logs
```powershell
docker logs -f shiro-llma
```

### 4. Stop Container
```powershell
docker stop shiro-llma
docker rm shiro-llma
```

---

## Comparison: PowerShell vs Docker

### Traditional (PowerShell)
```powershell
cd D:\Shiro-LLMA
python -m venv venv
venv\Scripts\Activate
pip install -r requirements.txt
python web.py
```

**Pros:** Simple, direct control
**Cons:** Manual setup, version conflicts, dependency issues

### Docker (New Way)
```powershell
cd D:\Shiro-LLMA
docker-compose up -d
```

**Pros:** 
- ✅ One command to run
- ✅ Automatic environment setup
- ✅ No Python installed needed on PC
- ✅ Reproducible across machines
- ✅ Easy to stop/start/restart
- ✅ Auto-restart if crash
- ✅ Easy version management

**Cons:**
- Requires Docker Desktop (~2GB extra)

---

## File Structure

```
Shiro-LLMA/
├── Dockerfile                 # Image definition
├── docker-compose.yml        # Orchestration
├── .dockerignore             # Build exclusions
├── web.py
├── memory_manager_v2.py
├── requirements.txt
├── model/                    # 💾 Persisted (volume)
├── profile/                  # 💾 Persisted (volume)
├── ingatan_shiro.json        # 💾 Persisted (volume)
├── isekai_world.json         # 💾 Persisted (volume)
└── .cache/                   # 💾 Persisted (volume)
```

**💾 Volumes** = Data saved even if container is deleted

---

## Common Issues & Solutions

### Issue: "Docker is not recognized"
**Fix:** Restart PowerShell or computer after Docker install

### Issue: Port 7474 already in use
```powershell
# Stop the service using port 7474
netstat -ano | findstr :7474

# Kill the process
taskkill /PID <PID> /F

# Or change port in docker-compose.yml:
# ports:
#   - "8080:7474"
```

### Issue: Container exits immediately
```powershell
docker-compose logs shiro
# Check error message
```

### Issue: Model not found in container
**Fix:** Make sure model files are in `model/` folder on your PC
```powershell
ls D:\Shiro-LLMA\model\
```

### Issue: Memory not persisting
**Fix:** Check volumes in docker-compose.yml - paths must match your PC

---

## Performance Tips

### 1. Resource Limits (Optional)
Edit `docker-compose.yml`:
```yaml
deploy:
  resources:
    limits:
      cpus: '4'        # Max 4 CPU cores
      memory: 8G       # Max 8GB RAM
```

### 2. GPU Support (Advanced)
If you have NVIDIA GPU:
```yaml
services:
  shiro:
    runtime: nvidia
    environment:
      - NVIDIA_VISIBLE_DEVICES=all
```

### 3. Health Monitoring
```powershell
docker-compose ps
# Shows container status

docker stats shiro-llma
# Shows CPU, memory, network usage
```

---

## Updating/Rebuilding

### If you changed code:
```powershell
docker-compose up --build -d
```

### If you changed requirements.txt:
```powershell
docker-compose down
docker-compose up --build -d
```

### If you want fresh start:
```powershell
docker-compose down -v
docker-compose up -d
```

---

## Production vs Development

### Development (Current)
```powershell
docker-compose up -d
```
- Auto-restart on crash
- Keeps data in volumes
- Easy to monitor with logs

### Production (Future)
```yaml
# Add to docker-compose.yml
services:
  shiro:
    restart: always
    deploy:
      resources:
        limits:
          memory: 16G
```

---

## Troubleshooting Commands

```powershell
# Show running containers
docker ps

# Show all containers (including stopped)
docker ps -a

# View container logs
docker logs shiro-llma

# Follow logs in real-time
docker logs -f shiro-llma

# Execute command in running container
docker exec -it shiro-llma python -c "..."

# Copy file from container
docker cp shiro-llma:/app/ingatan_shiro.json ./

# Check container stats
docker stats shiro-llma

# Inspect container details
docker inspect shiro-llma

# Remove image
docker rmi shiro-llma:latest

# Remove all unused images
docker image prune -a
```

---

## Switching Between Methods

### From PowerShell to Docker:
```powershell
# Stop PowerShell version
Ctrl+C

# Start Docker version
docker-compose up -d
```

**Data persists** - Your memory & profiles are in volumes!

### From Docker to PowerShell:
```powershell
# Stop Docker
docker-compose down

# Start PowerShell version
venv\Scripts\Activate
python web.py
```

---

## Useful Docker Commands Cheat Sheet

| Command | Purpose |
|---------|---------|
| `docker-compose up -d` | Start service |
| `docker-compose down` | Stop service |
| `docker-compose logs -f` | View logs |
| `docker-compose restart` | Restart |
| `docker-compose ps` | Show status |
| `docker exec -it shiro-llma bash` | Enter container shell |

---

## Next Steps

1. **Install Docker Desktop** if not already installed
2. **Test with:** `docker-compose up -d`
3. **Access:** http://localhost:7474
4. **Monitor:** `docker-compose logs -f`
5. **Stop:** `docker-compose down`

That's it! Much simpler than PowerShell activation! ✨
