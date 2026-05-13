$Backend = Join-Path $PSScriptRoot "../mechanics/machine-fit/parts/windows-bridge/aoa_bootstrap_wsl.ps1"
& $Backend @args
exit $LASTEXITCODE
