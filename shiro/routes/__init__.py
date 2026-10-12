# -*- coding: utf-8 -*-
"""
Shiro Web Routes & Blueprints Package
"""

from shiro.routes.views import views_bp
from shiro.routes.chat import chat_bp
from shiro.routes.openai import openai_bp
from shiro.routes.documents import documents_bp
from shiro.routes.sessions import sessions_bp
from shiro.routes.admin import admin_bp

__all__ = [
    "views_bp",
    "chat_bp",
    "openai_bp",
    "documents_bp",
    "sessions_bp",
    "admin_bp"
]
