# Agon Runtime Roadmap

## Current route

- keep active dry-run runtime-kernel surfaces under `parts/runtime-kernels/`
- keep old raw Agon docs contained under `legacy/raw/`
- keep validators, tests, route cards, and generated registries pointed at the
  active part path

## Next candidates

- split dry-run event-log validation from generated registry construction
- add a higher-level operator wrapper only if this becomes a reviewed runtime
  command
