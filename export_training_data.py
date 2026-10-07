# -*- coding: utf-8 -*-
"""
Export Training Data CLI (Backward-compatible Shim)
Delegates to modular shiro.training.exporter
"""

import sys
from shiro.training.exporter import (
    SYSTEM_PROMPT,
    export_data
)

if __name__ == "__main__":
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    export_data()
