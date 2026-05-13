# Inference Pilots Landing Log

## 2026-05-07 - Initial package landing

Created the inference pilots package as a route home for local model pilots,
benchmarking, model profiles, and trial-backed promotion paths.

Validation route: `python scripts/validate_nested_agents.py` and
`python scripts/validate_stack.py`.

## 2026-05-13 - Part-local docs topology

Moved LangGraph, llama.cpp, local-trial, benchmark, and promotion-loop docs into
their owning parts. Old pilot files remain under `legacy/trials/raw/`.

Validation route: `python scripts/validate_stack.py`.

## 2026-05-13 - Trial legacy specialization

Moved preserved W0-W6 trial docs and runner scripts under
`legacy/trials/`.

Validation route: `python scripts/validate_stack.py`.
