# system systemd units

This directory stores privileged system-unit skeletons that support the local
working stack.

## Managed units

`managed-units.txt` is the allowlist for:

- `abyss-dictation-hotkey.service`
- `abyss-ai-workload-refresh.service` / `.timer`
- `abyss-observability-collect.service` / `.timer`
- `abyss-power-profile-auto.service` / `.timer`

`abyss-dictation-hotkey.service` reads optional local overrides from
`/etc/abyss-machine/dictation-hotkey.env`, for example
`ABYSS_DICTATION_USER` and `ABYSS_DICTATION_UID`.

Install them only through the explicit privileged route in
[AGENTS](AGENTS.md#privileged-install-route).

That mode backs up existing regular files under `/etc/systemd/system`, installs
root-owned copies of the allowlisted units from the deployed Configs mirror, and runs
`systemctl daemon-reload`. It does not start, stop, restart, enable, disable, or
mask services.
