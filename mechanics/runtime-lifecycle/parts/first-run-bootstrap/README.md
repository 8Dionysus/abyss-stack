# First Run Bootstrap

Routes `scripts/aoa-first-run`, with the implementation in
`mechanics/runtime-lifecycle/parts/first-run-bootstrap/aoa_first_run.sh`.

This part composes layout install, source-to-runtime sync, public template
bootstrap, and layout check for the first operator pass. It keeps missing
secrets explicit instead of pretending first-run creates live private state.
