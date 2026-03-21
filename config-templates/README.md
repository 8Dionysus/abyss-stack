# config templates

This directory stores public-safe runtime config templates.

These files are not the live runtime configs themselves.
They are source-managed templates that can be copied into the deployed runtime tree with:

```bash
scripts/aoa-bootstrap-configs
```

## Intent

- keep examples public-safe
- reduce first-run friction
- avoid mixing real secrets into git
- make the deployed runtime shape more obvious

## Current template families

- `Configs/monitoring/`
- `Configs/tts/`
- `Configs/ollama/`
- `Services/litellm/`
