# Machine Fit Direction

This package keeps host capability evidence readable by the stack without
turning `abyss-stack` into the machine control plane.

Current posture:

- keep reference-platform docs public-safe
- keep host facts, machine bridge, machine fit, platform adaptation, Windows
  bridge, and inference tuning as separate parts
- keep stack-side bridge reads bounded and read-only
- keep root wrappers stable while part-local backends own implementation

Near direction:

- keep private host captures out of git
- keep fit records advisory unless a live check proves the selected route
- keep inference tuning connected to inference-pilots without making model
  quality claims
- route machine provisioning and storage control to `abyss-machine`
