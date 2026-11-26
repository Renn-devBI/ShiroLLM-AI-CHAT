# -*- coding: utf-8 -*-
"""
Shiro Local PC Agent Policy & Intent Router (Antigravity Mode)
Aktif HANYA ketika berjalan di PC lokal (bukan Google Colab).
Mengatur pengaturan persetujuan, izin Administrator, deteksi tugas otonom,
dan gerbang eksekusi per-aksi.
"""

import os
import re
import json
import platform
from typing import Dict, Any, Optional, Tuple

import shiro.config as shiro_config
from shiro.models import is_running_in_colab
from shiro.agent.local_tools import get_tool_risk, is_os_admin

DEFAULT_AGENT_SETTINGS: Dict[str, Any] = {
    "enabled": True,
    "workspace_root": "",
    "approval_mode": "ask",   # "ask" | "auto_safe" | "auto_all"
    "allow_admin": False,
    "allow_outside_workspace": False,
    "max_steps": 12
}


def is_local_pc() -> bool:
    """Mengembalikan True hanya jika server berjalan di PC lokal (bukan Google Colab)."""
    return not is_running_in_colab()


def _resolve_settings_path(settings_file: Optional[str] = None) -> str:
    if settings_file:
        return settings_file
    env_p = os.environ.get("SHIRO_AGENT_SETTINGS_FILE")
    if env_p:
        return env_p
    return getattr(shiro_config, "AGENT_SETTINGS_FILE", "agent_settings.json")


def load_agent_settings(settings_file: Optional[str] = None) -> Dict[str, Any]:
    """Memuat konfigurasi Local PC Agent dari JSON dengan validasi aman."""
    cfg = dict(DEFAULT_AGENT_SETTINGS)
    path = _resolve_settings_path(settings_file)
    if path and os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                saved = json.load(f)
            if isinstance(saved, dict):
                cfg.update(saved)
        except Exception:
            pass

    cfg["enabled"] = bool(cfg.get("enabled", True))
    mode = str(cfg.get("approval_mode", "ask")).strip().lower()
    if mode not in ("ask", "auto_safe", "auto_all"):
        mode = "ask"
    cfg["approval_mode"] = mode
    cfg["allow_admin"] = bool(cfg.get("allow_admin", False))
    cfg["allow_outside_workspace"] = bool(cfg.get("allow_outside_workspace", False))
    try:
        steps = int(cfg.get("max_steps", 12))
    except Exception:
        steps = 12
    cfg["max_steps"] = max(1, min(25, steps))

    ws = str(cfg.get("workspace_root") or "").strip()
    cfg["workspace_root"] = ws
    cfg["effective_workspace"] = os.path.abspath(ws) if ws else os.path.abspath(os.getcwd())
    return cfg


def save_agent_settings(updates: Dict[str, Any], settings_file: Optional[str] = None) -> Dict[str, Any]:
    """Menyimpan pembaruan konfigurasi Local PC Agent ke JSON."""
    current = load_agent_settings(settings_file)
    if isinstance(updates, dict):
        for k in ("enabled", "workspace_root", "approval_mode", "allow_admin", "allow_outside_workspace", "max_steps"):
            if k in updates and updates[k] is not None:
                current[k] = updates[k]

    # Normalisasi ulang
    to_save = {
        "enabled": bool(current.get("enabled", True)),
        "workspace_root": str(current.get("workspace_root") or "").strip(),
        "approval_mode": str(current.get("approval_mode", "ask")).strip().lower(),
        "allow_admin": bool(current.get("allow_admin", False)),
        "allow_outside_workspace": bool(current.get("allow_outside_workspace", False)),
        "max_steps": max(1, min(25, int(current.get("max_steps", 12) or 12))),
    }
    if to_save["approval_mode"] not in ("ask", "auto_safe", "auto_all"):
        to_save["approval_mode"] = "ask"

    path = _resolve_settings_path(settings_file)
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(to_save, f, ensure_ascii=False, indent=2)

    return load_agent_settings(settings_file)


def get_agent_status(settings_file: Optional[str] = None) -> Dict[str, Any]:
    """Mengembalikan status lengkap lingkungan PC lokal dan kebijakan Agent."""
    settings = load_agent_settings(settings_file)
    local = is_local_pc()
    return {
        **settings,
        "is_local_pc": local,
        "is_colab": not local,
        "is_os_admin": is_os_admin(),
        "os_name": platform.system(),
        "effective_enabled": bool(local and settings["enabled"]),
    }


def needs_approval(
    tool_name: str,
    args: Optional[Dict[str, Any]],
    settings: Dict[str, Any],
    session_approvals: Optional[Dict[str, bool]] = None
) -> Tuple[bool, str]:
    """
    Menentukan apakah pemanggilan tool memerlukan persetujuan pengguna terlebih dahulu.
    Returns: (approval_needed, reason)
    """
    risk = get_tool_risk(tool_name)
    sess = session_approvals or {}
    mode = str(settings.get("approval_mode", "ask")).lower()
    allow_admin = bool(settings.get("allow_admin", False))

    if risk == "read":
        return False, "read_only"

    if risk == "admin":
        if sess.get("approve_admin"):
            return False, "session_admin_approved"
        if mode == "auto_all" and allow_admin:
            return False, "pre_authorized_admin"
        return True, "memerlukan persetujuan akses Administrator (UAC)"

    if risk == "destructive":
        if sess.get("approve_all") or mode == "auto_all":
            return False, "auto_approved"
        return True, "aksi penghapusan memerlukan persetujuan"

    # write / exec
    if sess.get("approve_all") or mode in ("auto_safe", "auto_all"):
        return False, "auto_approved"
    return True, "menunggu persetujuan sebelum mengubah file / menjalankan perintah"


def parse_agent_command(text: str) -> Optional[Dict[str, Any]]:
    """
    Memparsing perintah slash eksplisit Agent:
    - /agent status
    - /agent mode <ask|auto_safe|auto_all>
    - /agent admin <on|off|true|false>
    - /agent <on|off>
    - /agent <task> | /task <task> | /do <task> | /plan <task>
    """
    raw = (text or "").strip()
    if not raw:
        return None

    m_status = re.match(r'^/agent\s+status\s*$', raw, flags=re.IGNORECASE)
    if m_status:
        return {"cmd": "status"}

    m_mode = re.match(r'^/agent\s+mode\s+(ask|auto_safe|auto_all)\s*$', raw, flags=re.IGNORECASE)
    if m_mode:
        return {"cmd": "mode", "value": m_mode.group(1).lower()}

    m_admin = re.match(r'^/agent\s+admin\s+(on|off|true|false)\s*$', raw, flags=re.IGNORECASE)
    if m_admin:
        return {"cmd": "admin", "value": m_admin.group(1).lower() in ("on", "true")}

    m_toggle = re.match(r'^/agent\s+(on|off)\s*$', raw, flags=re.IGNORECASE)
    if m_toggle:
        return {"cmd": "enabled", "value": m_toggle.group(1).lower() == "on"}

    m_run = re.match(r'^/(?:agent|task|do|plan)\s+(.+)$', raw, flags=re.IGNORECASE | re.DOTALL)
    if m_run:
        return {"cmd": "run", "task": m_run.group(1).strip()}

    return None


_QA_PREFIX_RE = re.compile(
    r'^(?:apa\s+itu|jelaskan\s+(?:apa\s+itu|tentang)|kenapa|mengapa|siapa|kapan|di\s+mana|bagaimana\s+cara)\b',
    flags=re.IGNORECASE
)
_FILE_EXT_RE = re.compile(
    r'\b[\w\-/\\]+\.(?:py|js|ts|jsx|tsx|html|css|json|md|txt|ps1|bat|sh|yaml|yml|toml|env|cfg|ini|sql|cpp|c|java|go|rs)\b',
    flags=re.IGNORECASE
)
_FILE_ACTION_RE = re.compile(
    r'\b(?:buat|buatkan|bikin|bikinkan|tulis|tuliskan|edit|ubah|modifikasi|perbaiki|fix|hapus|delete|create|write|update|generate|refactor)\b'
    r'.*?\b(?:file|berkas|script|skrip|folder|direktori|proyek|project|aplikasi|program|kode|modul|halaman\s+web)\b',
    flags=re.IGNORECASE
)
_WORKSPACE_INSPECT_RE = re.compile(
    r'\b(?:cek|lihat|baca|scan|cari|periksa|inspect|read|list)\b'
    r'.*?\b(?:file|berkas|folder|direktori|workspace|proyek|project|isi\s+folder|kode\s+di)\b',
    flags=re.IGNORECASE
)
_PC_CMD_ACTION_RE = re.compile(
    r'\b(?:jalankan|eksekusi|run|execute|install|uninstall|aktifkan|matikan|restart|bersihkan|clean|atur|konfigurasi|uji|test)\b'
    r'.*?\b(?:admin|administrator|uac|runas|elevated|service|layanan|firewall|port|pip|npm|git|script|skrip|powershell|cmd|terminal|unittest|pytest)\b',
    flags=re.IGNORECASE
)
_ADMIN_EXPLICIT_RE = re.compile(
    r'(?:\b(?:sebagai|akses|hak|mode)\s+admin(?:istrator)?\b|\bas\s+admin(?:istrator)?\b|\bvia\s+uac\b|\brun\s+as\s+admin\b)',
    flags=re.IGNORECASE
)
_PLAN_EXEC_RE = re.compile(
    r'(?:\bbuatkan\s+planning\s+(?:dan\s+)?(?:kerjakan|eksekusi|buat)\b|\brencanakan\s+dan\s+(?:kerjakan|eksekusi|buat|ubah)\b|\bselesaikan\s+tugas\b|\bkerjakan\s+secara\s+otonom\b)',
    flags=re.IGNORECASE
)


def detect_local_agent_task(text: str) -> Dict[str, Any]:
    """
    Mendeteksi apakah pesan merupakan tugas AI Agent PC lokal (coding, manipulasi berkas,
    perintah sistem, atau eksekusi Administrator) tanpa mencegat obrolan/cuaca/web search.
    """
    raw = (text or "").strip()
    if not raw:
        return {"is_agent_task": False, "task": "", "reason": "empty", "explicit": False}

    slash = parse_agent_command(raw)
    if slash:
        if slash["cmd"] == "run":
            return {"is_agent_task": True, "task": slash["task"], "reason": "slash_command", "explicit": True}
        return {"is_agent_task": False, "task": "", "reason": "control_command", "explicit": False}

    low = raw.lower()

    # Kecualikan URL web / screenshot / cuaca / jam / pencarian web eksplisit
    if re.search(r'https?://[^\s]+', raw):
        return {"is_agent_task": False, "task": "", "reason": "url_browse", "explicit": False}
    if any(w in low for w in ("screenshot", "tangkapan layar", "cuaca", "hujan", "jam berapa", "hari apa", "tanggal berapa", "cari di google", "cari di web", "googling", "berita terbaru", "anime populer")):
        return {"is_agent_task": False, "task": "", "reason": "web_or_info_query", "explicit": False}

    has_file_ext = bool(_FILE_EXT_RE.search(raw))
    has_file_action = bool(_FILE_ACTION_RE.search(low))
    has_ws_inspect = bool(_WORKSPACE_INSPECT_RE.search(low))
    has_pc_cmd = bool(_PC_CMD_ACTION_RE.search(low))
    has_admin = bool(_ADMIN_EXPLICIT_RE.search(low))
    has_plan_exec = bool(_PLAN_EXEC_RE.search(low))

    has_action_verb = bool(re.search(
        r'\b(?:buat|buatkan|bikin|bikinkan|tulis|edit|ubah|perbaiki|fix|hapus|delete|jalankan|eksekusi|run|execute|cek|baca|create|write|update|test)\b',
        low
    ))

    # Jika pertanyaan konseptual ("apa itu file python?", "bagaimana cara install...?") tanpa aksi konkret -> bukan tugas agent
    if _QA_PREFIX_RE.match(low) and not (has_file_action or has_pc_cmd or has_admin or has_plan_exec or (has_file_ext and has_action_verb)):
        return {"is_agent_task": False, "task": "", "reason": "conceptual_question", "explicit": False}

    if has_admin:
        return {"is_agent_task": True, "task": raw, "reason": "admin_task", "explicit": False}
    if has_plan_exec:
        return {"is_agent_task": True, "task": raw, "reason": "autonomous_plan_task", "explicit": False}
    if has_file_action:
        return {"is_agent_task": True, "task": raw, "reason": "file_action", "explicit": False}
    if has_file_ext and has_action_verb:
        return {"is_agent_task": True, "task": raw, "reason": "target_filename_action", "explicit": False}
    if has_pc_cmd:
        return {"is_agent_task": True, "task": raw, "reason": "pc_command_task", "explicit": False}
    if has_ws_inspect:
        return {"is_agent_task": True, "task": raw, "reason": "workspace_inspection", "explicit": False}

    return {"is_agent_task": False, "task": "", "reason": "normal_chat", "explicit": False}


def should_route_to_local_agent(
    text: str,
    has_image: bool = False,
    settings_file: Optional[str] = None
) -> Dict[str, Any]:
    """
    Gerbang utama: hanya merutekan ke Local PC Agent jika berjalan di PC lokal,
    fitur aktif, bukan giliran gambar (kecuali perintah /agent), dan terdeteksi sebagai tugas agent.
    """
    if not is_local_pc():
        return {"route": False, "task": "", "reason": "not_local_pc", "explicit": False}

    settings = load_agent_settings(settings_file)
    if not settings.get("enabled", True):
        return {"route": False, "task": "", "reason": "disabled", "explicit": False}

    det = detect_local_agent_task(text)
    if has_image and not det.get("explicit"):
        return {"route": False, "task": "", "reason": "image_turn", "explicit": False}

    return {
        "route": bool(det["is_agent_task"]),
        "task": det["task"],
        "reason": det["reason"],
        "explicit": det["explicit"]
    }
