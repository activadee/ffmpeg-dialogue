#!/usr/bin/env python3
"""
Entry point for the modular Video Generator Server
"""
from app.main import main

if __name__ == '__main__':
    import ssl
    ssl._create_default_https_context = ssl._create_unverified_context

    main()