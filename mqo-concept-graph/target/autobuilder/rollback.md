# Rollback plan

HEAD: `578470fdcf28bf5d8516a0f9e7df882fc4dd4416`
Base: `HEAD~1` (`db1dfc638ded610e21820e6b56986a7941005207`)

Reverts are listed newest → oldest. Each `git revert` was
dry-run via `git merge-tree --write-tree` against current HEAD,
so the working tree was not touched during verification.

| # | sha | revertable | command | subject |
|---|---|---|---|---|
| 1 | `578470f` | ✓ | `git revert 578470f` | autobuilder: update gate receipts for mqo-concept-graph (iter 2) |

## Notes

- `578470f` — clean revert
