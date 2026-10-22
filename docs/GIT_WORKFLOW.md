# Git Workflow for PricePulse

## Is `git add .` okay?

Yes, `git add .` is a normal Git command. It stages all changes and untracked files under the current directory, except files excluded by ignore rules. It is not inherently wrong, but it can stage files you did not intend to publish. The important habit is to inspect the staged changes before committing.

## Before staging

Run:

```bash
git status --short
```

Review the files shown. Check that `.gitignore` includes at least:

```gitignore
.venv/
__pycache__/
*.py[cod]
.env
data/raw/*
!data/raw/.gitkeep
```

This is a starting point, not a universal complete ignore file. Add editor caches, local logs, database dumps, secrets, or other generated artifacts when the project creates them.

**Important:** `.gitignore` does not untrack a file that was committed or already tracked before the ignore rule was added. If a secret was committed, deleting it in a later commit does not make the secret safe again; rotate/revoke it.

## Safer staging pattern

For a documentation-only commit:

```bash
git add README.md docs/
git status --short
git diff --cached --stat
git diff --cached --name-only
git diff --cached
```

Review the staged diff. Then commit:

```bash
git commit -m "docs: document PricePulse pipeline"
```

For a normal code milestone, you can stage selected paths:

```bash
git add scripts/ tests/ sql/ requirements.txt
```

Or use `git add .`, but still inspect the staged file list and diff before committing.

## If you already ran `git add .`

No need to panic. It stages files locally; it does not automatically commit or push them. Inspect:

```bash
git status --short
git diff --cached --name-only
git diff --cached --stat
```

To unstage one accidental file while keeping it on disk:

```bash
git restore --staged path/to/file
```

To stop tracking a file that should remain locally but be ignored going forward:

```bash
git rm --cached path/to/file
```

Only do this after checking the path carefully. If the file contains a password or token, rotate it if it may have been exposed.

## Commit and push

After reviewing the staged diff:

```bash
git commit -m "Describe the change in a short, specific sentence"
git push
```

The `git push` command sends the local commit to the configured remote. `git add` only stages changes, and `git commit` records them locally.

## What should be committed?

Good candidates:

- Python source code, SQL scripts, tests, and documentation.
- `requirements.txt` for the development environment.
- Small fixtures or sample datasets that are intentionally part of tests and can legally be redistributed.
- Architecture diagrams or reproducible configuration, without secrets.

Review deliberately before committing:

- `data/processed/*.csv`: generated outputs may be useful as a small demonstration, but the repository should state whether they are tracked or regenerated.
- `data/raw/*.json`: source snapshots can be useful for reproducibility but may grow over time; this project currently ignores them.
- database dumps and logs: usually keep them out unless there is a specific, documented need.

Never commit:

- `.venv/` or Python cache files.
- `.env` files containing secrets, real passwords, API tokens, or private credentials.
- Local database data directories or large accidental output files.
