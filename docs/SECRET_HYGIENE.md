# Secret Hygiene (Phase 18.5)

We use [Yelp/detect-secrets](https://github.com/Yelp/detect-secrets) to prevent accidental secret commits.

## Overview

- **Baseline file:** `.secrets.baseline` — committed to the repo, acts as an allowlist of known non-secrets (test DB creds, placeholder API keys, etc.)
- **Pre-commit hook:** Defined in `.pre-commit-config.yaml`; runs on every commit
- **CI check:** Runs on every push and PR via `.github/workflows/integration-tests.yml`

## For Contributors

- The pre-commit hook runs automatically on every commit via `.pre-commit-config.yaml`.
- If a commit introduces a new secret, the pre-commit hook will block it and show you which file/line caused the issue.
- If the detection is a **false positive** (e.g., a test fixture with a dummy API key):

  1. Run `pre-commit run detect-secrets --all-files` to see the output.
  2. Add a comment to the flagged line: `# pragma: allowlist secret` (Python) or `// pragma: allowlist secret` (JS/TS).
  3. Regenerate the baseline: `detect-secrets scan . > .secrets.baseline`
  4. Commit the updated `.secrets.baseline` alongside your change.

## For Maintainers

- The `.secrets.baseline` is committed to the repo and acts as an allowlist.
- CI runs `detect-secrets scan --baseline .secrets.baseline --all-files` on every PR. Any new secret fails the build.
- To audit the baseline interactively: `detect-secrets audit .secrets.baseline`
- To rotate or update the baseline after legitimate changes:

  ```bash
  detect-secrets scan . > .secrets.baseline
  ```

  Then commit the updated `.secrets.baseline`.
