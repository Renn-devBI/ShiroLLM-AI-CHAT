# -*- coding: utf-8 -*-
"""
Global Configuration & Environment Setup for Shiro LLMA
"""

import os
from pathlib import Path

# Base directories
BASE_DIR = Path(__file__).resolve().parent.parent

# Files & Storage Paths
MEMORY_FILE = os.environ.get("SHIRO_MEMORY_FILE", "ingatan_shiro.json")
WORLD_FILE = os.environ.get("SHIRO_WORLD_FILE", "isekai_world.json")
PROFILE_DIR = os.environ.get("SHIRO_PROFILE_DIR", "profile")
MODEL_DIR = os.environ.get("SHIRO_MODEL_DIR", "model")
MODEL_CONFIG_FILE = os.environ.get("SHIRO_MODEL_CONFIG", "model_config.json")
API_KEY_FILE = os.environ.get("SHIRO_API_KEY_FILE", "api_key.json")
TRAINING_DIR = os.environ.get("SHIRO_TRAINING_DIR", "training_data")
MEMORY_TEMPLATE_FILE = str(BASE_DIR / "data" / "templates" / "ingatan_shiro.template.json")

# Model & Context Parameters
CONTEXT_SIZE = int(os.environ.get("SHIRO_CONTEXT_SIZE", "4096"))
DEFAULT_TEMPERATURE = float(os.environ.get("SHIRO_TEMPERATURE", "0.7"))
DEFAULT_TOP_P = float(os.environ.get("SHIRO_TOP_P", "0.9"))
DEFAULT_MAX_TOKENS = int(os.environ.get("SHIRO_MAX_TOKENS", "350"))

# Google Drive Automatic Detection (Google Colab)
DRIVE_DIR = os.environ.get("SHIRO_DRIVE_DIR")
if not DRIVE_DIR and os.path.exists("/content/drive/MyDrive/Shiro_Memory"):
    DRIVE_DIR = "/content/drive/MyDrive/Shiro_Memory"
