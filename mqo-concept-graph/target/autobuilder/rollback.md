# Rollback plan

HEAD: `db1dfc638ded610e21820e6b56986a7941005207`
Base: `HEAD~1` (`7f0cd8d8389c0f481babda34336135d82dfccf06`)

Reverts are listed newest → oldest. Each `git revert` was
dry-run via `git merge-tree --write-tree` against current HEAD,
so the working tree was not touched during verification.

| # | sha | revertable | command | subject |
|---|---|---|---|---|
| 1 | `db1dfc6` | ✓ | `git revert db1dfc6` | autobuilder: fix proof-lanes globs for monorepo paths |

## Notes

- `db1dfc6` — clean revert
