# Federation Seams Roadmap

## Current route

- keep sibling-owner seams optional and profile-visible
- keep compatibility names isolated behind explicit bridge config and legacy
  inventory
- keep generated RPG runtime collections source-rebuilt and checked
- keep KAG runtime projection cost, latency, retrieval quality, and retention
  measured against the bundle and receipts
- keep route-api consumption subordinate to owner repositories
- keep current routing ABI fields and mirror hashes fail-closed while the
  `aoa-sdk` successor remains shadow-only

## Next candidates

- decide whether a live runtime consumer should read the materialized RPG
  file contract, without adding live `/rpg/*` endpoints or source quest
  mutation by accident
- add a seam summary matrix if owner routes become hard to scan from `PARTS.md`
- split route-api specific federation checks if the service grows more
  independent from sync checks
- admit an exact routing trust verdict and SDK producer identity only through
  the reviewed M2/G5 runtime cutover contract
- add stronger contract tests for owner mirror inputs only when a downstream
  runtime consumer requires them

## Stop-lines

- do not copy sibling doctrine into this repository as source truth
- do not make federation mandatory without profile, preset, config, and
  validation movement
- do not let upstream compatibility IDs become active local names again
