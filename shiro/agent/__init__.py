# -*- coding: utf-8 -*-
"""
Shiro AI Agent Package
Autonomous tools, network layer with Cloudflare 1.1.1.1 & Mozilla headers,
and 2-step agent reasoning loop.
"""

from shiro.agent.network import (
    MOZILLA_HEADERS,
    resolve_dns_cloudflare,
    fetch_html_content,
    get_agent_session
)
from shiro.agent.tools import (
    detect_agent_intent,
    check_weather,
    search_google_web,
    open_and_read_webpage,
    calculate_math,
    get_current_time_info,
    take_web_screenshot,
    execute_powershell_command,
    find_available_browser
)
from shiro.agent.engine import (
    ShiroAgentExecutor,
    agent_executor
)

__all__ = [
    "MOZILLA_HEADERS",
    "resolve_dns_cloudflare",
    "fetch_html_content",
    "get_agent_session",
    "detect_agent_intent",
    "check_weather",
    "search_google_web",
    "open_and_read_webpage",
    "calculate_math",
    "get_current_time_info",
    "take_web_screenshot",
    "execute_powershell_command",
    "find_available_browser",
    "ShiroAgentExecutor",
    "agent_executor"
]
