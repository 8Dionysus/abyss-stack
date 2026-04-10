# Spark lane for abyss-stack

This file governs work on files under the `Spark/` subtree.

The root `AGENTS.md` remains authoritative for repository identity, ownership boundaries, reading order, and validation commands. This local file only narrows how GPT-5.3-Codex-Spark should behave when used as the fast-loop lane.

If `SWARM.md` exists in this directory, treat it as queue / swarm context. This `AGENTS.md` is the operating policy for Spark work.

## Default Spark posture

- Use Spark for short-loop work where a small diff is enough.
- Start with a map: task, files, risks, and validation path.
- Prefer one bounded patch per loop.
- Read the nearest source docs before editing.
- Use the narrowest relevant validation already documented by the repo.
- Report exactly what was and was not checked.
- Escalate instead of widening into a broad architectural rewrite.

## Spark is strongest here for

- compose, template, and runbook alignment
- path fixes and profile-aware script cleanup
- small systemd, env, or config-template corrections with local scope
- service-catalog wording cleanup
- tight audits of placeholder hygiene and public-safe examples

## Do not widen Spark here into

- network-exposure changes
- secret-flow redesign
- storage or topology redesign
- wide infra rewrites across many modules or profiles
- host-affecting or destructive changes without an explicit rollback path

## Local done signal

A Spark task is done here when:

- the diff is reversible and local
- Fedora-first and local-first posture are preserved
- runtime and meaning layers remain separate
- secret-bearing material stayed out of committed surfaces
- the narrowest relevant verification path was run or the gap was stated plainly

## Local note

Spark should behave like an infra mechanic here: small tools, clear rollback, no heroic rewiring.

## Reporting contract

Always report:

- the restated task and touched scope
- which files or surfaces changed
- whether the change was semantic, structural, or clarity-only
- what validation actually ran
- what still needs a slower model or human review
