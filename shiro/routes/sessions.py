# -*- coding: utf-8 -*-
"""
Shiro Session Management Routes
Handles multi-session creation, switching, listing, and deletion.
"""

from flask import Blueprint, request, jsonify
from shiro.auth import verify_api_key
from shiro.server_state import state
from shiro.routes.chat import _format_message_for_api

sessions_bp = Blueprint("sessions_bp", __name__)

@sessions_bp.route('/api/sessions', methods=['GET'])
def list_sessions():
    if not verify_api_key(allow_web_ui=True):
        return jsonify({"error": "Unauthorized"}), 401
    try:
        memory = state.init_memory()
        with memory.lock:
            return jsonify({
                "sessions": memory.get_sessions_list(),
                "active_session_id": getattr(memory, "active_session_id", "default"),
                "messages": [_format_message_for_api(m) for m in memory.short_term_history]
            })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@sessions_bp.route('/api/sessions/new', methods=['POST'])
def create_session():
    if not verify_api_key(allow_web_ui=True):
        return jsonify({"error": "Unauthorized"}), 401
    try:
        data = request.json or {}
        title = data.get("title", None)
        memory = state.init_memory()
        with memory.lock:
            new_id = memory.create_new_session(title=title)
            return jsonify({
                "success": True,
                "session_id": new_id,
                "sessions": memory.get_sessions_list(),
                "active_session_id": new_id,
                "messages": []
            })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@sessions_bp.route('/api/sessions/switch', methods=['POST'])
def switch_session():
    if not verify_api_key(allow_web_ui=True):
        return jsonify({"error": "Unauthorized"}), 401
    try:
        data = request.json or {}
        session_id = data.get("session_id")
        if not session_id:
            return jsonify({"error": "session_id wajib diisi"}), 400
        memory = state.init_memory()
        with memory.lock:
            ok = memory.switch_session(session_id)
            if not ok:
                return jsonify({"error": "Sesi tidak ditemukan"}), 404
            return jsonify({
                "success": True,
                "active_session_id": session_id,
                "messages": [_format_message_for_api(m) for m in memory.short_term_history],
                "sessions": memory.get_sessions_list()
            })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@sessions_bp.route('/api/sessions/<session_id>', methods=['DELETE'])
def delete_session(session_id):
    if not verify_api_key(allow_web_ui=True):
        return jsonify({"error": "Unauthorized"}), 401
    try:
        memory = state.init_memory()
        with memory.lock:
            ok = memory.delete_session(session_id)
            return jsonify({
                "success": ok,
                "active_session_id": memory.active_session_id,
                "messages": [_format_message_for_api(m) for m in memory.short_term_history],
                "sessions": memory.get_sessions_list()
            })
    except Exception as e:
        return jsonify({"error": str(e)}), 500
