# -*- coding: utf-8 -*-
"""
Shiro Server Runtime State Container
Holds singleton references to LLM instance, Vision Chat Handler, Memory Manager,
and Web Reader to decouple routes and inference modules from web.py.
"""

from typing import Optional, Any
from shiro.config import MEMORY_FILE, WORLD_FILE

class ServerRuntimeState:
    def __init__(self):
        self.llm: Optional[Any] = None
        self.vision_chat_handler: Optional[Any] = None
        self.memory: Optional[Any] = None
        self.web_reader: Optional[Any] = None
        self.serial_questions: int = 0

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

# Singleton instance
state = ServerRuntimeState()
