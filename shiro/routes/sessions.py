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
            memory._ensure_message_ids(memory.short_term_history)
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
            memory._ensure_message_ids(memory.short_term_history)
            return jsonify({
                "success": True,
                "active_session_id": session_id,
                "messages": [_format_message_for_api(m) for m in memory.short_term_history],
                "sessions": memory.get_sessions_list()
            })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@sessions_bp.route('/api/sessions/<session_id>', methods=['GET'])
def get_session(session_id):
    if not verify_api_key(allow_web_ui=True):
        return jsonify({"error": "Unauthorized"}), 401
    try:
        memory = state.init_memory()
        with memory.lock:
            if not hasattr(memory, "sessions_store") or session_id not in memory.sessions_store:
                return jsonify({"error": "Sesi tidak ditemukan", "found": False}), 404
            sess = memory.sessions_store[session_id]
            msgs = sess.get("messages", [])
            memory._ensure_message_ids(msgs)
            return jsonify({
                "found": True,
                "session": {
                    "id": sess.get("id", session_id),
                    "title": sess.get("title", f"Chat {session_id[:8]}"),
                    "pinned": sess.get("pinned", False),
                    "created_at": sess.get("created_at"),
                    "last_active": sess.get("last_active")
                },
                "messages": [_format_message_for_api(m) for m in msgs]
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
            memory._ensure_message_ids(memory.short_term_history)
            return jsonify({
                "success": ok,
                "active_session_id": memory.active_session_id,
                "messages": [_format_message_for_api(m) for m in memory.short_term_history],
                "sessions": memory.get_sessions_list()
            })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@sessions_bp.route('/api/sessions/<session_id>/rename', methods=['POST'])
def rename_session(session_id):
    if not verify_api_key(allow_web_ui=True):
        return jsonify({"error": "Unauthorized"}), 401
    try:
        data = request.json or {}
        new_title = data.get("title", "").strip()
        if not new_title:
            return jsonify({"error": "Judul percakapan tidak boleh kosong"}), 400
        memory = state.init_memory()
        with memory.lock:
            ok = memory.rename_session(session_id, new_title)
            if not ok:
                return jsonify({"error": "Sesi tidak ditemukan"}), 404
            return jsonify({
                "success": True,
                "session_id": session_id,
                "title": new_title,
                "sessions": memory.get_sessions_list()
            })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@sessions_bp.route('/api/sessions/<session_id>/pin', methods=['POST'])
def pin_session(session_id):
    if not verify_api_key(allow_web_ui=True):
        return jsonify({"error": "Unauthorized"}), 401
    try:
        data = request.json or {}
        pinned = data.get("pinned", None)
        memory = state.init_memory()
        with memory.lock:
            res = memory.toggle_pin_session(session_id, pinned)
            if not res:
                return jsonify({"error": "Sesi tidak ditemukan"}), 404
            return jsonify({
                "success": True,
                "session_id": session_id,
                "pinned": res["pinned"],
                "sessions": memory.get_sessions_list()
            })
    except Exception as e:
        return jsonify({"error": str(e)}), 500
