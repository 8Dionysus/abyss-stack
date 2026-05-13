# .github

`.github/` contains the GitHub-native platform surface for this repository.

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

