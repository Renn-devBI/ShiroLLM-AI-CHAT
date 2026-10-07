# SHIRO Docker - Quick Start

## 30-Second Setup

### Windows (PowerShell)
```powershell
# 1. Install Docker Desktop (one-time only)
# Download from: https://www.docker.com/products/docker-desktop

# 2. Start SHIRO
docker-compose up -d

# 3. Open browser
# http://localhost:7474

# 4. To stop
docker-compose down
```

### Linux / Mac
```bash
# 1. Install Docker
# https://docs.docker.com/install/

# 2. Start SHIRO
docker-compose up -d

# 3. Open browser
# http://localhost:7474

# 4. To stop
docker-compose down
```

---

## What Just Happened?

Docker automatically:
✅ Created isolated environment
✅ Installed Python 3.11
✅ Installed all dependencies (llama-cpp-python, Flask, etc)
✅ Started web.py
✅ Made it accessible at http://localhost:7474
✅ Set up auto-restart if it crashes

---

## Using PowerShell Helper Script (Windows)

```powershell
# Make script executable first-time only:
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser

# Now you can use:
.\run-docker.ps1              # Start
.\run-docker.ps1 logs         # View logs
.\run-docker.ps1 stop         # Stop
.\run-docker.ps1 restart      # Restart
.\run-docker.ps1 status       # Show status
.\run-docker.ps1 build        # Rebuild after code changes
```

---

## Using Bash Helper Script (Linux/Mac)

```bash
# Make executable first-time only:
chmod +x run-docker.sh

# Now you can use:
./run-docker.sh              # Start
./run-docker.sh logs         # View logs
./run-docker.sh stop         # Stop
./run-docker.sh restart      # Restart
./run-docker.sh status       # Show status
./run-docker.sh build        # Rebuild after code changes
```

---

## Data Persistence

Your data is saved even if container restarts:
- 💾 `ingatan_shiro.json` - Memory/conversations
- 💾 `isekai_world.json` - World settings
- 💾 `model/` - AI model files
- 💾 `profile/` - User/AI profiles

All these are **automatically backed up** on your PC!

---

## Troubleshooting

### "docker: command not found"
→ Docker Desktop not installed. Download from: https://www.docker.com/products/docker-desktop

### "Address already in use"
→ Port 7474 is busy. Stop the service or use different port:
```yaml
# In docker-compose.yml, change:
ports:
  - "8080:7474"  # Use 8080 instead
```

### "Container keeps stopping"
```powershell
docker-compose logs shiro
# Shows error message
```

### "Model not loading"
Check that model files exist:
```powershell
ls model\
# Should show .gguf files
```

---

## Docker vs Traditional Comparison

| Feature | Docker | Traditional |
|---------|--------|-------------|
| Setup time | 30 seconds | 10 minutes |
| Activation command | None | venv\Scripts\Activate |
| Python install needed | No | Yes |
| Reproducible | Always | Sometimes |
| Auto-restart | Yes | No |
| Stop/Start | 1 second | Manual |

---

## Common Commands Reference

```powershell
# Start in background
docker-compose up -d

# Stop
docker-compose down

# View status
docker-compose ps

# View logs (follow in real-time)
docker-compose logs -f shiro

# Restart
docker-compose restart

# Full rebuild (after code changes)
docker-compose up --build -d

# Remove everything and start fresh
docker-compose down -v
docker-compose up -d
```

---

## Next Steps

1. ✅ Install Docker Desktop
2. ✅ Run `docker-compose up -d`
3. ✅ Access http://localhost:7474
4. ✅ Enjoy! No more venv activation needed!

---

## Still Prefer Traditional?

That's fine! You can still use PowerShell:
```powershell
venv\Scripts\Activate
python web.py
```

Both methods work! Just pick one. 🎯
