"""Small diagnostic CLI for the XDA MCP wrapper."""

from __future__ import annotations

import argparse
import json

from .core import AoAXDAConnectorMCPState


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("source-route", "status"))
    args = parser.parse_args()
    state = AoAXDAConnectorMCPState.discover()
    payload = state.source_route() if args.action == "source-route" else state.status()
    print(json.dumps(payload, ensure_ascii=False, indent=2))
