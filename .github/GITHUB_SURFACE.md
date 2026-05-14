# GitHub Surface

`.github/` contains the GitHub-native platform surface for this repository.
This map is intentionally not named `README.md`: GitHub may select
`.github/README.md` as the repository homepage README and hide the root
source-checkout front door.

## Current Surfaces

- [workflows/validate-stack.yml](workflows/validate-stack.yml): repository
  validation check.
- [workflows/mirror-canary.yml](workflows/mirror-canary.yml): source/install
  mirror canary.
- [pull_request_template.md](pull_request_template.md): PR closeout template.
- [CODEOWNERS](CODEOWNERS): ownership routing for review.

GitHub automation must remain public-safe and weaker than source-owned
repository docs. It should validate the source checkout; it should not mutate
deployed runtime state or sibling repositories.

See [AGENTS.md](AGENTS.md) for editing rules.
