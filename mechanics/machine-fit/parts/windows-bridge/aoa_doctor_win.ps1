[CmdletBinding(PositionalBinding = $false)]
param(
    [string]$Distro = $env:AOA_WSL_DISTRO,
    [string]$RuntimeRoot = "/srv/AbyssOS/abyss-stack",
    [switch]$Strict
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$script:ErrorCount = 0
$script:WarningCount = 0

function Write-DoctorOk {
    param([string]$Message)
    Write-Host "ok $Message"
}

function Write-DoctorWarn {
    param([string]$Message)
    Write-Host "warn $Message"
    $script:WarningCount += 1
}

function Write-DoctorFail {
    param([string]$Message)
    Write-Host "fail $Message"
    $script:ErrorCount += 1
}

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

function Test-WslCommand {
    param(
        [string]$DistroName,
        [Parameter(Mandatory = $true)][string]$CommandName
    )

    $result = Invoke-WslCapture -DistroName $DistroName -Arguments @("--exec", "sh", "-lc", "command -v $CommandName >/dev/null 2>&1")

    if ($result.ExitCode -eq 0) {
        Write-DoctorOk "cmd $CommandName inside WSL"
    }
    else {
        Write-DoctorFail "cmd $CommandName not found inside WSL"
    }
}

if (-not [System.Runtime.InteropServices.RuntimeInformation]::IsOSPlatform([System.Runtime.InteropServices.OSPlatform]::Windows)) {
    Write-DoctorFail "platform is not Windows"
}
else {
    Write-DoctorOk "platform Windows"
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Write-Host "repo root: $repoRoot"
Write-Host "runtime root: $RuntimeRoot"

$wsl = Get-Command wsl.exe -ErrorAction SilentlyContinue
if (-not $wsl) {
    Write-DoctorFail "wsl.exe not found"
}
else {
    Write-DoctorOk "wsl.exe"
}

if ($repoRoot -match '^[A-Za-z]:\\') {
    Write-DoctorWarn "source checkout is on the Windows filesystem; keep hot runtime data in WSL ext4 for best Linux-side performance"
}
elseif ($repoRoot.StartsWith("\\wsl$\")) {
    Write-DoctorOk "source checkout is already in a WSL-backed filesystem view"
}
else {
    Write-DoctorOk "source checkout path detected"
}

if ($wsl) {
    $status = Invoke-WslCapture -DistroName $null -Arguments @("--status")
    if ($status.ExitCode -eq 0) {
        Write-DoctorOk "wsl status available"
    }
    else {
        Write-DoctorWarn "wsl status unavailable"
    }

    $distroList = Invoke-WslCapture -DistroName $null -Arguments @("--list", "--quiet")
    $installedDistros = @(
        $distroList.Output |
        ForEach-Object { $_.ToString().Trim() } |
        Where-Object { $_ }
    )

    if ($distroList.ExitCode -ne 0 -or $installedDistros.Count -eq 0) {
        Write-DoctorFail "no WSL distro found"
    }
    else {
        if ($Distro) {
            Write-DoctorOk "using distro $Distro"
        }
        else {
            Write-DoctorOk "using default WSL distro"
        }

        $pid1 = Invoke-WslCapture -DistroName $Distro -Arguments @("--exec", "sh", "-lc", "ps -p 1 -o comm= 2>/dev/null")
        if ($pid1.ExitCode -eq 0 -and (($pid1.Output | Select-Object -First 1).Trim() -eq "systemd")) {
            Write-DoctorOk "systemd is PID 1 inside WSL"
        }
        else {
            Write-DoctorWarn "systemd is not PID 1 inside WSL; enable it in /etc/wsl.conf and restart WSL"
        }

        Test-WslCommand -DistroName $Distro -CommandName "podman"
        Test-WslCommand -DistroName $Distro -CommandName "rsync"
        Test-WslCommand -DistroName $Distro -CommandName "curl"

        $runtimeCheck = Invoke-WslCapture -DistroName $Distro -Arguments @("--exec", "sh", "-lc", "test -d '$RuntimeRoot'")
        if ($runtimeCheck.ExitCode -eq 0) {
            Write-DoctorOk "runtime root $RuntimeRoot"
        }
        else {
            Write-DoctorWarn "runtime root $RuntimeRoot not created yet"
        }
    }
}

if ($script:ErrorCount -gt 0) {
    throw "doctor found $($script:ErrorCount) hard errors"
}

if ($Strict -and $script:WarningCount -gt 0) {
    throw "doctor found $($script:WarningCount) warnings in strict mode"
}

Write-Host "doctor check passed"
if ($script:WarningCount -gt 0) {
    Write-Host "warnings: $($script:WarningCount)"
}
