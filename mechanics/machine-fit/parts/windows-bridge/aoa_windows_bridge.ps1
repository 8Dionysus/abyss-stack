[CmdletBinding(PositionalBinding = $false)]
param(
    [string]$Distro = $env:AOA_WSL_DISTRO,
    [string]$RuntimeRoot = $env:AOA_STACK_ROOT,
    [string]$VaultRoot = $env:AOA_VAULT_ROOT,
    [string[]]$Overlay = @(),
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$RemainingArgs = @()
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Convert-ToBashSingleQuoted {
    param([Parameter(Mandatory = $true)][string]$Value)

    return "'" + ($Value -replace "'", "'`"`'`"`'") + "'"
}

function Convert-ToWslPath {
    param(
        [Parameter(Mandatory = $true)][string]$WindowsPath,
        [string]$DistroName
    )

    $wslArgs = @()
    if ($DistroName) {
        $wslArgs += @("-d", $DistroName)
    }
    $wslArgs += @("--exec", "wslpath", "-a", $WindowsPath)

    $output = & wsl.exe @wslArgs

    if ($LASTEXITCODE -ne 0) {
        throw "Unable to map Windows path into WSL: $WindowsPath"
    }

    return ($output | Select-Object -First 1).Trim()
}

function Resolve-OverlaySpecs {
    param(
        [string[]]$Specs,
        [string]$DistroName
    )

    $resolved = @()

    foreach ($spec in $Specs) {
        if ([string]::IsNullOrWhiteSpace($spec)) {
            continue
        }

        if ($spec -match '^[A-Za-z]:\\') {
            $resolved += Convert-ToWslPath -WindowsPath $spec -DistroName $DistroName
            continue
        }

        $resolved += $spec
    }

    return $resolved
}

function Get-LinuxScriptPath {
    param([Parameter(Mandatory = $true)][string]$CommandName)

    switch ($CommandName) {
        "doctor" { return "scripts/aoa-doctor" }
        "first-run" { return "scripts/aoa-first-run" }
        "install-layout" { return "scripts/aoa-install-layout" }
        "sync-configs" { return "scripts/aoa-sync-configs" }
        "bootstrap-configs" { return "scripts/aoa-bootstrap-configs" }
        "check-layout" { return "scripts/aoa-check-layout" }
        "install-systemd" { return "scripts/aoa-install-systemd" }
        "preset-profiles" { return "scripts/aoa-preset-profiles" }
        "profile-modules" { return "scripts/aoa-profile-modules" }
        "profile-endpoints" { return "scripts/aoa-profile-endpoints" }
        "render-services" { return "scripts/aoa-render-services" }
        "render-config" { return "scripts/aoa-render-config" }
        "up" { return "scripts/aoa-up" }
        "down" { return "scripts/aoa-down" }
        "status" { return "scripts/aoa-status" }
        "logs" { return "scripts/aoa-logs" }
        "smoke" { return "scripts/aoa-smoke" }
        "wait" { return "scripts/aoa-wait" }
        default {
            if ($CommandName.StartsWith("aoa-")) {
                return "scripts/$CommandName"
            }

            return "scripts/aoa-$CommandName"
        }
    }
}

function Show-Usage {
    @"
abyss-stack Windows bridge

Usage:
  pwsh -File scripts/aoa.ps1 host-doctor
  pwsh -File scripts/aoa.ps1 bootstrap-wsl
  pwsh -File scripts/aoa.ps1 doctor --preset agent-full
  pwsh -File scripts/aoa.ps1 first-run --strict
  pwsh -File scripts/aoa.ps1 up --preset agent-full
  pwsh -File scripts/aoa.ps1 up -Overlay compose/tuning/llamacpp.cpu.yml --preset agent-full

Optional PowerShell parameters:
  -Distro <name>       Use a specific WSL distro instead of the default one.
  -RuntimeRoot <path>  Linux runtime root. Default: /srv/AbyssOS/abyss-stack
  -VaultRoot <path>    Linux vault root. Default: /abyss when not overridden.
  -Overlay <path[]>    Extra compose files. Relative paths are resolved inside AOA_CONFIGS_ROOT.

Special commands:
  host-doctor          Runs the Windows/WSL readiness check.
  bootstrap-wsl        Prints guided WSL bootstrap steps.
"@ | Write-Host
}

if (-not (Get-Command wsl.exe -ErrorAction SilentlyContinue)) {
    throw "wsl.exe is not available. Install WSL first."
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

if (-not $RuntimeRoot) {
    $RuntimeRoot = "/srv/AbyssOS/abyss-stack"
}

$configRoot = "$RuntimeRoot/Configs"

if ($RemainingArgs.Count -eq 0) {
    Show-Usage
    exit 1
}

$command = $RemainingArgs[0]
$forwardArgs = if ($RemainingArgs.Count -gt 1) { $RemainingArgs[1..($RemainingArgs.Count - 1)] } else { @() }

switch ($command) {
    "help" {
        Show-Usage
        exit 0
    }
    "host-doctor" {
        & (Join-Path $PSScriptRoot "aoa-doctor-win.ps1") -Distro $Distro -RuntimeRoot $RuntimeRoot
        if ($null -ne $LASTEXITCODE) { exit $LASTEXITCODE } else { exit 0 }
    }
    "bootstrap-wsl" {
        & (Join-Path $PSScriptRoot "aoa-bootstrap-wsl.ps1") -Distro $Distro -RuntimeRoot $RuntimeRoot
        if ($null -ne $LASTEXITCODE) { exit $LASTEXITCODE } else { exit 0 }
    }
}

$linuxScript = Get-LinuxScriptPath -CommandName $command
$linuxScriptWindowsPath = Join-Path $repoRoot $linuxScript.Replace("/", [IO.Path]::DirectorySeparatorChar.ToString())

if (-not (Test-Path $linuxScriptWindowsPath)) {
    throw "Linux script not found in repository: $linuxScript"
}

$repoRootLinux = Convert-ToWslPath -WindowsPath $repoRoot -DistroName $Distro
$overlaySpecs = Resolve-OverlaySpecs -Specs $Overlay -DistroName $Distro
$overlayCsv = if ($overlaySpecs.Count -gt 0) { ($overlaySpecs -join ",") } else { "" }

$bootstrap = @(
    "export AOA_STACK_ROOT=$(Convert-ToBashSingleQuoted -Value $RuntimeRoot)",
    "export AOA_CONFIGS_ROOT=$(Convert-ToBashSingleQuoted -Value $configRoot)"
)

if ($VaultRoot) {
    $bootstrap += "export AOA_VAULT_ROOT=$(Convert-ToBashSingleQuoted -Value $VaultRoot)"
}

if ($overlayCsv) {
    $bootstrap += "export AOA_EXTRA_COMPOSE_FILES=$(Convert-ToBashSingleQuoted -Value $overlayCsv)"
}

$bootstrap += 'cd "$1"'
$bootstrap += 'shift'
$bootstrap += '"$@"'

$bashCommand = ($bootstrap -join "; ")

$wslArguments = @()
if ($Distro) {
    $wslArguments += @("-d", $Distro)
}
$wslArguments += @("--exec", "bash", "-lc", $bashCommand, "--", $repoRootLinux, $linuxScript)
$wslArguments += $forwardArgs

& wsl.exe @wslArguments
exit $LASTEXITCODE
