# -*- coding: utf-8 -*-
"""
Typo and Slang Intelligence Helper for Shiro LLMA (Backward-compatible Shim)
Delegates to modular shiro.nlp.typo
"""

from shiro.nlp.typo import (
    INDONESIAN_CHAT_TYPOS,
    normalize_typos,
    get_typo_understanding_prompt
)

__all__ = [
    "INDONESIAN_CHAT_TYPOS",
    "normalize_typos",
    "get_typo_understanding_prompt"
]
