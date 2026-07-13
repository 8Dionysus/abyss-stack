# Federation Seams Direction

This package keeps sibling-owner consumption optional, explicit, and
subordinate to the repositories that own the meaning.

Current posture:

- keep sync wrappers and federation checks package-local
- keep route-api and advisory mirrors consuming public-safe owner surfaces
  without becoming the owner of those surfaces
- keep upstream compatibility IDs behind explicit compatibility bridges
- keep RPG, repo-self KAG, and ToS graph projections as source-derived runtime
  read models

Near direction:

- keep owner-boundary docs aligned across memo, eval, playbook, KAG, ToS, and
  RPG seams
- keep generated RPG runtime collections rebuilt from source
- keep repo-self exact, vector, and graph projections bound to one verified
  `aoa-kag` bundle identity
- make federation profile activation visible before runtime consumption widens
- route stronger owner changes to the relevant sibling repository instead of
  copying authority here
