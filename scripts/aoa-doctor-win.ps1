$Backend = Join-Path $PSScriptRoot "../mechanics/machine-fit/parts/windows-bridge/aoa_doctor_win.ps1"
& $Backend @args
exit $LASTEXITCODE
