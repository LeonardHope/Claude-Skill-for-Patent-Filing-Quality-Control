# Contributing

## ⚠️ This repository is PUBLIC — never commit client or firm material

This tool is frequently run against **unfiled** patent applications. Real matter
data must never enter the repository — not in code, comments, tests, fixtures,
commit messages, **or pull-request titles/descriptions**.

Never commit:

- **Firm docket / file numbers** (real matter numbers — use `X000-0000US` instead)
- **Invention titles, abstracts, claim or specification text, drawing labels**
- **Inventor, assignee, or client names; addresses; emails**
- **Firm branding**

Use the obviously-synthetic placeholders the test suite already relies on:

| Kind            | Placeholder |
|-----------------|-------------|
| Docket number   | `X000-0000US` (fake family: `X000-…` / `X999-…`) |
| Invention title | `WIDGET ASSEMBLY DEVICE` |
| Inventors       | `Alice J. EXAMPLE`, `Carol Dana SAMPLE` |
| Assignee / firm | `ACME CORP.` |
| Practitioner    | `Dana X. TESTER`, Reg. No. `00000` |

When a bug is found by reviewing a real matter, describe the **technical
pattern** generically (e.g. "a title that line-breaks mid-word", "rotated
drawings whose text extracts in reverse") — never name the matter or quote its
content.

## Automated guard

`scripts/check_no_client_material.py` blocks docket-shaped tokens that aren't
allowlisted placeholders. It runs in two places:

- **CI** — `.github/workflows/no-client-material.yml` scans the tree on every
  push and pull request and fails if it finds anything.
- **Pre-commit** — enable the local hook once:

  ```sh
  git config core.hooksPath .githooks
  ```

  After that, commits containing a real-looking docket number are rejected
  (bypass with `git commit --no-verify` only if you are certain it's a false
  positive; genuine false positives should be added to `ALLOW` in the script).
