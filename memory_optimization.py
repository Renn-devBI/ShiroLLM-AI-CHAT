# -*- coding: utf-8 -*-
"""
Memory Optimization & Compression Module (Backward-compatible Shim)
Delegates to modular shiro.memory.optimization
"""

from shiro.memory.optimization import (
    compress_old_messages,
    get_smart_memory_context,
    diagnose_memory_status,
    calculate_token_budget,
    estimate_tokens,
    calculate_messages_tokens,
    trim_text_to_token_budget
)

__all__ = [
    "compress_old_messages",
    "get_smart_memory_context",
    "diagnose_memory_status",
    "calculate_token_budget",
    "estimate_tokens",
    "calculate_messages_tokens",
    "trim_text_to_token_budget"
]
