"""Adapter per sorgenti esterne di vincoli temporali (Fase 8)."""

from src.integrations.outlook import (
    GRAPH_BASE_URL,
    GRAPH_SCOPES,
    LOGIN_AUTHORITY,
    parse_graph_events,
)
from src.integrations.outlook_auth import OutlookClient, OutlookError, disconnect

__all__ = [
    "GRAPH_BASE_URL",
    "GRAPH_SCOPES",
    "LOGIN_AUTHORITY",
    "OutlookClient",
    "OutlookError",
    "disconnect",
    "parse_graph_events",
]
