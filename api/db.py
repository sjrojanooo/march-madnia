from __future__ import annotations

import logging

from supabase import Client, create_client

from api.config import Settings

logger = logging.getLogger(__name__)

_client: Client | None = None


def get_supabase_client() -> Client | None:
    """Return a Supabase client using the service role key, or None if not configured."""
    global _client
    if _client is not None:
        return _client

    settings = Settings()
    if not settings.supabase_url or not settings.supabase_service_role_key:
        logger.warning("Supabase URL or service role key not set — DB disabled.")
        return None

    _client = create_client(settings.supabase_url, settings.supabase_service_role_key)
    logger.info("Supabase client initialized (service role).")
    return _client
