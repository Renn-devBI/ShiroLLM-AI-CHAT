# -*- coding: utf-8 -*-
"""
Shiro AI - Web Server & API Gateway
Modular Flask application orchestrating UI, REST, and OpenAI API endpoints.
"""

import os
import sys
import logging
from flask import Flask, jsonify

# Pre-configuration & UTF-8 Encoding
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

os.environ['PYTHONIOENCODING'] = 'utf-8'

# Base Configuration & State
from shiro.config import CONTEXT_SIZE, MODEL_DIR
from shiro.server_state import state
from shiro.models import (
    load_model_config,
    save_model_config,
    get_available_gguf_models,
    instantiate_llama_model,
    find_active_lora_path,
    get_gpu_layers
)
from shiro.auth import (
    get_active_api_key,
    get_all_valid_api_keys,
    get_or_create_api_key,
    verify_api_key
)
from shiro.pipeline.inference import get_shiro_reply
from shiro.pipeline.trace import global_pipeline_manager

# Import Modular Blueprints
from shiro.routes import (
    views_bp,
    chat_bp,
    openai_bp,
    documents_bp,
    sessions_bp,
    admin_bp
)

# Initialize Flask App
app = Flask(
    __name__,
    template_folder='templates',
    static_folder='static',
    static_url_path='/static'
)

# Register Modular Blueprints
app.register_blueprint(views_bp)
app.register_blueprint(chat_bp)
app.register_blueprint(openai_bp)
app.register_blueprint(documents_bp)
app.register_blueprint(sessions_bp)
app.register_blueprint(admin_bp)

# Error Handlers
@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "Endpoint not found"}), 404

@app.errorhandler(500)
def server_error(e):
    return jsonify({"error": "Internal server error"}), 500

# Backward compatibility attributes for external scripts
memory = state.init_memory()
llm = state.llm
latest_pipeline_trace = global_pipeline_manager.get_latest_trace()

def broadcast_pipeline_trace(trace):
    global_pipeline_manager.broadcast(trace)

if __name__ == '__main__':
    from werkzeug.serving import WSGIRequestHandler
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.ERROR)

    config = load_model_config()
    current_model_path = config.get("current_model")

    if not current_model_path or not os.path.exists(current_model_path):
        existing_models = get_available_gguf_models()
        if existing_models:
            current_model_path = existing_models[0]
            print(f"⚠️ Model di config ({config.get('current_model')}) belum tersedia di disk, otomatis beralih ke: {current_model_path}")
        else:
            print(f"❌ Error: Model file '{current_model_path}' tidak ditemukan di folder {MODEL_DIR}!")
            sys.exit(1)

    try:
        active_llm, active_vision = instantiate_llama_model(current_model_path)
        state.set_llm(active_llm, active_vision)
        llm = active_llm

        model_name = os.path.basename(current_model_path)
        print(f"✓ Model loaded: {model_name}")
        print(f"✓ Context Window: {CONTEXT_SIZE} tokens")
        if active_vision:
            print("👁️ Multimodal Vision Mode: AKTIF (Mendukung Kamera Real-Time & Analisis Gambar)")
        gpu_layers = get_gpu_layers()
        if gpu_layers != 0:
            print(f"🚀 Akselerasi GPU AKTIF (Layers: {gpu_layers})")
        else:
            print("⚠️ Mode: CPU (Di Colab pastikan Runtime -> Change runtime type -> T4/A100 GPU)")
    except Exception as e:
        print(f"❌ Error loading model: {e}")
        sys.exit(1)

    # Inisialisasi ingatan dan web reader
    state.init_memory()
    state.init_web_reader()

    try:
        active_api_key = get_or_create_api_key(force_new=True)
        print("\n" + "=" * 60)
        print("SERVER SHIRO LLMA AKTIF")
        print("Web UI: http://127.0.0.1:7474")
        print("=" * 60)
        print("API INTEGRATION (WhatsApp Bot / VTuber / Eksternal):")
        print(f"SHIRO API KEY: {active_api_key}")
        print("👉 v1 (Default Shiro - ID)  : http://127.0.0.1:7474/v1")
        print("👉 v2 (VTuber Engine - JP)  : http://127.0.0.1:7474/v2")
        print("👉 v3 (Custom Base Prompt)  : http://127.0.0.1:7474/v3")
        print("👉 Chat Endpoint (v1)       : http://127.0.0.1:7474/v1/chat/completions")
        print("👉 Chat Endpoint (v2 VTuber): http://127.0.0.1:7474/v2/chat/completions")
        print("👉 Chat Endpoint (v3 Custom): http://127.0.0.1:7474/v3/chat/completions")
        print("=" * 60)
        print("Press Ctrl+C to stop\n")

        app.run(
            host='127.0.0.1',
            port=7474,
            debug=False,
            use_reloader=False,
            threaded=True
        )
    except OSError as e:
        print(f"\n❌ Port 7474 already in use or error: {e}")
        print("💡 Try closing other applications using this port")
    except KeyboardInterrupt:
        print("\n\nShutting down server...")
        try:
            if state.memory:
                state.memory.finalize_session()
                state.memory.save_memory()
                print("✓ Memory saved successfully")
        except Exception:
            pass
        print("Goodbye!\n")
        sys.exit(0)
