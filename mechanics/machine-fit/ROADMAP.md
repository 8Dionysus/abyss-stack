# Machine Fit Roadmap

## Current route

- keep reference platform, host facts, machine bridge, fit records, adaptation,
  Windows bridge, and inference tuning separated by part
- keep captures public-safe in source examples and private in runtime records
- keep stack-side bridge reads bounded and read-only

## Next candidates

- add a package-level public fixture index if machine-fit examples multiply
- extend platform adaptation only when a profile or preset uses the new signal
- add focused tests around Windows bridge wrappers if PowerShell behavior grows

## Stop-lines

- do not mutate `/srv/abyss-machine`, Podman storage, accelerator settings, or
  live host state from source docs
- do not treat fit recommendations as service-health proof
- do not commit private host facts or model binaries
