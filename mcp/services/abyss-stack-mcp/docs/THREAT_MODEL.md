# Threat model

## Protected claims

- a read caller cannot enumerate or prepare candidate/runtime effects;
- a candidate output cannot claim execution authority;
- stale or replaced evidence cannot silently authorize a plan;
- a compromised owner adapter cannot self-assert stack provenance;
- one credential cannot cross owner or policy contours.

## Controls

- a separate credential for each read and candidate process, alongside
  separate ports, tools, scopes, and client identities;
- loopback-only HTTP with DNS-rebinding protection;
- explicit regular observation file with symlink rejection and a 2 MiB limit;
- strict input and output models with unknown fields denied;
- secret-like material rejected before validation or response;
- URI-like references reject credential-bearing userinfo and forbidden
  query/fragment keys before validation or response;
- exact observation digest and short expiry for candidate plans;
- structured allowlisted plan actions with no free-form command;
- active processes require an observed process identity rather than a bare
  boolean;
- activation requires a passed central-proof verdict issued by `proof_owner`
  and bound to the current source/package/deploy/schema/consumer/canary
  contour;
- activation requires acceptance-owner evidence bound to the exact source
  revision and package digest, and carries that expiring receipt into the
  candidate;
- required evidence timestamps cannot postdate the observation snapshot beyond
  the bounded clock-skew allowance;
- rollback-required links need explicit unexpired evidence and cannot fail late
  through candidate-model validation;
- server-side read-subject filtering before catalog result construction and
  higher-policy inspection rejection before observation loading;
- server-side policy checks independent of MCP annotations or model behavior.

## Confused deputy

The server never proxies another MCP tool and never dispatches a plan. An
operator or later effect plane must revalidate the exact target, evidence,
approval, current snapshot, postcondition canary, and rollback route. Discovery
therefore cannot turn this service into a confused deputy for sibling
authority.

## Residual risk

A same-UID process that can read the deployed Secrets tree remains outside the
protection offered by bearer authentication. OS-user or container isolation is
required before any effect plane. No effect plane is admitted by this package.
