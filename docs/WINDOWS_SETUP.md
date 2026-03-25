# WINDOWS SETUP

This is the least-friction Windows route for the current `abyss-stack`.

## Shape

- keep the source checkout wherever Windows editing is convenient
- run the runtime inside WSL2
- keep the canonical runtime root inside Linux as `/srv/abyss-stack`

## Before you start

You want:

- WSL2 installed
- a Linux distro available in WSL
- systemd enabled inside that distro
- `podman`, `rsync`, and `curl` installed inside the distro

## Recommended order

### 1. Check the Windows side

From PowerShell at the repo root:

```powershell
pwsh -File scripts/aoa.ps1 host-doctor
```

This checks the Windows-host and WSL bridge posture before you burn time on stack startup.

### 2. Run the Linux doctor through the bridge

```powershell
pwsh -File scripts/aoa.ps1 doctor --preset agent-full
```

That uses the existing Linux doctor inside WSL.

### 3. Bootstrap the runtime tree

```powershell
pwsh -File scripts/aoa.ps1 first-run --strict
```

### 4. Bring up a profile or preset

```powershell
pwsh -File scripts/aoa.ps1 up --preset agent-full
```

### 5. Inspect status

```powershell
pwsh -File scripts/aoa.ps1 status --preset agent-full
```

### 6. Shut it down

```powershell
pwsh -File scripts/aoa.ps1 down --preset agent-full
```

## Choosing a distro explicitly

If you work with multiple WSL distros:

```powershell
pwsh -File scripts/aoa.ps1 -Distro Fedora doctor --preset agent-full
```

## Applying a placeholder overlay

If you want to exercise the bounded overlay path with the shipped placeholder example:

```powershell
pwsh -File scripts/aoa.ps1 up -Overlay compose/tuning/ollama.cpu.yml --preset agent-full
```

Treat `compose/tuning/ollama.cpu.yml` as a placeholder overlay that proves the path works. It is not a claim that this repository ships a fully validated CPU tuning profile.

## Important habit

The source checkout may live on Windows.

The hot runtime should not.

Keep these inside the Linux filesystem whenever possible:

- runtime root
- models
- logs
- container data
- caches that are hit constantly
