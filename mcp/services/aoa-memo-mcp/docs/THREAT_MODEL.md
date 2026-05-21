# Threat Model

## Main Risks

- untrusted source text becomes durable memory;
- indirect prompt injection is copied into a candidate as instruction;
- local runtime evidence is over-promoted into central truth;
- stale memory beats current repository evidence;
- session archive summaries are treated as raw evidence;
- MCP tool metadata or tool results are trusted beyond their owner layer.

## Controls

- Candidate validation requires evidence refs and rejects direct durable writes
  from untrusted or review-required sources.
- Port validation requires `PORT.yaml`, packet shape, generated index parity,
  and local check/export routes before durable landing is proposed.
- Packet validation uses `aoa-memo` memory-port schemas and confines
  candidate/export/receipt paths to known local `memo/` ports.
- Briefs report operation mode and owner hierarchy before suggesting a write.
- MCP resources expose pointers and compact route data, not full raw archives.
- Local ports default to `write_candidate_only`.
- Durable memory promotion remains outside this MCP server.

## Guardrail Rule

When source trust is `untrusted`, `unknown`, or `review_required`, the candidate
may only route to review. It may not validate as direct durable memory.
