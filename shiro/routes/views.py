# -*- coding: utf-8 -*-
"""
Shiro Views & Pipeline Visualizer Routes
"""

import json
import time
from flask import Blueprint, render_template, jsonify, Response
from shiro.pipeline.trace import global_pipeline_manager

views_bp = Blueprint("views_bp", __name__)

@views_bp.route('/')
def index():
    return render_template('index.html')

@views_bp.route('/pipeline')
def pipeline_page():
    """Halaman visualisasi real-time alur kerja pemikiran AI (n8n-style workflow canvas)"""
    return render_template('pipeline.html')

@views_bp.route('/api/pipeline/latest', methods=['GET'])
def get_latest_pipeline():
    """Mengambil trace eksekusi neural pipeline terkini"""
    return jsonify(global_pipeline_manager.get_latest_trace())

@views_bp.route('/api/pipeline/events')
def pipeline_events():
    """Server-Sent Events (SSE) stream untuk telemetry alur AI real-time"""
    def event_stream():
        q = global_pipeline_manager.subscribe()
        try:
            # Kirim trace awal saat client pertama kali tersambung
            first_trace = global_pipeline_manager.get_latest_trace()
            yield f"data: {json.dumps(first_trace)}\n\n"
            while True:
                try:
                    trace = q.get(timeout=25)
                    yield f"data: {json.dumps(trace)}\n\n"
                except Exception:
                    # Heartbeat keep-alive komentar SSE tiap 25 detik
                    yield ": ping\n\n"
        finally:
            global_pipeline_manager.unsubscribe(q)

    return Response(event_stream(), mimetype="text/event-stream")
