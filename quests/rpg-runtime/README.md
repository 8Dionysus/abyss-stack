# rpg-runtime Quest Lane

RPG runtime service and projection obligations.

Use this lane for runtime-owned RPG contracts, filesystem-first collections,
and frontend projection follow-through. It does not own upstream AoA RPG
meaning, quest canon, role canon, or reward logic.

## Current state

- `done/` holds landed source-side service contracts.
- `done/` also holds the closed runtime materialization packet. Future live
  consumption still must stay a read model unless a new reviewed route adds
  endpoints without source quest mutation.
