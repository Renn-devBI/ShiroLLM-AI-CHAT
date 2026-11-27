# -*- coding: utf-8 -*-
"""
Shiro Server Runtime State Container
Holds singleton references to LLM instance, Vision Chat Handler, Memory Manager,
and Web Reader to decouple routes and inference modules from web.py.
"""

import threading
from typing import Optional, Any
from shiro.config import MEMORY_FILE, WORLD_FILE

class ServerRuntimeState:
    def __init__(self):
        self.llm: Optional[Any] = None
        self.vision_chat_handler: Optional[Any] = None
        self.memory: Optional[Any] = None
        self.web_reader: Optional[Any] = None
        self.serial_questions: int = 0
        self.last_turn_had_image: bool = False
        # Global lock untuk menserialisasi seluruh operasi llama.cpp (inferensi, vision, switch model)
        # Mencegah race condition C++ (GGML_ASSERT / SIGABRT) akibat akses paralel ke llama_context
        self.llm_lock = threading.Lock()
        self._running_sessions_lock = threading.Lock()
        self._running_sessions: dict = {}

    def mark_session_running(self, session_id: Optional[str]):
        """Menandai sesi tertentu sedang menjalankan respons AI di latar belakang."""
        sid = (session_id or "").strip()
        if not sid:
            return
        with self._running_sessions_lock:
            self._running_sessions[sid] = int(self._running_sessions.get(sid, 0)) + 1

    def mark_session_done(self, session_id: Optional[str]):
        """Mengurangi hitungan eksekusi aktif untuk sesi saat respons selesai/berhenti."""
        sid = (session_id or "").strip()
        if not sid:
            return
        with self._running_sessions_lock:
            cur = int(self._running_sessions.get(sid, 0)) - 1
            if cur <= 0:
                self._running_sessions.pop(sid, None)
            else:
                self._running_sessions[sid] = cur

    def get_running_session_ids(self) -> list:
        """Mengembalikan daftar ID sesi yang saat ini masih berjalan di backend."""
        with self._running_sessions_lock:
            return [sid for sid, cnt in self._running_sessions.items() if cnt > 0]

    def is_llm_busy(self) -> bool:
        """Memeriksa apakah instance LLM sedang digunakan untuk inferensi atau perpindahan model"""
        return self.llm_lock.locked()

    def init_memory(self):
        """Inisialisasi AdvancedMemoryManager jika belum dimuat"""
        if self.memory is None:
            from shiro.memory.manager import AdvancedMemoryManager
            self.memory = AdvancedMemoryManager(MEMORY_FILE, WORLD_FILE)
        return self.memory

    def init_web_reader(self):
        """Inisialisasi WebReader jika belum dimuat"""
        if self.web_reader is None:
            try:
                import web_reader
                self.web_reader = web_reader
            except Exception as e:
                print(f"[ServerState] Warning loading web_reader: {e}")
        return self.web_reader

    def set_llm(self, llm_instance: Any, vision_handler: Optional[Any] = None):
        """Memperbarui LLM instance aktif dan vision handler"""
        self.llm = llm_instance
        self.vision_chat_handler = vision_handler
        self.last_turn_had_image = False

# Singleton instance
state = ServerRuntimeState()
