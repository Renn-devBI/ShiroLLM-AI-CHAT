# -*- coding: utf-8 -*-
import os
import json
import shutil
import tempfile
import unittest
import subprocess
from unittest.mock import MagicMock, patch
from flask import Flask

from shiro.agent.local_tools import (
    TOOL_RISK_LEVELS,
    is_dangerous_command,
    execute_local_tool,
    tool_write_file,
    tool_read_file,
    tool_edit_file,
    tool_delete_file,
    tool_search_files,
    tool_list_dir,
    tool_run_command,
    tool_run_admin_command,
)
from shiro.agent.local_agent import (
    load_agent_settings,
    save_agent_settings,
    get_agent_status,
    needs_approval,
    parse_agent_command,
    detect_local_agent_task,
    should_route_to_local_agent,
)
from shiro.agent.autonomous_runner import AutonomousAgentRunner, AgentTaskStore
from shiro.routes.agent import agent_bp
from shiro.routes.chat import chat_bp
from shiro.server_state import state


class TestLocalAutonomousAgent(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.ws_dir = os.path.join(self.tmp_dir, "workspace")
        os.makedirs(self.ws_dir, exist_ok=True)
        self.settings_file = os.path.join(self.tmp_dir, "agent_settings.json")
        self.env_patch = patch.dict(os.environ, {"SHIRO_AGENT_SETTINGS_FILE": self.settings_file})
        self.env_patch.start()
        save_agent_settings({"enabled": True, "workspace_root": self.ws_dir, "approval_mode": "ask", "allow_admin": False}, self.settings_file)

    def tearDown(self):
        self.env_patch.stop()
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_01_local_pc_vs_colab_gating(self):
        """Mode Agent PC hanya aktif di PC lokal (bukan Google Colab) dan tidak mencegat chat/web biasa."""
        with patch("shiro.agent.local_agent.is_running_in_colab", return_value=False):
            self.assertTrue(should_route_to_local_agent("buatkan file hello.py di workspace")["route"])
            self.assertTrue(should_route_to_local_agent("jalankan perintah ini sebagai admin")["route"])
            self.assertTrue(should_route_to_local_agent("/agent buat script backup")["route"])
            # Tidak mencegat obrolan biasa, cuaca, web search, atau pertanyaan konseptual
            self.assertFalse(should_route_to_local_agent("Halo Shiro apa kabar?")["route"])
            self.assertFalse(should_route_to_local_agent("cek cuaca di Jakarta hari ini")["route"])
            self.assertFalse(should_route_to_local_agent("cari di google anime populer tahun ini")["route"])
            self.assertFalse(should_route_to_local_agent("apa itu file python?")["route"])

        # Di Google Colab, semua routing agent PC lokal harus mati total
        with patch("shiro.agent.local_agent.is_running_in_colab", return_value=True):
            res_colab = should_route_to_local_agent("buatkan file hello.py di workspace")
            self.assertFalse(res_colab["route"])
            self.assertEqual(res_colab["reason"], "not_local_pc")
            self.assertFalse(should_route_to_local_agent("/agent cek folder")["route"])

    def test_02_local_tools_file_lifecycle_and_workspace_guard(self):
        """Uji tulis, baca, edit, cari, list, hapus file serta proteksi path di luar workspace."""
        # Write
        r_w = tool_write_file("src/app.py", "def greet():\n    return 'halo'\n", workspace_root=self.ws_dir)
        self.assertTrue(r_w["success"])

        # List dir
        r_l = tool_list_dir("src", workspace_root=self.ws_dir)
        self.assertTrue(r_l["success"])
        self.assertIn("app.py", r_l["summary"])

        # Read
        r_r = tool_read_file("src/app.py", workspace_root=self.ws_dir)
        self.assertTrue(r_r["success"])
        self.assertIn("def greet()", r_r["summary"])

        # Edit
        r_e = tool_edit_file("src/app.py", "return 'halo'", "return 'halo dunia'", workspace_root=self.ws_dir)
        self.assertTrue(r_e["success"])
        self.assertIn("halo dunia", tool_read_file("src/app.py", workspace_root=self.ws_dir)["summary"])

        # Search (glob + content grep)
        r_s = tool_search_files(pattern="*.py", content_query="halo dunia", workspace_root=self.ws_dir)
        self.assertTrue(r_s["success"])
        self.assertIn("src/app.py:2:", r_s["summary"])

        # Path traversal guard
        outside = tool_write_file("../escape.txt", "bad", workspace_root=self.ws_dir, allow_outside_workspace=False)
        self.assertFalse(outside["success"])
        self.assertIn("luar workspace", outside["error"])

        # Delete
        r_d = tool_delete_file("src/app.py", workspace_root=self.ws_dir)
        self.assertTrue(r_d["success"])
        self.assertFalse(os.path.exists(os.path.join(self.ws_dir, "src", "app.py")))

    def test_03_run_command_and_hard_safety_blocklist(self):
        """Uji eksekusi terminal aman dan pemblokiran keras perintah destruktif katastropik."""
        r_ok = tool_run_command("echo SHIRO_LOCAL_OK", workspace_root=self.ws_dir)
        self.assertTrue(r_ok["success"])
        self.assertIn("SHIRO_LOCAL_OK", r_ok["data"]["stdout"])

        for bad_cmd in ["format c: /q", "rm -rf /", "del /f /s /q c:\\windows", "diskpart"]:
            self.assertIsNotNone(is_dangerous_command(bad_cmd))
            r_bad = tool_run_command(bad_cmd, workspace_root=self.ws_dir)
            self.assertFalse(r_bad["success"])
            r_adm = tool_run_admin_command(bad_cmd, workspace_root=self.ws_dir)
            self.assertFalse(r_adm["success"])

    def test_04_run_admin_command_windows_uac_wrapper(self):
        """Uji pembungkus UAC Windows (Start-Process -Verb RunAs) dengan mocking subprocess & non-admin."""
        def fake_subproc_run(cmd_args, **kwargs):
            cmd_str = " ".join(cmd_args) if isinstance(cmd_args, list) else str(cmd_args)
            import re
            m = re.search(r"([A-Za-z]:\\[^'\"]+shiro_admin_[a-f0-9]+\.ps1)", cmd_str)
            self.assertIsNotNone(m, f"Path skrip .ps1 sementara tidak ditemukan di argumen: {cmd_str}")
            ps1_file = m.group(1)
            base = ps1_file[:-4]
            with open(base + ".out", "w", encoding="utf-8") as fo:
                fo.write("ADMIN_SERVICE_OK\n")
            with open(base + ".code", "w", encoding="ascii") as fc:
                fc.write("0")
            m_res = MagicMock()
            m_res.returncode = 0
            m_res.stderr = ""
            return m_res

        with patch("shiro.agent.local_tools.platform.system", return_value="Windows"), \
             patch("shiro.agent.local_tools.os.name", "nt"), \
             patch("shiro.agent.local_tools.is_os_admin", return_value=False), \
             patch("shiro.agent.local_tools.subprocess.run", side_effect=fake_subproc_run) as mock_run:
            res = tool_run_admin_command("Get-Service Spooler", workspace_root=self.ws_dir)
            self.assertTrue(res["success"])
            self.assertTrue(res["data"]["elevated"])
            self.assertEqual(res["data"]["returncode"], 0)
            self.assertIn("ADMIN_SERVICE_OK", res["data"]["stdout"])
            called_cmd = " ".join(mock_run.call_args[0][0])
            self.assertIn("-Verb RunAs", called_cmd)

    def test_05_approval_policy_all_modes(self):
        """Uji matriks kebijakan persetujuan untuk ask, auto_safe, auto_all x allow_admin."""
        ask_cfg = {"approval_mode": "ask", "allow_admin": False}
        safe_cfg = {"approval_mode": "auto_safe", "allow_admin": False}
        all_no_adm = {"approval_mode": "auto_all", "allow_admin": False}
        all_with_adm = {"approval_mode": "auto_all", "allow_admin": True}

        # Read selalu bebas persetujuan di semua mode
        self.assertFalse(needs_approval("read_file", {}, ask_cfg)[0])

        # ask: write, exec, destructive, admin wajib izin
        for t in ("write_file", "run_command", "delete_file", "run_admin_command"):
            self.assertTrue(needs_approval(t, {}, ask_cfg)[0], f"{t} harus minta persetujuan di mode ask")

        # auto_safe: write & exec otomatis; destructive & admin tetap konfirmasi
        self.assertFalse(needs_approval("write_file", {}, safe_cfg)[0])
        self.assertFalse(needs_approval("run_command", {}, safe_cfg)[0])
        self.assertTrue(needs_approval("delete_file", {}, safe_cfg)[0])
        self.assertTrue(needs_approval("run_admin_command", {}, safe_cfg)[0])

        # auto_all tanpa allow_admin: write/exec/delete otomatis; admin TETAP minta izin
        self.assertFalse(needs_approval("delete_file", {}, all_no_adm)[0])
        self.assertTrue(needs_approval("run_admin_command", {}, all_no_adm)[0])

        # auto_all + allow_admin=True: admin pre-authorized
        self.assertFalse(needs_approval("run_admin_command", {}, all_with_adm)[0])

        # Session approval overrides
        self.assertFalse(needs_approval("write_file", {}, ask_cfg, {"approve_all": True, "approve_admin": False})[0])
        self.assertTrue(needs_approval("run_admin_command", {}, ask_cfg, {"approve_all": True, "approve_admin": False})[0])
        self.assertFalse(needs_approval("run_admin_command", {}, ask_cfg, {"approve_all": False, "approve_admin": True})[0])

    def test_06_autonomous_runner_plan_pause_approve_and_complete(self):
        """Dalam mode ask: buat plan -> jeda sebelum write_file -> approve_all -> tulis & jalankan -> selesai."""
        runner = AutonomousAgentRunner(AgentTaskStore())
        target_file = os.path.join(self.ws_dir, "demo.py")

        mock_llm = MagicMock()
        mock_llm.create_chat_completion.side_effect = [
            {"choices": [{"message": {"content": json.dumps({
                "goal": "Buat demo.py dan jalankan",
                "requires_admin": False,
                "steps": [
                    {"id": 1, "title": "Buat file demo.py", "tool": "write_file", "risk": "write", "details": "Tulis print"},
                    {"id": 2, "title": "Jalankan demo.py", "tool": "run_command", "risk": "exec", "details": "Verifikasi output"},
                ]
            })}}]},
            {"choices": [{"message": {"content": json.dumps({
                "thought": "Saya akan membuat demo.py terlebih dahulu",
                "step_id": 1,
                "action": "write_file",
                "args": {"path": "demo.py", "content": "print('ANTIGRAVITY_SHIRO_OK')\n"}
            })}}]},
            {"choices": [{"message": {"content": json.dumps({
                "thought": "Sekarang jalankan demo.py untuk memverifikasi",
                "step_id": 2,
                "action": "run_command",
                "args": {"command": "python demo.py"}
            })}}]},
            {"choices": [{"message": {"content": json.dumps({
                "thought": "File dibuat dan berjalan lancar",
                "action": "finish",
                "final_answer": "Berhasil Kakak! File `demo.py` sudah dibuat dan menghasilkan output `ANTIGRAVITY_SHIRO_OK`."
            })}}]},
        ]

        r1 = runner.run_task("buatkan file demo.py dan jalankan", mock_llm, settings_file=self.settings_file)
        self.assertEqual(r1["status"], "awaiting_approval")
        self.assertEqual(r1["pending_action"]["tool"], "write_file")
        # Pastikan file BELUM dibuat sebelum user menyetujui!
        self.assertFalse(os.path.exists(target_file))

        # Setujui semua langkah sesi ini
        r2 = runner.resume_task(r1["task_id"], "approve_all", mock_llm, settings_file=self.settings_file)
        self.assertEqual(r2["status"], "completed")
        self.assertTrue(os.path.exists(target_file))
        self.assertIn("ANTIGRAVITY_SHIRO_OK", r2["reply"])

    def test_07_autonomous_runner_reject_leaves_workspace_untouched(self):
        """Jika user menekan Tolak (reject), file tidak dibuat dan tugas berakhir rejected."""
        runner = AutonomousAgentRunner(AgentTaskStore())
        mock_llm = MagicMock()
        mock_llm.create_chat_completion.side_effect = [
            {"choices": [{"message": {"content": json.dumps({
                "goal": "Buat rahasia.txt",
                "requires_admin": False,
                "steps": [{"id": 1, "title": "Tulis rahasia.txt", "tool": "write_file", "risk": "write", "details": ""}]
            })}}]},
            {"choices": [{"message": {"content": json.dumps({
                "thought": "Buat file",
                "step_id": 1,
                "action": "write_file",
                "args": {"path": "rahasia.txt", "content": "jangan ditulis"}
            })}}]},
        ]

        r1 = runner.run_task("buat file rahasia.txt", mock_llm, settings_file=self.settings_file)
        self.assertEqual(r1["status"], "awaiting_approval")

        r2 = runner.resume_task(r1["task_id"], "reject", mock_llm, settings_file=self.settings_file)
        self.assertEqual(r2["status"], "rejected")
        self.assertFalse(os.path.exists(os.path.join(self.ws_dir, "rahasia.txt")))
        self.assertIn("membatalkan", r2["reply"].lower())

    def test_08_autonomous_runner_auto_all_executes_end_to_end(self):
        """Pada mode auto_all, AI Agent menyusun plan dan menyelesaikan tugas tanpa jeda persetujuan."""
        save_agent_settings({"approval_mode": "auto_all"}, self.settings_file)
        runner = AutonomousAgentRunner(AgentTaskStore())
        mock_llm = MagicMock()
        mock_llm.create_chat_completion.side_effect = [
            {"choices": [{"message": {"content": json.dumps({
                "goal": "Buat catatan.txt",
                "requires_admin": False,
                "steps": [{"id": 1, "title": "Tulis catatan", "tool": "write_file", "risk": "write", "details": ""}]
            })}}]},
            {"choices": [{"message": {"content": json.dumps({
                "thought": "Tulis file catatan.txt",
                "step_id": 1,
                "action": "write_file",
                "args": {"path": "catatan.txt", "content": "Auto mode berhasil"}
            })}}]},
            {"choices": [{"message": {"content": json.dumps({
                "thought": "Selesai",
                "action": "finish",
                "final_answer": "File `catatan.txt` selesai dibuat otomatis."
            })}}]},
        ]

        res = runner.run_task("buatkan file catatan.txt", mock_llm, settings_file=self.settings_file)
        self.assertEqual(res["status"], "completed")
        self.assertTrue(os.path.exists(os.path.join(self.ws_dir, "catatan.txt")))
        with open(os.path.join(self.ws_dir, "catatan.txt"), "r", encoding="utf-8") as f:
            self.assertEqual(f.read(), "Auto mode berhasil")

    def test_09_agent_api_routes_settings_tasks_and_approve(self):
        """Uji endpoint REST /api/agent/settings, /api/agent/tasks, /api/agent/approve, dan kontrol /agent."""
        app = Flask(__name__)
        app.register_blueprint(agent_bp)
        app.register_blueprint(chat_bp)
        client = app.test_client()

        with patch("shiro.agent.local_agent.is_running_in_colab", return_value=False):
            # 1. GET / POST settings
            r_get = client.get("/api/agent/settings")
            self.assertEqual(r_get.status_code, 200)
            self.assertTrue(r_get.get_json()["is_local_pc"])

            r_post = client.post("/api/agent/settings", json={"approval_mode": "auto_safe", "allow_admin": True, "max_steps": 8})
            self.assertEqual(r_post.status_code, 200)
            pdata = r_post.get_json()
            self.assertTrue(pdata["success"])
            self.assertEqual(pdata["approval_mode"], "auto_safe")
            self.assertTrue(pdata["allow_admin"])
            self.assertEqual(pdata["max_steps"], 8)

            # 2. Slash command /agent status via /api/chat
            r_ctrl = client.post("/api/chat", json={"message": "/agent status", "stream": False})
            self.assertEqual(r_ctrl.status_code, 200)
            self.assertIn("[Agent PC]", r_ctrl.get_json()["reply"])

            # 3. Reset ke ask mode & uji approve route non-streaming via singleton runner
            save_agent_settings({"approval_mode": "ask", "allow_admin": False}, self.settings_file)
            mock_llm = MagicMock()
            mock_llm.create_chat_completion.side_effect = [
                {"choices": [{"message": {"content": json.dumps({
                    "goal": "Buat route_test.txt",
                    "requires_admin": False,
                    "steps": [{"id": 1, "title": "Tulis berkas", "tool": "write_file", "risk": "write", "details": ""}]
                })}}]},
                {"choices": [{"message": {"content": json.dumps({
                    "thought": "Buat berkas",
                    "step_id": 1,
                    "action": "write_file",
                    "args": {"path": "route_test.txt", "content": "OK_ROUTE"}
                })}}]},
                {"choices": [{"message": {"content": json.dumps({
                    "thought": "Selesai",
                    "action": "finish",
                    "final_answer": "Selesai via endpoint approve."
                })}}]},
            ]
            with patch.object(state, "llm", mock_llm):
                r_chat = client.post("/api/chat", json={"message": "buatkan file route_test.txt", "stream": False})
                self.assertEqual(r_chat.status_code, 200)
                cdata = r_chat.get_json()
                self.assertEqual(cdata["status"], "awaiting_approval")
                tid = cdata["task_id"]

                r_tasks = client.get("/api/agent/tasks")
                self.assertEqual(r_tasks.status_code, 200)
                self.assertTrue(any(t["task_id"] == tid for t in r_tasks.get_json()["tasks"]))

                r_app = client.post("/api/agent/approve", json={"task_id": tid, "decision": "approve_all", "stream": False})
                self.assertEqual(r_app.status_code, 200)
                adata = r_app.get_json()
                self.assertEqual(adata["status"], "completed")
                self.assertTrue(os.path.exists(os.path.join(self.ws_dir, "route_test.txt")))


if __name__ == "__main__":
    unittest.main()
