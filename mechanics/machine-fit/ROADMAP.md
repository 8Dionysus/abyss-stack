# Machine Fit Roadmap

## Current route

- keep reference platform, host facts, machine bridge, fit records, adaptation,
  Windows bridge, and inference tuning separated by part
- keep captures public-safe in source examples and private in runtime records
- keep stack-side bridge reads bounded and read-only

## Next candidates

- rerun the profile machine-fit packet before promoting any new host-profile
  posture
- rerun the machine-fit follow-through packet when Windows bridge,
  reference-platform, platform-adaptation, or fit-record posture drifts
- add a package-level public fixture index only if machine-fit examples
  multiply beyond the current part-local route
- add focused tests around Windows bridge wrappers if PowerShell behavior grows

## Stop-lines

- do not mutate `/srv/abyss-machine`, Podman storage, accelerator settings, or
  live host state from source docs
- do not treat fit recommendations as service-health proof
- do not commit private host facts or model binaries
