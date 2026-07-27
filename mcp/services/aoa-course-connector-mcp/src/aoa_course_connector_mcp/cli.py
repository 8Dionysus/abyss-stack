from __future__ import annotations

import json

from .core import AoACourseConnectorMCPState


def main() -> None:
    print(
        json.dumps(
            AoACourseConnectorMCPState.discover().source_route(),
            ensure_ascii=False,
            indent=2,
        )
    )
