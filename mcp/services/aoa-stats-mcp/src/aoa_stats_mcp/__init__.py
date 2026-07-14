"""Read-only MCP access plane for the federated OS Abyss stats system."""

from .core import AoAStatsMCPState, StatsAccessError

__all__ = ["AoAStatsMCPState", "StatsAccessError"]
