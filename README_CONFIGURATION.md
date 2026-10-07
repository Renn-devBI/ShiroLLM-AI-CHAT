# Configuration System - Complete Documentation

Welcome! This document provides an overview of the new model configuration system for Shiro LLMA.

## What Changed?

The application now uses a **centralized configuration system** to manage AI models. Instead of hardcoding model paths in the code, all models are:
- Stored in a dedicated `/model` folder
- Managed via `model_config.json` 
- Switchable via the web interface

## Quick Links

Choose your role to find relevant documentation:

### 👤 Regular Users
Start here if you want to use the application:
- **[QUICKSTART.md](QUICKSTART.md)** - Get running in 2 minutes
- **[MODEL_CONFIG_README.md](MODEL_CONFIG_README.md)** - How to add/switch models

### 👨‍💻 Developers
Start here if you're contributing to the code:
- **[DEVELOPER_REFERENCE.md](DEVELOPER_REFERENCE.md)** - Architecture & API reference
- **[CHANGES_SUMMARY.md](CHANGES_SUMMARY.md)** - What was modified
- **[FILES_MODIFIED.md](FILES_MODIFIED.md)** - Line-by-line changes

### 🔍 System Administrators
Start here if you're deploying/managing the system:
- **[IMPLEMENTATION_COMPLETE.md](IMPLEMENTATION_COMPLETE.md)** - Implementation status
- **[FILES_MODIFIED.md](FILES_MODIFIED.md)** - Change summary
- **[verify_config.py](verify_config.py)** - Config validation script

---

## New System Architecture

### Before (Old System)
```
web.py
├── MODEL_PATH = "Lumimaid-v0.2-8B-Q5_K_M-imat.gguf"
│   (hardcoded in code)
│
└── Load model from root directory
```

### After (New System)
```
web.py
├── load_model_config()
│   └── reads from model_config.json
│
├── Load model from model/ folder
│
└── model_config.json
    ├── current_model: "model/Lumimaid-v0.2-8B-Q5_K_M-imat.gguf"
    └── available_models: [...]

model/
├── Llama-3.2-3B-Instruct-uncensored-Q6_K.gguf
├── Phi-3-mini-4k-instruct-q4.gguf
└── Lumimaid-v0.2-8B-Q5_K_M-imat.gguf
```

## Key Features

### ✨ Centralized Configuration
- Single JSON file manages all models
- No code changes needed to add/remove models
- Easy to backup and restore

### 📁 Organized Storage
- All models in dedicated `/model` folder
- Easy to find and manage
- Cleaner file structure

### 🔄 Hot Switching
- Switch models via web interface
- No server restart needed
- Real-time feedback

### 🛡️ Robust Validation
- Validates paths before loading
- Checks model files exist
- Graceful error handling

### 📚 Complete Documentation
- 5 user guides
- 2 developer guides
- 1 configuration reference
- 1 verification script

---

## Getting Started

### 1. Check Configuration
```bash
python verify_config.py
```

Expected output:
```
[OK] model_config.json is valid JSON
  Current model: model/Lumimaid-v0.2-8B-Q5_K_M-imat.gguf
  Available models: 3
    [OK] model/Llama-3.2-3B-Instruct-uncensored-Q6_K.gguf
    [OK] model/Phi-3-mini-4k-instruct-q4.gguf
    [OK] model/Lumimaid-v0.2-8B-Q5_K_M-imat.gguf
```

### 2. Start Application
```bash
python web.py
```

### 3. Open Web Interface
```
http://127.0.0.1:7474
```

### 4. Switch Models (Optional)
- Settings ⚙️ > Model tab
- Select model > Switch Model

---

## File Structure

```
Shiro-LLMA/
│
├── 📄 web.py                       ← Main application
├── 📄 model_config.json            ← Configuration ⭐ NEW
│
├── 📁 model/                       ← AI models (NEW)
│   ├── Llama-3.2-3B-...Q6_K.gguf
│   ├── Phi-3-mini-4k...q4.gguf
│   └── Lumimaid-v0.2-8B...gguf
│
├── 📁 static/
│   ├── script.js                   ← Updated
│   └── style.css
│
├── 📁 templates/
│   └── index.html                  ← Updated
│
├── 📁 profile/                     ← User profiles
│
├── 📖 README_CONFIGURATION.md      ← This file
├── 📖 QUICKSTART.md                ← Quick reference
├── 📖 MODEL_CONFIG_README.md       ← Configuration guide
├── 📖 CHANGES_SUMMARY.md           ← Change log
├── 📖 DEVELOPER_REFERENCE.md       ← Developer guide
├── 📖 IMPLEMENTATION_COMPLETE.md   ← Status report
├── 📖 FILES_MODIFIED.md            ← Detailed changes
│
├── 🔧 verify_config.py             ← Validation script
├── 🔧 ingatan_shiro.json           ← Chat history
├── 🔧 isekai_world.json            ← World config
│
└── 📋 requirements.txt              ← Dependencies
```

---

## Configuration File

### Location
```
d:\Shiro-LLMA\model_config.json
```

### Example
```json
{
  "current_model": "model/Lumimaid-v0.2-8B-Q5_K_M-imat.gguf",
  "available_models": [
    "model/Llama-3.2-3B-Instruct-uncensored-Q6_K.gguf",
    "model/Phi-3-mini-4k-instruct-q4.gguf",
    "model/Lumimaid-v0.2-8B-Q5_K_M-imat.gguf"
  ],
  "model_info": {
    "model/Lumimaid-v0.2-8B-Q5_K_M-imat.gguf": {
      "name": "Lumimaid-v0.2-8B",
      "size": "8B",
      "quantization": "Q5_K_M",
      "description": "High quality model"
    }
  }
}
```

### Fields
- **current_model**: Currently active model (full path)
- **available_models**: Array of all available model paths
- **model_info**: Optional metadata (for reference)

---

## Common Tasks

### Add a New Model
1. Copy `.gguf` file to `model/` folder
2. Edit `model_config.json`:
   ```json
   "available_models": [
     ...existing models...,
     "model/your-new-model.gguf"  ← Add this line
   ]
   ```
3. Restart application

### Switch Model via Web UI
1. Settings ⚙️ (top right)
2. Model tab
3. Select from dropdown
4. Click "Switch Model"

### Switch Model via Config
1. Edit `model_config.json`
2. Change `current_model` value
3. Restart application

### Verify Configuration
```bash
python verify_config.py
```

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| "Model not found" | Check model file in model/ folder |
| Model missing from dropdown | Restart browser (Ctrl+F5) |
| Config error | Check model_config.json JSON syntax |
| Slow loading | Large models take 10-30s to load |
| Server won't start | Run verify_config.py to check |

**For more help**: See QUICKSTART.md

---

## What Was Changed?

### Modified Files (3)
1. **web.py** - Model loading logic
2. **static/script.js** - Frontend UI
3. **templates/index.html** - Settings interface

### New Files (7)
1. **model_config.json** - Configuration ⭐
2. **MODEL_CONFIG_README.md** - Config guide
3. **QUICKSTART.md** - Quick reference
4. **CHANGES_SUMMARY.md** - Change log
5. **DEVELOPER_REFERENCE.md** - Dev guide
6. **IMPLEMENTATION_COMPLETE.md** - Status
7. **verify_config.py** - Validator script

**Detailed info**: See [FILES_MODIFIED.md](FILES_MODIFIED.md)

---

## API Endpoints

### Get Models
```bash
GET /api/models

Response:
{
  "current_model": "model/Lumimaid-v0.2-8B-Q5_K_M-imat.gguf",
  "available_models": [...]
}
```

### Switch Model
```bash
POST /api/models/switch

Request:
{"model": "model/Phi-3-mini-4k-instruct-q4.gguf"}

Response:
{
  "success": true,
  "message": "Model switched to Phi-3-mini-4k-instruct-q4",
  "current_model": "model/Phi-3-mini-4k-instruct-q4.gguf"
}
```

**Full API reference**: See [DEVELOPER_REFERENCE.md](DEVELOPER_REFERENCE.md)

---

## Model Information

Available models and their characteristics:

| Model | Size | Parameters | Speed | Quality |
|-------|------|------------|-------|---------|
| Llama-3.2-3B-Q6_K | 2.1 GB | 3B | ⚡⚡⚡ | ⭐⭐ |
| Phi-3-mini-Q4 | 2.4 GB | 3.8B | ⚡⚡⚡ | ⭐⭐ |
| Lumimaid-8B-Q5_K_M | 5.1 GB | 8B | ⚡⚡ | ⭐⭐⭐⭐ |

---

## System Requirements

- **Python**: 3.8+
- **RAM**: 4GB minimum (8GB recommended)
- **Storage**: 10GB for models
- **Disk Space**: Model size + 500MB

---

## Migration from Old System

If upgrading from previous version:

1. **Move models**
   ```
   From: d:\Shiro-LLMA\*.gguf (root)
   To:   d:\Shiro-LLMA\model\*.gguf
   ```

2. **Verify configuration**
   ```bash
   python verify_config.py
   ```

3. **Restart application**
   ```bash
   python web.py
   ```

---

## Questions & Support

- **How do I...?** → Check QUICKSTART.md
- **What changed?** → See CHANGES_SUMMARY.md
- **I'm a developer** → Read DEVELOPER_REFERENCE.md
- **Is something wrong?** → Run verify_config.py

---

## Version Info

- **Version**: 1.0
- **Release Date**: February 6, 2026
- **Status**: Production Ready ✅

---

## Documentation Index

```
README_CONFIGURATION.md (this file)
├── Quick Start
├── Getting Started
├── File Structure
├── Configuration Details
├── Common Tasks
├── Troubleshooting
├── API Reference
└── Support

QUICKSTART.md
├── Prerequisites
├── Startup
├── Configuration Location
├── Basic Operations
└── Troubleshooting

MODEL_CONFIG_README.md
├── Directory Structure
├── Configuration Guide
├── Adding Models
├── Switching Models
├── API Endpoints
└── FAQ

CHANGES_SUMMARY.md
├── Overview
├── Files Modified
├── How to Use
├── Technical Details
└── Next Steps

DEVELOPER_REFERENCE.md
├── Architecture
├── Components
├── Functions
├── API Details
├── Data Flow
├── Error Handling
├── Configuration Schema
├── Testing Guide
└── Security

FILES_MODIFIED.md
├── Modified Files (3)
├── New Files (7)
├── Summary
├── Verification
└── Impact Analysis

IMPLEMENTATION_COMPLETE.md
├── Summary
├── Verification Results
├── Key Features
├── Directory Structure
├── Usage Guide
└── Troubleshooting

verify_config.py
└── Configuration Validator
```

---

**Ready to start?** → See [QUICKSTART.md](QUICKSTART.md)

**Have a specific question?** Pick the guide that matches your role above.

---

*Last Updated: February 6, 2026*  
*Configuration System Version: 1.0*  
*All components verified and ready for production use.*
