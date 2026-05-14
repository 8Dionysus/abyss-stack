# Diagnostic Spine Roadmap

## Current route

- keep readiness, diagnose wrappers, truth surfaces, and diagnostic contracts
  in separate parts
- keep generated diagnostic catalog parity checked
- keep diagnostic handoffs advisory until reviewed by the repair or owner route

## Next candidates

- route drifted diagnostic packets into explicit repair governance only when
  an operator asks for a repair packet
- add a package-local check for doctor/diagnose wrapper parity if wrappers grow
- split companion summaries from machine-readable contracts if the schema set
  expands
- add a small owner-handoff fixture only when runtime-repair needs a stronger
  contract

## Stop-lines

- do not make diagnostics perform repair
- do not treat generated catalog output as stronger than source docs
- do not expose private host facts in public examples
