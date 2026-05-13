# Federation Seams Landing Log

## 2026-05-07 - Initial package landing

Created the federation seams package as a route home for owner-surface mirrors,
advisory sync, and optional federation runtime posture.

Validation route: `python scripts/validate_nested_agents.py` and
`python scripts/validate_stack.py`.

## 2026-05-12 - RPG runtime read-model landing

Moved RPG runtime read-model schemas, examples, generated transport files, and
script tests into the federation-seams package. Root questbook schemas,
examples, and quests stayed in the root technical districts because they still
mix repository obligation tracking with federation-facing runtime projection.

Validation route: source-only RPG projection check, package-local pytest,
`python scripts/validate_stack.py`, and `python scripts/validate_nested_agents.py`.
