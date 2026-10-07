#!/usr/bin/env python
# -*- coding: utf-8 -*-
import json
import os
import sys

sys.stdout.reconfigure(encoding='utf-8')

print("\n" + "="*50)
print("Configuration Verification")
print("="*50)

# Check model_config.json
if os.path.exists('model_config.json'):
    try:
        with open('model_config.json', 'r', encoding='utf-8') as f:
            config = json.load(f)
        print("\n[OK] model_config.json is valid JSON")
        print(f"  Current model: {config.get('current_model')}")
        print(f"  Available models: {len(config.get('available_models', []))}")
        
        for model in config.get('available_models', []):
            exists = os.path.exists(model)
            status = "[OK]" if exists else "[MISSING]"
            print(f"    {status} {model}")
    except Exception as e:
        print(f"[ERROR] Error reading config: {e}")
else:
    print("[MISSING] model_config.json not found")

# Check model directory
print(f"\n[OK] Model directory: model/")
if os.path.exists('model'):
    files = os.listdir('model')
    print(f"  Files in model folder: {len(files)}")
    for f in files:
        print(f"    - {f}")
else:
    print("  [MISSING] model/ directory not found")

print("\n" + "="*50)
