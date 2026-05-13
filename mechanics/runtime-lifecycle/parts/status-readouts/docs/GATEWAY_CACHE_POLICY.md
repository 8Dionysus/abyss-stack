# GATEWAY CACHE POLICY

## Purpose

This document defines the bounded cache-lane contract for `abyss-stack`.

It covers future request deduplication and cache-status readout for the `langchain-api` gateway path.
This surface documents the contract only. It does not activate live cache behavior.

## Core rule

`abyss-stack` may describe gateway cache metabolism.

It does not own truth.
It does not grant routing authority.
It does not lock the stack to one vendor.

## Vocabulary

- `request deduplication` means later callers for the same normalized request may wait on one active upstream call instead of opening a second one
- `inflight replay` means one active request may satisfy multiple waiting callers without widening route meaning
- `completed TTL` means a completed response may remain reusable for a short bounded window
- `cache key normalization` means the key is derived from request shape, selected headers, and runtime identity rather than raw vendor-specific payload trivia
- `no-cache bypass` means an explicit caller signal such as `Cache-Control: no-cache` asks the runtime not to serve or store a cached result
- `eviction` means bounded removal when TTL or retention pressure says an entry should leave the active lane
- `hit rate` means a runtime-only readout about reuse; it is not a quality score or truth claim

## First artifact slice

The first slice is a status artifact, not a wire API.
It is represented by `runtime_gateway_cache_status_v1`.

Recommended local path when this surface exists:

- `${AOA_STACK_ROOT}/Logs/runtime-gateway/cache-status/latest/`

The artifact may describe:

- `cache_key_strategy`
- `normalization_rules`
- `inflight_state`
- `ttl_window`
- `bypass_reason`
- `hit_state`
- `generated_at`

This slice is for readout only.
It does not alter `/run` or `/run/federated`.
It does not add new HTTP endpoints in this contract surface.

## Intended future seam

The future implementation seam sits below the existing `langchain-api` request path.
It may eventually support bounded deduplication and reuse for `POST /run` and `POST /run/federated`.

This document does not claim that the cache lane is live on every profile.
It only defines the public-safe contract that later runtime work must satisfy.

## Non-goals

This surface must not:

- decide which route is correct
- become a hidden model selector
- carry vendor-specific lock-in as policy
- replace proof or eval meaning
- pretend a cache hit is evidence of correctness

## One-line rule

`abyss-stack` may describe a future gateway cache lane as a bounded runtime contract, but it must not silently turn gateway metabolism into truth, routing, or proof authority.
