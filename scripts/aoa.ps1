$Backend = Join-Path $PSScriptRoot "../mechanics/machine-fit/parts/windows-bridge/aoa_windows_bridge.ps1"
& $Backend @args
exit $LASTEXITCODE
