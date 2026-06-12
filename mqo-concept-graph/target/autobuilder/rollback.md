# Rollback plan

HEAD: `46c7cf929adbeb0d91b6816b0de3e8e3ec112452`
Base: `HEAD~1` (`578470fdcf28bf5d8516a0f9e7df882fc4dd4416`)

Reverts are listed newest → oldest. Each `git revert` was
dry-run via `git merge-tree --write-tree` against current HEAD,
so the working tree was not touched during verification.

| # | sha | revertable | command | subject |
|---|---|---|---|---|
| 1 | `46c7cf9` | ✓ | `git revert 46c7cf9` | autobuilder: finalize reviewer and proof receipts for mqo-concept-graph |

## Notes

- `46c7cf9` — clean revert
