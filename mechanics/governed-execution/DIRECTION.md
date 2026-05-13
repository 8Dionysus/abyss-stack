# Governed Execution Direction

This package keeps local-worker execution reviewable, bounded, and exportable
without turning runtime into autonomous authority.

Current posture:

- keep governed-run records, autonomy status, return policy, and candidate
  exports part-local
- keep root wrappers stable while implementation bodies live under package
  parts
- keep candidate exports as handoff material, not owner acceptance
- keep local-worker context budget and return policy visible before execution
  widens

Near direction:

- keep schema/example/test coverage paired with run-record or candidate-export
  movement
- keep autonomy status as a readout, not a control-plane verdict
- route memory, proof, playbook, and skill meaning to stronger owner
  repositories
- keep recurrence and return language bounded, evidence-linked, and reversible
