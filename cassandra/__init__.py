"""Cassandra: continuous integration for the spreadsheets that run your company.

Local configuration is loaded here, at package import, so every entry point
picks it up: the Cloud Run service, the demo builder, and the test suite alike.
Without this a developer following the README would create a .env, see nothing
read it, and fall back silently to an in memory store and an unconfigured model
endpoint. Real environment variables always win, which is what Cloud Run sets.
"""

from __future__ import annotations

try:
    from dotenv import load_dotenv

    load_dotenv(override=False)
except Exception:
    # python-dotenv is a local convenience. In a deployed container the
    # environment is already populated and there is no .env to read.
    pass
