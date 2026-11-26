# -*- coding: utf-8 -*-
"""
Shiro Local PC Agent REST API Blueprint
Mengelola pengaturan mode Antigravity PC Lokal, daftar tugas, dan gerbang persetujuan.
"""

import json as py_json
from datetime import datetime
from flask import Blueprint, request, jsonify, Response

from shiro.auth import verify_api_key
from shiro.server_state import state
from shiro.memory.optimization import compress_old_messages
from shiro.agent.local_agent import get_agent_status, save_agent_settings
from shiro.agent.autonomous_runner import autonomous_runner

agent_bp = Blueprint("agent_bp", __name__)


def _persist_agent_reply_to_memory(user_message: str, reply: str):
    """Menyimpan hasil akhir jawaban Agent ke memori percakapan aktif."""
    if not reply or not reply.strip():
        return None, None
    memory = state.init_memory()
    with memory.lock:
        assistant_msg_id = memory.add_message("assistant", reply)
        memory.update_emotional_state_from_response(reply)
        memory.update_mood_from_emotions()
        if user_message and memory.system_metadata.get("enable_training_logging", True):
            memory.record_learned_pattern(user_message, reply)
        active_sess_id = getattr(memory, "active_session_id", "default")
        if hasattr(memory, "sessions_store") and active_sess_id in memory.sessions_store:
            memory.sessions_store[active_sess_id]["messages"] = list(memory.short_term_history)
            memory.sessions_store[active_sess_id]["last_active"] = datetime.now().isoformat()
        if len(memory.short_term_history) > 500:
            compress_old_messages(memory, keep_count=500)
        memory.save_memory()
        return assistant_msg_id, memory.system_metadata.get("total_turns", 0)


@agent_bp.route('/api/agent/settings', methods=['GET', 'POST'])
def agent_settings_route():
    """Membaca atau memperbarui pengaturan Local PC Agent (persetujuan & izin admin)."""
    if not verify_api_key(allow_web_ui=True):
        return jsonify({"error": "Unauthorized"}), 401

    if request.method == 'GET':
        return jsonify(get_agent_status())

    try:
        data = request.json or {}
        save_agent_settings(data)
        return jsonify({"success": True, **get_agent_status()})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@agent_bp.route('/api/agent/tasks', methods=['GET'])
def agent_tasks_route():
    """Daftar tugas otonom PC lokal beserta status rencana & antrean persetujuan."""
    if not verify_api_key(allow_web_ui=True):
        return jsonify({"error": "Unauthorized"}), 401
    return jsonify({"tasks": autonomous_runner.task_store.list_tasks()})


@agent_bp.route('/api/agent/approve', methods=['POST'])
def agent_approve_route():
    """Melanjutkan atau membatalkan langkah tugas Agent yang menunggu persetujuan."""
    if not verify_api_key(allow_web_ui=True):
        return jsonify({"error": "Unauthorized"}), 401

    data = request.json or {}
    task_id = (data.get("task_id") or "").strip()
    decision = (data.get("decision") or "").strip().lower()
    stream_mode = data.get("stream", True)

    if not task_id:
        return jsonify({"error": "Parameter 'task_id' wajib diisi"}), 400
    if decision not in ("approve", "approve_all", "approve_admin", "reject"):
        return jsonify({"error": "Parameter 'decision' harus bernilai approve, approve_all, approve_admin, atau reject"}), 400

    task = autonomous_runner.task_store.get(task_id)
    if not task:
        return jsonify({"error": f"Task '{task_id}' tidak ditemukan"}), 404

    if not stream_mode:
        res = autonomous_runner.resume_task(task_id, decision, state.llm)
        if res.get("status") in ("completed", "rejected") and res.get("reply"):
            msg_id, total_turns = _persist_agent_reply_to_memory(task.get("user_input", ""), res["reply"])
            res["assistant_message_id"] = msg_id
            res["count"] = total_turns
        return jsonify(res)

    def generate_resume_stream():
        try:
            for ev in autonomous_runner.resume_task_stream(task_id, decision, state.llm):
                etype = ev.get("type")
                if etype == "done":
                    final_reply = ev.get("reply", "")
                    msg_id, total_turns = _persist_agent_reply_to_memory(task.get("user_input", ""), final_reply)
                    ev["assistant_message_id"] = msg_id
                    if total_turns is not None:
                        ev["count"] = total_turns
                yield f"data: {py_json.dumps(ev)}\n\n"
        except Exception as e_st:
            yield f"data: {py_json.dumps({'type': 'error', 'error': str(e_st)})}\n\n"

    resp = Response(generate_resume_stream(), mimetype="text/event-stream")
    resp.headers["Cache-Control"] = "no-cache"
    resp.headers["X-Accel-Buffering"] = "no"
    return resp
