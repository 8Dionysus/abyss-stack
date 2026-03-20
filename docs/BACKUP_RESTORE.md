# BACKUP AND RESTORE

## Backup layers

### S0

Configuration and documentation state:
- compose modules
- profiles
- scripts
- systemd user files
- public-safe docs

### S1

Service state:
- database data
- vector store data
- runtime service state

### S2

Heavy or slow-moving artifacts:
- models
- large knowledge corpora
- media and large generated assets

## Rule of thumb

- before changing runtime topology, protect S0
- before changing stateful services, protect S1
- before moving model or heavy-data paths, think about S2

## Restore stance

Restore should be explicit and profile-aware.
Do not restore blindly over a live stack without deciding whether the stack must be stopped first.

## Current status

This document is a contract skeleton for the new stack.
Exact restore procedures should be hardened as the wrapper and operational model mature.
