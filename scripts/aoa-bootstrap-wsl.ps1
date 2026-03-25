[CmdletBinding(PositionalBinding = $false)]
param(
    [string]$Distro = $env:AOA_WSL_DISTRO,
    [string]$RuntimeRoot = "/srv/abyss-stack"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Invoke-WslCapture {
    param(
        [string]$DistroName,
        [Parameter(Mandatory = $true)][string[]]$Arguments
    )

    $wslArgs = @()
    if ($DistroName) {
        $wslArgs += @("-d", $DistroName)
    }
    $wslArgs += $Arguments

    $output = & wsl.exe @wslArgs 2>&1
    $code = $LASTEXITCODE

    return [pscustomobject]@{
        Output = @($output)
        ExitCode = $code
    }
}

if (-not (Get-Command wsl.exe -ErrorAction SilentlyContinue)) {
    throw "wsl.exe is not available. Install WSL first."
}

$osRelease = Invoke-WslCapture -DistroName $Distro -Arguments @("--exec", "sh", "-lc", '. /etc/os-release >/dev/null 2>&1 && printf "%s" "$ID"')
$osReleaseFirstLine = $osRelease.Output | Select-Object -First 1
$distroId = if ($osRelease.ExitCode -eq 0 -and $null -ne $osReleaseFirstLine) {
    $osReleaseFirstLine.ToString().Trim()
}
else {
    ""
}

Write-Host "abyss-stack WSL bootstrap"
Write-Host ""
Write-Host "Target distro: $(if ($Distro) { $Distro } else { '(default)' })"
Write-Host "Runtime root: $RuntimeRoot"
Write-Host ""
Write-Host "Suggested sequence:"
Write-Host ""
Write-Host "1. Confirm your distro is running on WSL2:"
Write-Host "   wsl.exe --list --verbose"
Write-Host ""
Write-Host "2. Enable systemd inside the distro by writing /etc/wsl.conf:"
Write-Host "   [boot]"
Write-Host "   systemd=true"
Write-Host ""
Write-Host "   Example inside the distro:"
Write-Host "   sudo tee /etc/wsl.conf >/dev/null <<'EOF'"
Write-Host "   [boot]"
Write-Host "   systemd=true"
Write-Host "   EOF"
Write-Host ""
Write-Host "3. Restart WSL from PowerShell:"
Write-Host "   wsl.exe --shutdown"
Write-Host ""
Write-Host "4. Re-enter the distro and install runtime prerequisites."

switch ($distroId) {
    "fedora" {
        Write-Host "   Fedora example:"
        Write-Host "   sudo dnf install -y podman rsync curl"
    }
    "ubuntu" {
        Write-Host "   Ubuntu detected."
        Write-Host "   Install podman, rsync and curl using the distro package manager you trust for your environment."
        Write-Host "   Fedora remains the least-friction reference posture for abyss-stack."
    }
    "debian" {
        Write-Host "   Debian detected."
        Write-Host "   Install podman, rsync and curl using the distro package manager you trust for your environment."
        Write-Host "   Fedora remains the least-friction reference posture for abyss-stack."
    }
    default {
        Write-Host "   Install podman, rsync and curl inside the distro."
        Write-Host "   Fedora remains the least-friction reference posture for abyss-stack."
    }
}

Write-Host ""
Write-Host "5. Keep hot runtime data inside the Linux filesystem:"
Write-Host "   - runtime root"
Write-Host "   - models"
Write-Host "   - logs"
Write-Host "   - container data"
Write-Host ""
Write-Host "6. Then run:"
Write-Host "   pwsh -File scripts/aoa.ps1 host-doctor"
Write-Host "   pwsh -File scripts/aoa.ps1 doctor --preset agent-full"
Write-Host "   pwsh -File scripts/aoa.ps1 first-run --strict"
