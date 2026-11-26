# -*- coding: utf-8 -*-
"""
Shiro Local PC Toolset (Antigravity Mode)
Menyediakan akses file workspace, pencarian kode, eksekusi terminal standar,
dan eksekusi Administrator (Windows UAC / RunAs) secara aman & terstruktur.
"""

import os
import re
import fnmatch
import ctypes
import shutil
import platform
import tempfile
import subprocess
import uuid
from typing import Dict, Any, List, Optional, Tuple

TOOL_RISK_LEVELS: Dict[str, str] = {
    "list_dir": "read",
    "search_files": "read",
    "read_file": "read",
    "write_file": "write",
    "edit_file": "write",
    "run_command": "exec",
    "delete_file": "destructive",
    "run_admin_command": "admin",
}

SKIP_SCAN_DIRS = {
    ".git", "__pycache__", "node_modules", "venv", "vevn2", "vevn", ".venv", ".mypy_cache", ".pytest_cache"
}

LOCAL_TOOLS_SCHEMA_PROMPT = """Daftar Tools PC Lokal yang tersedia:
1. list_dir(path=".", max_entries=100) [risk: read] — Melihat daftar berkas dan subfolder di workspace.
2. search_files(pattern="*", path=".", content_query=null, max_results=40) [risk: read] — Mencari nama berkas (glob) atau isi teks di dalam berkas.
3. read_file(path, start_line=1, end_line=250) [risk: read] — Membaca isi berkas dengan nomor baris.
4. write_file(path, content, overwrite=true, append=false) [risk: write] — Membuat berkas baru atau menulis ulang/menambah isi berkas (membuat folder induk otomatis).
5. edit_file(path, target, replacement) [risk: write] — Mengubah blok teks persis (`target` -> `replacement`) di dalam berkas.
6. delete_file(path) [risk: destructive] — Menghapus satu berkas atau folder kosong.
7. run_command(command, cwd=null, timeout=60) [risk: exec] — Menjalankan perintah terminal PowerShell/Bash biasa di workspace.
8. run_admin_command(command, cwd=null, timeout=90) [risk: admin] — Menjalankan perintah dengan hak akses Administrator (Windows UAC / RunAs)."""


def get_tool_risk(tool_name: str) -> str:
    """Mengembalikan kategori risiko tool ('read', 'write', 'exec', 'destructive', 'admin')."""
    return TOOL_RISK_LEVELS.get((tool_name or "").strip(), "exec")


_DANGEROUS_COMMAND_PATTERNS: List[Tuple[str, str]] = [
    (r'\bformat\s+[a-z]:', "Perintah format partisi disk diblokir."),
    (r'\bdiskpart\b', "Perintah diskpart diblokir demi keamanan partisi."),
    (r'\bdel\s+[^#\n]*\s+c:\\windows\b', "Penghapusan direktori Windows diblokir."),
    (r'\bdel\s+/[sfq]+\s+c:\\windows\b', "Penghapusan direktori Windows diblokir."),
    (r'\b(?:rd|rmdir)\s+/[sq]+\s+c:\\(?:\s|$|["\'])', "Penghapusan root drive C:\\ diblokir."),
    (r'\bremove-item\b[^\n]*\bc:\\(?:windows)?\b[^\n]*-recurse', "Penghapusan rekursif root C:\\ diblokir."),
    (r'\brm\s+-[rf]{1,2}\s+/(?:\s|$|\*)', "Penghapusan root filesystem '/' diblokir."),
    (r'\bmkfs\b', "Pembuatan filesystem (mkfs) diblokir."),
    (r':\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:', "Fork bomb diblokir."),
    (r'\bbcdedit\s+/delete\b', "Penghapusan boot configuration (bcdedit) diblokir."),
    (r'\breg\s+delete\s+hklm\\system\b', "Penghapusan registry HKLM\\SYSTEM diblokir."),
    (r'\bshutdown\s+/s\s+/t\s+0\b', "Shutdown paksa seketika diblokir."),
    (r'\bcipher\s+/w:c:', "Penghapusan ruang bebas drive sistem (cipher /w:c:) diblokir."),
]


def is_dangerous_command(command: str) -> Optional[str]:
    """Memeriksa apakah perintah termasuk pola katastropik yang selalu diblokir."""
    if not command:
        return None
    low = command.lower().strip()
    for pat, reason in _DANGEROUS_COMMAND_PATTERNS:
        if re.search(pat, low, re.IGNORECASE):
            return reason
    return None


def is_os_admin() -> bool:
    """Memeriksa apakah proses Python saat ini berjalan dengan hak Administrator / root."""
    try:
        if os.name == "nt" or platform.system().lower() == "windows":
            return bool(ctypes.windll.shell32.IsUserAnAdmin())
        if hasattr(os, "geteuid"):
            return os.geteuid() == 0
    except Exception:
        pass
    return False


def resolve_safe_path(
    path: str,
    workspace_root: str,
    allow_outside_workspace: bool = False
) -> Tuple[bool, str, str]:
    """
    Menyelesaikan path relatif terhadap workspace_root dan memastikan tidak keluar
    dari workspace kecuali allow_outside_workspace=True.
    Returns: (ok, abs_target, error_message)
    """
    abs_ws = os.path.abspath(workspace_root or ".")
    raw = (path or ".").strip()
    if os.path.isabs(raw):
        abs_target = os.path.abspath(raw)
    else:
        abs_target = os.path.abspath(os.path.join(abs_ws, raw))

    if not allow_outside_workspace:
        try:
            common = os.path.commonpath([abs_ws, abs_target])
            if os.path.normcase(common) != os.path.normcase(abs_ws):
                return (
                    False,
                    abs_target,
                    f"Akses ditolak: path '{raw}' berada di luar workspace '{abs_ws}'."
                )
        except ValueError:
            return (
                False,
                abs_target,
                f"Akses ditolak: drive/root '{raw}' berbeda dengan workspace '{abs_ws}'."
            )

    return True, abs_target, ""


def _tool_result(
    tool: str,
    success: bool,
    summary: str,
    data: Any = None,
    error: Optional[str] = None
) -> Dict[str, Any]:
    return {
        "success": success,
        "tool": tool,
        "summary": summary,
        "data": data,
        "error": error
    }


def tool_list_dir(
    path: str = ".",
    max_entries: int = 100,
    workspace_root: str = ".",
    allow_outside_workspace: bool = False
) -> Dict[str, Any]:
    """Melihat isi direktori dengan filter folder berat."""
    ok, target, err = resolve_safe_path(path, workspace_root, allow_outside_workspace)
    if not ok:
        return _tool_result("list_dir", False, err, error=err)
    if not os.path.exists(target):
        msg = f"Direktori tidak ditemukan: {path}"
        return _tool_result("list_dir", False, msg, error=msg)
    if not os.path.isdir(target):
        msg = f"Path bukan direktori: {path}"
        return _tool_result("list_dir", False, msg, error=msg)

    entries: List[str] = []
    try:
        items = sorted(os.listdir(target))
        for name in items:
            if name in SKIP_SCAN_DIRS:
                continue
            full = os.path.join(target, name)
            if os.path.isdir(full):
                entries.append(f"[DIR]  {name}/")
            else:
                try:
                    sz = os.path.getsize(full)
                except OSError:
                    sz = 0
                entries.append(f"[FILE] {name} ({sz} bytes)")
            if len(entries) >= max_entries:
                entries.append(f"... [Dibatasi {max_entries} entri]")
                break
        summary = f"Isi direktori '{path}' ({len(entries)} entri):\n" + ("\n".join(entries) if entries else "(kosong)")
        return _tool_result("list_dir", True, summary, data={"path": target, "entries": entries})
    except Exception as e:
        msg = f"Gagal membaca direktori '{path}': {e}"
        return _tool_result("list_dir", False, msg, error=str(e))


def tool_search_files(
    pattern: str = "*",
    path: str = ".",
    content_query: Optional[str] = None,
    max_results: int = 40,
    workspace_root: str = ".",
    allow_outside_workspace: bool = False
) -> Dict[str, Any]:
    """Mencari berkas berdasarkan pola nama glob dan/atau kecocokan isi teks (case-insensitive)."""
    ok, target, err = resolve_safe_path(path, workspace_root, allow_outside_workspace)
    if not ok:
        return _tool_result("search_files", False, err, error=err)
    if not os.path.exists(target):
        msg = f"Path pencarian tidak ditemukan: {path}"
        return _tool_result("search_files", False, msg, error=msg)

    pat = (pattern or "*").strip()
    query_low = content_query.lower() if content_query else None
    matches: List[Dict[str, Any]] = []
    abs_ws = os.path.abspath(workspace_root or ".")

    try:
        for root, dirs, files in os.walk(target):
            dirs[:] = [d for d in sorted(dirs) if d not in SKIP_SCAN_DIRS]
            for fn in sorted(files):
                if pat != "*" and not (fnmatch.fnmatch(fn.lower(), pat.lower()) or pat.lower() in fn.lower()):
                    continue
                full_p = os.path.join(root, fn)
                rel_p = os.path.relpath(full_p, abs_ws).replace("\\", "/")
                if query_low:
                    try:
                        if os.path.getsize(full_p) > 2 * 1024 * 1024:
                            continue
                        with open(full_p, "r", encoding="utf-8", errors="ignore") as f:
                            for line_no, line in enumerate(f, 1):
                                if query_low in line.lower():
                                    matches.append({
                                        "file": rel_p,
                                        "line": line_no,
                                        "snippet": line.strip()[:160]
                                    })
                                    if len(matches) >= max_results:
                                        break
                    except Exception:
                        continue
                else:
                    matches.append({"file": rel_p})

                if len(matches) >= max_results:
                    break
            if len(matches) >= max_results:
                break

        lines_out = []
        for m in matches:
            if "line" in m:
                lines_out.append(f"{m['file']}:{m['line']}: {m['snippet']}")
            else:
                lines_out.append(m["file"])
        summary = f"Ditemukan {len(matches)} hasil pencarian:" + ("\n" + "\n".join(lines_out) if lines_out else " (tidak ada yang cocok)")
        return _tool_result("search_files", True, summary, data={"matches": matches})
    except Exception as e:
        msg = f"Gagal mencari berkas: {e}"
        return _tool_result("search_files", False, msg, error=str(e))


def tool_read_file(
    path: str,
    start_line: int = 1,
    end_line: int = 250,
    workspace_root: str = ".",
    allow_outside_workspace: bool = False
) -> Dict[str, Any]:
    """Membaca berkas teks UTF-8 dengan nomor baris (maks 25.000 karakter)."""
    ok, target, err = resolve_safe_path(path, workspace_root, allow_outside_workspace)
    if not ok:
        return _tool_result("read_file", False, err, error=err)
    if not os.path.exists(target) or not os.path.isfile(target):
        msg = f"Berkas tidak ditemukan: {path}"
        return _tool_result("read_file", False, msg, error=msg)

    try:
        s_line = max(1, int(start_line or 1))
        e_line = max(s_line, int(end_line or (s_line + 249)))
        with open(target, "r", encoding="utf-8", errors="replace") as f:
            all_lines = f.readlines()
        total_lines = len(all_lines)
        selected = all_lines[s_line - 1 : e_line]
        numbered = [f"{idx}: {ln.rstrip()}" for idx, ln in enumerate(selected, start=s_line)]
        text_out = "\n".join(numbered)
        if len(text_out) > 25000:
            text_out = text_out[:25000] + "\n... [Isi berkas dipotong pada batas 25.000 karakter]"
        summary = f"Membaca '{path}' (baris {s_line}-{min(e_line, total_lines)} dari {total_lines}):\n{text_out}"
        return _tool_result(
            "read_file",
            True,
            summary,
            data={"path": target, "total_lines": total_lines, "content": text_out}
        )
    except Exception as e:
        msg = f"Gagal membaca berkas '{path}': {e}"
        return _tool_result("read_file", False, msg, error=str(e))


def tool_write_file(
    path: str,
    content: str,
    overwrite: bool = True,
    append: bool = False,
    workspace_root: str = ".",
    allow_outside_workspace: bool = False
) -> Dict[str, Any]:
    """Membuat berkas baru atau menimpa/menambahkan konten dengan pembuatan folder induk otomatis."""
    ok, target, err = resolve_safe_path(path, workspace_root, allow_outside_workspace)
    if not ok:
        return _tool_result("write_file", False, err, error=err)

    if os.path.exists(target) and not overwrite and not append:
        msg = f"Berkas '{path}' sudah ada dan overwrite=False."
        return _tool_result("write_file", False, msg, error=msg)

    try:
        parent = os.path.dirname(target)
        if parent:
            os.makedirs(parent, exist_ok=True)
        mode = "a" if append else "w"
        text = content if content is not None else ""
        with open(target, mode, encoding="utf-8") as f:
            f.write(text)
        sz = os.path.getsize(target)
        verb = "Ditambahkan ke" if append else "Ditulis ke"
        summary = f"Berhasil {verb.lower()} berkas '{path}' ({sz} bytes)."
        return _tool_result("write_file", True, summary, data={"path": target, "bytes": sz})
    except Exception as e:
        msg = f"Gagal menulis berkas '{path}': {e}"
        return _tool_result("write_file", False, msg, error=str(e))


def tool_edit_file(
    path: str,
    target: str,
    replacement: str,
    workspace_root: str = ".",
    allow_outside_workspace: bool = False
) -> Dict[str, Any]:
    """Mengganti blok teks persis (`target` -> `replacement`) di dalam berkas."""
    ok, target_path, err = resolve_safe_path(path, workspace_root, allow_outside_workspace)
    if not ok:
        return _tool_result("edit_file", False, err, error=err)
    if not os.path.exists(target_path) or not os.path.isfile(target_path):
        msg = f"Berkas tidak ditemukan: {path}"
        return _tool_result("edit_file", False, msg, error=msg)

    try:
        with open(target_path, "r", encoding="utf-8") as f:
            original = f.read()
        if target not in original:
            msg = f"Teks target tidak ditemukan di dalam '{path}'. Pastikan ejaan dan spasi sesuai dengan hasil read_file."
            return _tool_result("edit_file", False, msg, error=msg)
        count = original.count(target)
        updated = original.replace(target, replacement)
        with open(target_path, "w", encoding="utf-8") as f:
            f.write(updated)
        summary = f"Berhasil mengedit berkas '{path}' ({count} blok diganti)."
        return _tool_result("edit_file", True, summary, data={"path": target_path, "replacements": count})
    except Exception as e:
        msg = f"Gagal mengedit berkas '{path}': {e}"
        return _tool_result("edit_file", False, msg, error=str(e))


def tool_delete_file(
    path: str,
    workspace_root: str = ".",
    allow_outside_workspace: bool = False
) -> Dict[str, Any]:
    """Menghapus satu berkas atau direktori kosong (tidak boleh menghapus root workspace)."""
    ok, target, err = resolve_safe_path(path, workspace_root, allow_outside_workspace)
    if not ok:
        return _tool_result("delete_file", False, err, error=err)

    abs_ws = os.path.abspath(workspace_root or ".")
    if os.path.normcase(target) == os.path.normcase(abs_ws):
        msg = "Ditolak: tidak boleh menghapus folder root workspace."
        return _tool_result("delete_file", False, msg, error=msg)
    if not os.path.exists(target):
        msg = f"Target tidak ditemukan: {path}"
        return _tool_result("delete_file", False, msg, error=msg)

    try:
        if os.path.isdir(target):
            if os.listdir(target):
                msg = f"Ditolak: direktori '{path}' tidak kosong."
                return _tool_result("delete_file", False, msg, error=msg)
            os.rmdir(target)
            return _tool_result("delete_file", True, f"Direktori kosong '{path}' berhasil dihapus.", data={"path": target})
        os.remove(target)
        return _tool_result("delete_file", True, f"Berkas '{path}' berhasil dihapus.", data={"path": target})
    except Exception as e:
        msg = f"Gagal menghapus '{path}': {e}"
        return _tool_result("delete_file", False, msg, error=str(e))


def _resolve_cwd(cwd: Optional[str], workspace_root: str, allow_outside_workspace: bool) -> Tuple[bool, str, str]:
    abs_ws = os.path.abspath(workspace_root or ".")
    if not cwd:
        return True, abs_ws, ""
    ok, target_cwd, err = resolve_safe_path(cwd, abs_ws, allow_outside_workspace)
    if not ok:
        return False, target_cwd, err
    if not os.path.isdir(target_cwd):
        return False, target_cwd, f"Working directory tidak ditemukan: {cwd}"
    return True, target_cwd, ""


def tool_run_command(
    command: str,
    cwd: Optional[str] = None,
    timeout: int = 60,
    workspace_root: str = ".",
    allow_outside_workspace: bool = False
) -> Dict[str, Any]:
    """Menjalankan perintah terminal standar (PowerShell di Windows, Bash di Linux/macOS)."""
    clean_cmd = (command or "").strip()
    if not clean_cmd:
        return _tool_result("run_command", False, "Perintah kosong.", error="Perintah kosong.")

    danger_reason = is_dangerous_command(clean_cmd)
    if danger_reason:
        return _tool_result("run_command", False, f"Diblokir demi keamanan: {danger_reason}", error=danger_reason)

    ok_cwd, work_dir, err_cwd = _resolve_cwd(cwd, workspace_root, allow_outside_workspace)
    if not ok_cwd:
        return _tool_result("run_command", False, err_cwd, error=err_cwd)

    is_windows = os.name == "nt" or platform.system().lower() == "windows"
    if is_windows:
        cmd_args = ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", clean_cmd]
        env_label = "PowerShell"
    else:
        cmd_args = ["bash", "-c", clean_cmd]
        env_label = "Bash"

    try:
        res = subprocess.run(cmd_args, cwd=work_dir, capture_output=True, text=True, timeout=int(timeout or 60))
        stdout = (res.stdout or "").strip()
        stderr = (res.stderr or "").strip()
        if len(stdout) > 6000:
            stdout = stdout[:6000] + f"\n... [Output dipotong, total {len(res.stdout)} karakter]"
        if len(stderr) > 3000:
            stderr = stderr[:3000] + "\n... [Stderr dipotong]"

        success = res.returncode == 0
        summary = (
            f"Perintah `{clean_cmd}` ({env_label}) selesai dengan Exit Code {res.returncode}.\n"
            f"Output:\n{stdout or stderr or '(tanpa output teks)'}"
        )
        return _tool_result(
            "run_command",
            success,
            summary,
            data={"command": clean_cmd, "cwd": work_dir, "returncode": res.returncode, "stdout": stdout, "stderr": stderr},
            error=None if success else (stderr or f"Exit code {res.returncode}")
        )
    except subprocess.TimeoutExpired:
        msg = f"Perintah `{clean_cmd}` melewati batas waktu ({timeout}s)."
        return _tool_result("run_command", False, msg, error=msg)
    except Exception as e:
        msg = f"Gagal mengeksekusi perintah `{clean_cmd}`: {e}"
        return _tool_result("run_command", False, msg, error=str(e))


def tool_run_admin_command(
    command: str,
    cwd: Optional[str] = None,
    timeout: int = 90,
    workspace_root: str = ".",
    allow_outside_workspace: bool = False
) -> Dict[str, Any]:
    """
    Menjalankan perintah dengan hak akses Administrator (Windows UAC / Start-Process -Verb RunAs)
    atau sudo non-interaktif di Linux/macOS.
    """
    clean_cmd = (command or "").strip()
    if not clean_cmd:
        return _tool_result("run_admin_command", False, "Perintah kosong.", error="Perintah kosong.")

    danger_reason = is_dangerous_command(clean_cmd)
    if danger_reason:
        return _tool_result("run_admin_command", False, f"Diblokir demi keamanan: {danger_reason}", error=danger_reason)

    ok_cwd, work_dir, err_cwd = _resolve_cwd(cwd, workspace_root, allow_outside_workspace)
    if not ok_cwd:
        return _tool_result("run_admin_command", False, err_cwd, error=err_cwd)

    is_windows = os.name == "nt" or platform.system().lower() == "windows"
    if not is_windows:
        if is_os_admin():
            cmd_args = ["bash", "-c", clean_cmd]
        else:
            cmd_args = ["sudo", "-n", "bash", "-c", clean_cmd]
        try:
            res = subprocess.run(cmd_args, cwd=work_dir, capture_output=True, text=True, timeout=int(timeout or 90))
            stdout = (res.stdout or "").strip()[:6000]
            stderr = (res.stderr or "").strip()[:3000]
            success = res.returncode == 0
            if not success and "password is required" in stderr.lower():
                stderr = "Akses root/sudo memerlukan autentikasi interaktif (tidak tersedia pada mode headless)."
            summary = f"[ADMIN] Perintah `{clean_cmd}` selesai dengan Exit Code {res.returncode}.\n{stdout or stderr or '(tanpa output)'}"
            return _tool_result(
                "run_admin_command",
                success,
                summary,
                data={"command": clean_cmd, "elevated": True, "returncode": res.returncode, "stdout": stdout, "stderr": stderr},
                error=None if success else stderr
            )
        except Exception as e:
            msg = f"[ADMIN] Gagal menjalankan perintah: {e}"
            return _tool_result("run_admin_command", False, msg, error=str(e))

    # Windows: jika sudah berjalan sebagai Administrator, jalankan langsung
    if is_os_admin():
        try:
            res = subprocess.run(
                ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", clean_cmd],
                cwd=work_dir,
                capture_output=True,
                text=True,
                timeout=int(timeout or 90)
            )
            stdout = (res.stdout or "").strip()[:6000]
            stderr = (res.stderr or "").strip()[:3000]
            success = res.returncode == 0
            summary = (
                f"[ADMIN] Perintah `{clean_cmd}` selesai dengan Exit Code {res.returncode}.\n"
                f"Output:\n{stdout or stderr or '(tanpa output teks)'}"
            )
            return _tool_result(
                "run_admin_command",
                success,
                summary,
                data={"command": clean_cmd, "cwd": work_dir, "elevated": True, "returncode": res.returncode, "stdout": stdout, "stderr": stderr},
                error=None if success else (stderr or f"Exit code {res.returncode}")
            )
        except Exception as e:
            msg = f"[ADMIN] Gagal mengeksekusi perintah: {e}"
            return _tool_result("run_admin_command", False, msg, error=str(e))

    # Windows non-admin: gunakan Start-Process ... -Verb RunAs agar UAC resmi muncul dan output tertangkap
    uid = uuid.uuid4().hex[:10]
    tmp_dir = tempfile.gettempdir()
    ps1_path = os.path.join(tmp_dir, f"shiro_admin_{uid}.ps1")
    out_path = os.path.join(tmp_dir, f"shiro_admin_{uid}.out")
    code_path = os.path.join(tmp_dir, f"shiro_admin_{uid}.code")

    safe_cwd = work_dir.replace("'", "''")
    safe_out = out_path.replace("'", "''")
    safe_code = code_path.replace("'", "''")
    ps1_body = (
        f"$ErrorActionPreference = 'Continue'\n"
        f"Set-Location -LiteralPath '{safe_cwd}'\n"
        f"$__shiro_ok = $true\n"
        f"$__shiro_exit = 0\n"
        f"try {{\n"
        f"    & {{\n"
        f"        {clean_cmd}\n"
        f"    }} *>&1 | Out-File -FilePath '{safe_out}' -Encoding utf8\n"
        f"    if ($null -ne $LASTEXITCODE) {{ $__shiro_exit = [int]$LASTEXITCODE }} elseif (-not $?) {{ $__shiro_exit = 1 }}\n"
        f"}} catch {{\n"
        f"    $_ | Out-String | Out-File -FilePath '{safe_out}' -Append -Encoding utf8\n"
        f"    $__shiro_exit = 1\n"
        f"}}\n"
        f"Set-Content -Path '{safe_code}' -Value $__shiro_exit -Encoding ascii\n"
    )

    try:
        with open(ps1_path, "w", encoding="utf-8") as f:
            f.write(ps1_body)

        safe_ps1 = ps1_path.replace("'", "''")
        launch_cmd = (
            f"$p = Start-Process -FilePath 'powershell.exe' "
            f"-ArgumentList @('-NoProfile','-ExecutionPolicy','Bypass','-WindowStyle','Hidden','-File','{safe_ps1}') "
            f"-Verb RunAs -Wait -PassThru; "
            f"if ($null -ne $p) {{ exit $p.ExitCode }}"
        )
        res = subprocess.run(
            ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", launch_cmd],
            capture_output=True,
            text=True,
            timeout=int(timeout or 90)
        )
        launcher_err = (res.stderr or "").strip()

        if res.returncode != 0 and not os.path.exists(code_path):
            if "canceled by the user" in launcher_err.lower() or "cancelled" in launcher_err.lower() or "1223" in launcher_err:
                msg = "UAC dibatalkan oleh pengguna."
            else:
                msg = f"Gagal elevasi UAC: {launcher_err or f'Exit code {res.returncode}'}"
            return _tool_result(
                "run_admin_command",
                False,
                msg,
                data={"command": clean_cmd, "elevated": True, "returncode": res.returncode, "stdout": "", "stderr": msg},
                error=msg
            )

        stdout = ""
        if os.path.exists(out_path):
            with open(out_path, "r", encoding="utf-8-sig", errors="replace") as f_out:
                stdout = f_out.read().strip()[:6000]

        exit_code = 0
        if os.path.exists(code_path):
            with open(code_path, "r", encoding="utf-8", errors="ignore") as f_code:
                raw_code = f_code.read().strip()
                if raw_code:
                    try:
                        exit_code = int(raw_code)
                    except ValueError:
                        exit_code = res.returncode

        success = exit_code == 0
        summary = (
            f"[ADMIN UAC] Perintah `{clean_cmd}` selesai dengan Exit Code {exit_code}.\n"
            f"Output:\n{stdout or '(tanpa output teks)'}"
        )
        return _tool_result(
            "run_admin_command",
            success,
            summary,
            data={"command": clean_cmd, "cwd": work_dir, "elevated": True, "returncode": exit_code, "stdout": stdout, "stderr": ""},
            error=None if success else (stdout or f"Exit code {exit_code}")
        )
    except subprocess.TimeoutExpired:
        msg = f"[ADMIN UAC] Perintah `{clean_cmd}` melewati batas waktu ({timeout}s)."
        return _tool_result("run_admin_command", False, msg, error=msg)
    except Exception as e:
        msg = f"[ADMIN UAC] Gagal menjalankan perintah Administrator: {e}"
        return _tool_result("run_admin_command", False, msg, error=str(e))
    finally:
        for tmp_f in (ps1_path, out_path, code_path):
            try:
                if os.path.exists(tmp_f):
                    os.remove(tmp_f)
            except Exception:
                pass


def execute_local_tool(
    tool_name: str,
    args: Optional[Dict[str, Any]],
    workspace_root: str = ".",
    allow_outside_workspace: bool = False
) -> Dict[str, Any]:
    """Dispatcher terpusat untuk seluruh tools PC lokal."""
    name = (tool_name or "").strip()
    p = args if isinstance(args, dict) else {}

    if name == "list_dir":
        return tool_list_dir(
            path=p.get("path", "."),
            max_entries=int(p.get("max_entries", 100) or 100),
            workspace_root=workspace_root,
            allow_outside_workspace=allow_outside_workspace
        )
    if name == "search_files":
        return tool_search_files(
            pattern=p.get("pattern", "*"),
            path=p.get("path", "."),
            content_query=p.get("content_query"),
            max_results=int(p.get("max_results", 40) or 40),
            workspace_root=workspace_root,
            allow_outside_workspace=allow_outside_workspace
        )
    if name == "read_file":
        return tool_read_file(
            path=p.get("path", ""),
            start_line=int(p.get("start_line", 1) or 1),
            end_line=int(p.get("end_line", 250) or 250),
            workspace_root=workspace_root,
            allow_outside_workspace=allow_outside_workspace
        )
    if name == "write_file":
        return tool_write_file(
            path=p.get("path", ""),
            content=p.get("content", ""),
            overwrite=bool(p.get("overwrite", True)),
            append=bool(p.get("append", False)),
            workspace_root=workspace_root,
            allow_outside_workspace=allow_outside_workspace
        )
    if name == "edit_file":
        return tool_edit_file(
            path=p.get("path", ""),
            target=p.get("target", ""),
            replacement=p.get("replacement", ""),
            workspace_root=workspace_root,
            allow_outside_workspace=allow_outside_workspace
        )
    if name == "delete_file":
        return tool_delete_file(
            path=p.get("path", ""),
            workspace_root=workspace_root,
            allow_outside_workspace=allow_outside_workspace
        )
    if name == "run_command":
        return tool_run_command(
            command=p.get("command", ""),
            cwd=p.get("cwd"),
            timeout=int(p.get("timeout", 60) or 60),
            workspace_root=workspace_root,
            allow_outside_workspace=allow_outside_workspace
        )
    if name == "run_admin_command":
        return tool_run_admin_command(
            command=p.get("command", ""),
            cwd=p.get("cwd"),
            timeout=int(p.get("timeout", 90) or 90),
            workspace_root=workspace_root,
            allow_outside_workspace=allow_outside_workspace
        )

    return _tool_result(name or "unknown", False, f"Tool '{name}' tidak dikenal.", error=f"Unknown tool: {name}")
