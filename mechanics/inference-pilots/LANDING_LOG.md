# Inference Pilots Landing Log

## 2026-05-07 - Initial package landing

Created the inference pilots package as a route home for local model pilots,
benchmarking, model profiles, and trial-backed promotion paths.

Validation followed the package and root validation routes.

## 2026-05-13 - Part-local docs topology

Moved LangGraph, llama.cpp, local-trial, benchmark, and promotion-loop docs into
their owning parts. Old pilot files remain under `legacy/trials/raw/`.

Validation followed the root source route.

## 2026-05-13 - Trial legacy specialization

Moved preserved W0-W6 trial docs and runner scripts under
`legacy/trials/`.

Validation followed the root source route.

## 2026-05-13 - Trial compatibility bridge cleanup

Renamed the active role-level compatibility adapter to
`parts/local-trials/trial_compatibility_bridge.py` so old stage labels remain
wire IDs rather than active module topology. Moved the LangGraph pilot
dependency manifest into `parts/langgraph-pilot/requirements.txt`.

Validation followed the root source route.
