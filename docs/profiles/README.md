# profiles

`docs/profiles/` owns profile, preset, and recipe selection for the runtime.

The current default source-owned runtime base is `substrate`: storage plus
orchestration. Add `local-worker`, `intel-worker`, `fallback-gateway`,
federation, tools, curation, or observability only when that layer is
intentionally part of the run.

| Surface | Role |
|---|---|
| [PROFILES](PROFILES.md) | named profile contracts |
| [PRESETS](PRESETS.md) | preset-to-profile composition |
| [PROFILE_RECIPES](PROFILE_RECIPES.md) | common operating combinations |

Use mechanic docs when profile changes require host fit, model tuning,
federation seams, or lifecycle implementation details.
