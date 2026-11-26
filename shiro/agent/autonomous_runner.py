# -*- coding: utf-8 -*-
"""
Shiro Autonomous Antigravity Runner (Local PC Only)
Arsitektur Plan -> Execute -> Observe -> Approval Gate -> Verify -> Synthesize.
Mengelola status tugas di memori agar stream SSE dapat berhenti seketika saat
menunggu persetujuan pengguna tanpa memblokir thread server.
"""

import re
import json
import time
import uuid
import threading
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple, Generator

from shiro.agent.local_tools import (
    TOOL_RISK_LEVELS,
    LOCAL_TOOLS_SCHEMA_PROMPT,
    get_tool_risk,
    tool_list_dir,
    execute_local_tool,
)
from shiro.agent.local_agent import (
    load_agent_settings,
    needs_approval,
)
from shiro.llm.cleaner import clean_response
from shiro.pipeline.trace import global_pipeline_manager


def extract_json_object(raw_text: str) -> Optional[Dict[str, Any]]:
    """
    Mengekstrak objek JSON pertama yang valid dari respons LLM
    (menghapus blok <think>, markdown code fence, dan trailing commas).
    """
    if not raw_text:
        return None
    cleaned = re.sub(r'<think>.*?</think>', '', str(raw_text), flags=re.DOTALL | re.IGNORECASE).strip()

    candidates: List[str] = []
    for m in re.finditer(r'```(?:json)?\s*(\{.*?\})\s*```', cleaned, flags=re.DOTALL | re.IGNORECASE):
        candidates.append(m.group(1).strip())

    # Cari objek JSON terluar dengan pencocokan kurung kurawal seimbang
    start_idx = cleaned.find("{")
    if start_idx != -1:
        depth = 0
        in_str = False
        esc = False
        for i in range(start_idx, len(cleaned)):
            ch = cleaned[i]
            if esc:
                esc = False
                continue
            if ch == "\\" and in_str:
                esc = True
                continue
            if ch == '"':
                in_str = not in_str
                continue
            if not in_str:
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        candidates.append(cleaned[start_idx : i + 1])
                        break

    for cand in candidates:
        for attempt in (cand, re.sub(r',\s*([}\]])', r'\1', cand)):
            try:
                obj = json.loads(attempt)
                if isinstance(obj, dict):
                    return obj
            except Exception:
                continue
    return None


class AgentTaskStore:
    """Penyimpanan thread-safe status tugas otonom dan antrean persetujuan."""

    def __init__(self):
        self._lock = threading.Lock()
        self._tasks: Dict[str, Dict[str, Any]] = {}

    def create(
        self,
        user_input: str,
        workspace_root: str,
        session_id: str = "default",
        api_version: str = "v1"
    ) -> Dict[str, Any]:
        task_id = f"agent-{uuid.uuid4().hex[:10]}"
        task = {
            "task_id": task_id,
            "user_input": user_input,
            "workspace_root": workspace_root,
            "session_id": session_id,
            "api_version": api_version,
            "status": "planning",   # planning | running | awaiting_approval | completed | rejected | error
            "plan": None,
            "step_index": 0,
            "observations": [],
            "steps_log": [],
            "files_touched": [],
            "commands_run": [],
            "pending_action": None,
            "session_approvals": {"approve_all": False, "approve_admin": False},
            "final_reply": "",
            "agent_action": None,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "started_perf": time.perf_counter(),
        }
        with self._lock:
            self._tasks[task_id] = task
        return task

    def get(self, task_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            return self._tasks.get(task_id)

    def update(self, task_id: str, **fields) -> Optional[Dict[str, Any]]:
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return None
            task.update(fields)
            task["updated_at"] = datetime.now().isoformat()
            return task

    def list_tasks(self, limit: int = 20) -> List[Dict[str, Any]]:
        with self._lock:
            items = sorted(self._tasks.values(), key=lambda t: t.get("created_at", ""), reverse=True)[:limit]
            return [
                {
                    "task_id": t["task_id"],
                    "user_input": t["user_input"][:120],
                    "status": t["status"],
                    "workspace_root": t["workspace_root"],
                    "created_at": t["created_at"],
                    "updated_at": t["updated_at"],
                    "steps_count": len(t.get("steps_log", [])),
                    "pending_action": t.get("pending_action"),
                    "plan": t.get("plan"),
                }
                for t in items
            ]


class AutonomousAgentRunner:
    """Mesin AI Agent otonom ala Antigravity (Plan -> Approve/Execute -> Verify -> Reply)."""

    def __init__(self, task_store: Optional[AgentTaskStore] = None):
        self.task_store = task_store or AgentTaskStore()

    def _call_llm_json(
        self,
        llm: Any,
        messages: List[Dict[str, Any]],
        max_tokens: int = 2048,
        temperature: float = 0.2
    ) -> Tuple[str, Optional[Dict[str, Any]]]:
        from shiro.server_state import state as server_state
        with server_state.llm_lock:
            res = llm.create_chat_completion(
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
                top_p=0.9,
            )
        raw = ""
        if isinstance(res, dict) and res.get("choices"):
            raw = res["choices"][0].get("message", {}).get("content", "") or ""
        return raw.strip(), extract_json_object(raw)

    def _build_plan(
        self,
        llm: Any,
        task_text: str,
        workspace_root: str,
        allow_admin: bool
    ) -> Dict[str, Any]:
        """Fase 1: Menyusun rencana kerja terstruktur berdasarkan isi workspace aktual."""
        dir_snapshot = tool_list_dir(".", max_entries=30, workspace_root=workspace_root)
        ws_preview = dir_snapshot.get("summary", "(workspace kosong)")

        planner_system = (
            "Kamu adalah Modul Perencana (Antigravity Planner) pada sistem AI Agent PC Lokal.\n"
            "Tugasmu adalah menyusun rencana langkah demi langkah yang realistis dan ringkas.\n"
            f"Workspace aktif: {workspace_root}\n"
            f"Izin pre-authorized Admin UAC: {'AKTIF' if allow_admin else 'NONAKTIF (tetap bisa diajukan untuk persetujuan pengguna)'}\n\n"
            f"{LOCAL_TOOLS_SCHEMA_PROMPT}\n\n"
            "Keluarkan HANYA satu objek JSON valid dengan struktur persis:\n"
            '{"goal": "tujuan singkat", "requires_admin": false, "steps": ['
            '{"id": 1, "title": "judul langkah singkat", "tool": "nama_tool", "risk": "read|write|exec|destructive|admin", "details": "penjelasan singkat"}]}'
        )
        planner_user = (
            f"Tugas dari pengguna:\n{task_text}\n\n"
            f"Kondisi workspace saat ini:\n{ws_preview}\n\n"
            "Buat rencana JSON sekarang."
        )

        _, parsed = self._call_llm_json(
            llm,
            [{"role": "system", "content": planner_system}, {"role": "user", "content": planner_user}],
            max_tokens=1536,
            temperature=0.2
        )

        if parsed and isinstance(parsed.get("steps"), list) and len(parsed["steps"]) > 0:
            norm_steps: List[Dict[str, Any]] = []
            for idx, st in enumerate(parsed["steps"][:10], 1):
                if not isinstance(st, dict):
                    continue
                t_name = str(st.get("tool") or "run_command").strip()
                norm_steps.append({
                    "id": int(st.get("id") or idx),
                    "title": str(st.get("title") or f"Langkah {idx}")[:120],
                    "tool": t_name,
                    "risk": str(st.get("risk") or get_tool_risk(t_name)),
                    "details": str(st.get("details") or "")[:240],
                    "status": "pending",
                })
            if norm_steps:
                return {
                    "goal": str(parsed.get("goal") or task_text[:120]),
                    "requires_admin": bool(parsed.get("requires_admin", False)) or any(s["risk"] == "admin" for s in norm_steps),
                    "steps": norm_steps,
                }

        # Fallback rencana aman 2 langkah
        return {
            "goal": task_text[:120],
            "requires_admin": False,
            "steps": [
                {"id": 1, "title": "Analisis & Eksekusi Tugas", "tool": "write_file", "risk": "write", "details": task_text[:180], "status": "pending"},
                {"id": 2, "title": "Verifikasi Hasil Pekerjaan", "tool": "run_command", "risk": "exec", "details": "Memastikan hasil di workspace berjalan benar", "status": "pending"},
            ],
        }

    def _set_step_status(self, plan: Optional[Dict[str, Any]], step_id: Optional[int], status: str):
        if not plan or not isinstance(plan.get("steps"), list):
            return
        matched = False
        if step_id is not None:
            for st in plan["steps"]:
                if st.get("id") == step_id:
                    st["status"] = status
                    matched = True
                    break
        if not matched:
            for st in plan["steps"]:
                if st.get("status") in ("pending", "in_progress", "awaiting_approval"):
                    st["status"] = status
                    break

    def _record_execution(self, task: Dict[str, Any], tool_name: str, args: Dict[str, Any], res: Dict[str, Any], step_id: Optional[int], thought: str):
        plan = task.get("plan")
        step_status = "done" if res.get("success") else "failed"
        self._set_step_status(plan, step_id, step_status)

        if tool_name in ("write_file", "edit_file", "delete_file"):
            p = (args or {}).get("path")
            if p and p not in task["files_touched"]:
                task["files_touched"].append(p)
        elif tool_name in ("run_command", "run_admin_command"):
            c = (args or {}).get("command")
            if c:
                task["commands_run"].append(c)

        obs_line = f"[{tool_name} -> {'OK' if res.get('success') else 'GAGAL'}] {res.get('summary', '')}"
        task["observations"].append(obs_line[:1200])
        task["steps_log"].append({
            "step_id": step_id,
            "tool": tool_name,
            "risk": get_tool_risk(tool_name),
            "args": args,
            "thought": thought,
            "success": bool(res.get("success")),
            "status": step_status,
            "summary": res.get("summary", ""),
            "error": res.get("error"),
        })
        task["step_index"] = int(task.get("step_index", 0)) + 1

    def _finalize_task_events(
        self,
        task: Dict[str, Any],
        final_reply: str,
        status: str = "completed"
    ) -> Generator[Dict[str, Any], None, None]:
        cleaned = clean_response(final_reply, assistant_name="Shiro", user_input=task.get("user_input", ""))
        if not cleaned or not cleaned.strip():
            cleaned = final_reply.strip() or "Tugas PC lokal telah selesai dijalankan."

        elapsed = round(time.perf_counter() - task.get("started_perf", time.perf_counter()), 2)
        plan = task.get("plan") or {}
        if status == "completed" and isinstance(plan.get("steps"), list):
            for st in plan["steps"]:
                if st.get("status") in ("pending", "in_progress"):
                    st["status"] = "done"

        obs_summary = "\n".join(task.get("observations", [])) or "Eksekusi selesai."
        agent_action = {
            "tool": "local_autonomous_agent",
            "description": f"Antigravity Local Agent: {plan.get('goal') or task.get('user_input', '')[:80]}",
            "observation": obs_summary,
            "details": {
                "task_id": task["task_id"],
                "plan": plan,
                "steps_log": task.get("steps_log", []),
                "files_touched": task.get("files_touched", []),
                "commands_run": task.get("commands_run", []),
            },
            "execution_time_sec": elapsed,
            "status": "success" if status == "completed" else "failed",
        }

        trace = {
            "id": f"trace-{int(time.time()*1000)}",
            "timestamp": datetime.now().isoformat(),
            "status": status,
            "total_duration_ms": round(elapsed * 1000, 2),
            "user_input": task.get("user_input", ""),
            "reply": cleaned,
            "agent_action": agent_action,
            "nodes": [
                {
                    "id": "node_agent_plan",
                    "name": "Antigravity Local Planner",
                    "type": "analyzer",
                    "icon": "ph-list-checks",
                    "color": "#8b5cf6",
                    "status": "success",
                    "duration_ms": 10.0,
                    "summary": f"{len(plan.get('steps', []))} Langkah Rencana",
                },
                {
                    "id": "node_agent_exec",
                    "name": "Local PC Autonomous Executor",
                    "type": "tool",
                    "icon": "ph-terminal-window",
                    "color": "#10b981" if status == "completed" else "#ef4444",
                    "status": "success" if status == "completed" else "failed",
                    "duration_ms": round(elapsed * 1000, 2),
                    "summary": f"{len(task.get('steps_log', []))} Aksi Dieksekusi",
                },
            ],
        }
        global_pipeline_manager.broadcast(trace)

        self.task_store.update(
            task["task_id"],
            status=status,
            final_reply=cleaned,
            agent_action=agent_action,
            pending_action=None,
        )

        yield {"type": "agent_action", "agent_action": agent_action}
        yield {"type": "token", "token": cleaned}
        yield {
            "type": "done",
            "reply": cleaned,
            "status": status,
            "task_id": task["task_id"],
            "plan": plan,
            "agent_action": agent_action,
            "trace": trace,
        }

    def _build_exec_prompt(self, task: Dict[str, Any], settings: Dict[str, Any]) -> List[Dict[str, str]]:
        plan = task.get("plan") or {}
        obs = task.get("observations", [])
        obs_block = "\n".join(f"- {o}" for o in obs[-10:]) if obs else "(belum ada aksi yang dijalankan)"
        sys_msg = (
            "Kamu adalah Shiro dalam mode Antigravity Autonomous Local PC Agent.\n"
            "Eksekusi rencana satu langkah tool pada satu waktu menggunakan JSON.\n"
            f"Workspace root: {task['workspace_root']}\n"
            f"Kebijakan Approval: {settings['approval_mode']} | Allow Admin: {settings['allow_admin']}\n\n"
            f"{LOCAL_TOOLS_SCHEMA_PROMPT}\n\n"
            "Aturan Output JSON:\n"
            "- Untuk menjalankan tool:\n"
            '  {"thought": "alasan singkat", "step_id": 1, "action": "nama_tool", "args": {...}}\n'
            "- Jika seluruh tujuan sudah selesai dan terverifikasi:\n"
            '  {"thought": "ringkasan verifikasi", "action": "finish", "final_answer": "Jawaban manis dan akurat untuk Kakak dalam Bahasa Indonesia (sesuai bahasa user) yang merangkum hasil nyata yang telah dilakukan."}\n'
            "PENTING: Jangan mengarang hasil tool; jalankan tool lalu lihat observasinya. Keluarkan HANYA JSON valid."
        )
        user_msg = (
            f"TUJUAN UTAMA:\n{task['user_input']}\n\n"
            f"RENCANA (PLAN):\n{json.dumps(plan, ensure_ascii=False, indent=2)}\n\n"
            f"RIWAYAT OBSERVASI EKSEKUSI SEJAUH INI:\n{obs_block}\n\n"
            f"Langkah ke-{task.get('step_index', 0) + 1} dari maks {settings['max_steps']}. Tentukan aksi JSON berikutnya:"
        )
        return [{"role": "system", "content": sys_msg}, {"role": "user", "content": user_msg}]

    def _execute_loop_stream(
        self,
        task: Dict[str, Any],
        llm: Any,
        settings: Dict[str, Any]
    ) -> Generator[Dict[str, Any], None, None]:
        max_steps = int(settings.get("max_steps", 12))
        ws_root = task["workspace_root"]
        allow_outside = bool(settings.get("allow_outside_workspace", False))

        while int(task.get("step_index", 0)) < max_steps:
            step_num = int(task.get("step_index", 0)) + 1
            yield {"type": "status", "status": f"Agen PC otonom menentukan langkah {step_num}..."}

            msgs = self._build_exec_prompt(task, settings)
            raw_txt, parsed = self._call_llm_json(llm, msgs, max_tokens=2048, temperature=0.2)

            if not parsed or not parsed.get("action"):
                # Coba 1x koreksi format JSON
                retry_msgs = msgs + [
                    {"role": "assistant", "content": raw_txt or "{}"},
                    {"role": "user", "content": "Format respons tidak valid. Keluarkan HANYA satu objek JSON valid dengan key 'action' ('finish' atau nama tool)."},
                ]
                raw_txt2, parsed = self._call_llm_json(llm, retry_msgs, max_tokens=1536, temperature=0.1)
                if not parsed or not parsed.get("action"):
                    fallback_reply = raw_txt2 or raw_txt or (
                        "Tugas selesai diproses, Kakak. " + ("\n".join(task.get("observations", [])) if task.get("observations") else "")
                    )
                    yield from self._finalize_task_events(task, fallback_reply, status="completed")
                    return

            action_name = str(parsed.get("action") or "").strip()
            thought = str(parsed.get("thought") or "").strip()
            step_id = parsed.get("step_id")
            action_args = parsed.get("args") if isinstance(parsed.get("args"), dict) else {}

            if action_name == "finish":
                final_ans = str(parsed.get("final_answer") or thought or "Tugas selesai dilaksanakan, Kakak!")
                yield from self._finalize_task_events(task, final_ans, status="completed")
                return

            if action_name not in TOOL_RISK_LEVELS:
                task["observations"].append(f"[ERROR] Tool '{action_name}' tidak tersedia. Gunakan hanya tool dalam skema.")
                task["step_index"] = step_num
                continue

            risk = get_tool_risk(action_name)
            need_app, app_reason = needs_approval(action_name, action_args, settings, task.get("session_approvals"))

            if need_app:
                self._set_step_status(task.get("plan"), step_id, "awaiting_approval")
                pending = {
                    "tool": action_name,
                    "risk": risk,
                    "args": action_args,
                    "thought": thought,
                    "step_id": step_id,
                    "reason": app_reason,
                }
                self.task_store.update(task["task_id"], status="awaiting_approval", pending_action=pending)
                yield {
                    "type": "approval_required",
                    "task_id": task["task_id"],
                    "plan": task.get("plan"),
                    "pending_action": pending,
                }
                return

            self._set_step_status(task.get("plan"), step_id, "in_progress")
            yield {"type": "status", "status": f"Menjalankan `{action_name}`..."}

            res = execute_local_tool(action_name, action_args, workspace_root=ws_root, allow_outside_workspace=allow_outside)
            self._record_execution(task, action_name, action_args, res, step_id, thought)

            yield {
                "type": "agent_step",
                "task_id": task["task_id"],
                "step_index": step_num,
                "step_id": step_id,
                "tool": action_name,
                "risk": risk,
                "args": action_args,
                "status": "done" if res.get("success") else "failed",
                "summary": res.get("summary", ""),
                "output": (res.get("data") or {}).get("stdout") or res.get("summary", ""),
                "plan": task.get("plan"),
            }

        # Mencapai batas max_steps -> sintesis hasil akhir berdasarkan observasi
        summary_ans = (
            f"Shiro telah menyelesaikan {len(task.get('steps_log', []))} langkah otonom di workspace `{ws_root}`:\n"
            + "\n".join(f"- {s.get('tool')}: {'Berhasil' if s.get('success') else 'Gagal'}" for s in task.get("steps_log", []))
        )
        yield from self._finalize_task_events(task, summary_ans, status="completed")

    def run_task_stream(
        self,
        user_input: str,
        llm: Any,
        settings_file: Optional[str] = None,
        session_id: str = "default",
        api_version: str = "v1"
    ) -> Generator[Dict[str, Any], None, None]:
        """Memulai tugas Antigravity baru secara streaming SSE."""
        if llm is None:
            yield {"type": "error", "error": "Model LLM belum dimuat di memori server."}
            return

        settings = load_agent_settings(settings_file)
        ws_root = settings["effective_workspace"]
        task = self.task_store.create(
            user_input=user_input,
            workspace_root=ws_root,
            session_id=session_id,
            api_version=api_version,
        )

        yield {"type": "status", "status": "Menyusun rencana kerja (Antigravity Planner)..."}
        plan = self._build_plan(llm, user_input, ws_root, settings.get("allow_admin", False))
        self.task_store.update(task["task_id"], status="running", plan=plan)

        yield {"type": "agent_plan", "task_id": task["task_id"], "plan": plan}
        yield from self._execute_loop_stream(task, llm, settings)

    def resume_task_stream(
        self,
        task_id: str,
        decision: str,
        llm: Any,
        settings_file: Optional[str] = None
    ) -> Generator[Dict[str, Any], None, None]:
        """Melanjutkan atau menolak tugas yang sedang menunggu persetujuan pengguna."""
        task = self.task_store.get(task_id)
        if not task:
            yield {"type": "error", "error": f"Task '{task_id}' tidak ditemukan."}
            return
        if task.get("status") != "awaiting_approval" or not task.get("pending_action"):
            yield {"type": "error", "error": f"Task '{task_id}' tidak sedang menunggu persetujuan."}
            return

        dec = (decision or "").strip().lower()
        pending = task["pending_action"]

        if dec == "reject":
            self._set_step_status(task.get("plan"), pending.get("step_id"), "skipped")
            cancel_msg = (
                f"Baik Kakak, Shiro membatalkan eksekusi `{pending.get('tool')}` sesuai permintaan Kakak. "
                "Tidak ada perubahan lanjutan yang diterapkan."
            )
            yield from self._finalize_task_events(task, cancel_msg, status="rejected")
            return

        if dec not in ("approve", "approve_all", "approve_admin"):
            yield {"type": "error", "error": f"Keputusan persetujuan tidak valid: '{decision}'."}
            return

        if llm is None:
            yield {"type": "error", "error": "Model LLM belum dimuat di memori server."}
            return

        settings = load_agent_settings(settings_file)
        if dec == "approve_all":
            task["session_approvals"]["approve_all"] = True
        elif dec == "approve_admin":
            task["session_approvals"]["approve_admin"] = True

        self.task_store.update(task_id, status="running", pending_action=None)
        tool_name = pending["tool"]
        action_args = pending.get("args") or {}
        step_id = pending.get("step_id")
        thought = pending.get("thought", "")
        risk = pending.get("risk") or get_tool_risk(tool_name)

        self._set_step_status(task.get("plan"), step_id, "in_progress")
        yield {"type": "status", "status": f"Menjalankan `{tool_name}` (disetujui)..."}

        res = execute_local_tool(
            tool_name,
            action_args,
            workspace_root=task["workspace_root"],
            allow_outside_workspace=bool(settings.get("allow_outside_workspace", False)),
        )
        self._record_execution(task, tool_name, action_args, res, step_id, thought)

        yield {
            "type": "agent_step",
            "task_id": task_id,
            "step_index": int(task.get("step_index", 1)),
            "step_id": step_id,
            "tool": tool_name,
            "risk": risk,
            "args": action_args,
            "status": "done" if res.get("success") else "failed",
            "summary": res.get("summary", ""),
            "output": (res.get("data") or {}).get("stdout") or res.get("summary", ""),
            "plan": task.get("plan"),
        }

        yield from self._execute_loop_stream(task, llm, settings)

    def _consume_stream(self, event_iter: Generator[Dict[str, Any], None, None]) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "status": "completed",
            "task_id": None,
            "plan": None,
            "pending_action": None,
            "reply": "",
            "agent_action": None,
            "steps_log": [],
        }
        for ev in event_iter:
            etype = ev.get("type")
            if etype == "agent_plan":
                result["task_id"] = ev.get("task_id")
                result["plan"] = ev.get("plan")
            elif etype == "agent_step":
                result["steps_log"].append(ev)
                result["plan"] = ev.get("plan") or result["plan"]
            elif etype == "approval_required":
                result["status"] = "awaiting_approval"
                result["task_id"] = ev.get("task_id")
                result["plan"] = ev.get("plan")
                result["pending_action"] = ev.get("pending_action")
                p = result["pending_action"] or {}
                result["reply"] = (
                    f"Shiro sudah menyusun rencana dan membutuhkan persetujuan Kakak untuk menjalankan "
                    f"`{p.get('tool')}` ({p.get('risk')}): {p.get('reason', '')}."
                )
            elif etype == "agent_action":
                result["agent_action"] = ev.get("agent_action")
            elif etype == "done":
                result["status"] = ev.get("status", "completed")
                result["task_id"] = ev.get("task_id") or result["task_id"]
                result["plan"] = ev.get("plan") or result["plan"]
                result["reply"] = ev.get("reply", result["reply"])
                result["agent_action"] = ev.get("agent_action") or result["agent_action"]
            elif etype == "error":
                result["status"] = "error"
                result["reply"] = f"Kendala Agent: {ev.get('error', 'Unknown error')}"
        return result

    def run_task(
        self,
        user_input: str,
        llm: Any,
        settings_file: Optional[str] = None,
        session_id: str = "default",
        api_version: str = "v1"
    ) -> Dict[str, Any]:
        """Eksekusi sinkron non-streaming tugas Antigravity PC lokal."""
        return self._consume_stream(
            self.run_task_stream(
                user_input=user_input,
                llm=llm,
                settings_file=settings_file,
                session_id=session_id,
                api_version=api_version,
            )
        )

    def resume_task(
        self,
        task_id: str,
        decision: str,
        llm: Any,
        settings_file: Optional[str] = None
    ) -> Dict[str, Any]:
        """Eksekusi sinkron non-streaming untuk melanjutkan/menolak tugas tertunda."""
        return self._consume_stream(
            self.resume_task_stream(
                task_id=task_id,
                decision=decision,
                llm=llm,
                settings_file=settings_file,
            )
        )


autonomous_runner = AutonomousAgentRunner()
