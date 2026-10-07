# -*- coding: utf-8 -*-
"""
Web Reader & Online Real-Time Browsing Module (Backward-compatible Shim)
Delegates to modular shiro.web.reader
"""

from shiro.web.reader import (
    BROWSER_HEADERS,
    extract_urls,
    detect_web_intent,
    clean_html_content,
    fetch_fandom_mediawiki,
    fetch_url,
    search_wikipedia_online,
    append_to_training_dataset,
    integrate_web_knowledge
)

__all__ = [
    "BROWSER_HEADERS",
    "extract_urls",
    "detect_web_intent",
    "clean_html_content",
    "fetch_fandom_mediawiki",
    "fetch_url",
    "search_wikipedia_online",
    "append_to_training_dataset",
    "integrate_web_knowledge"
]
