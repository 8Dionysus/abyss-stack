# Windows Bridge

Owns Windows and WSL bridge docs for `abyss-stack`.

This part keeps Windows source-checkout ergonomics separate from the canonical
Linux runtime body:

- `docs/WINDOWS_BRIDGE.md`
- `docs/WINDOWS_SETUP.md`
- `docs/WINDOWS_PERFORMANCE.md`
- `aoa_windows_bridge.ps1`
- `aoa_doctor_win.ps1`
- `aoa_bootstrap_wsl.ps1`

It does not define a second compose authority or a second runtime root.
