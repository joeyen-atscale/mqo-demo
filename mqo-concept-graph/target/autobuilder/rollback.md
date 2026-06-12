# Rollback plan

HEAD: `8ed2068e90c44f94667ef9d2d7e71f34a3b71343`
Base: `HEAD~1` (`fa887b233f9e4204d4532fed2addd1c3fabaa9af`)

Reverts are listed newest → oldest. Each `git revert` was
dry-run via `git merge-tree --write-tree` against current HEAD,
so the working tree was not touched during verification.

| # | sha | revertable | command | subject |
|---|---|---|---|---|
| 1 | `8ed2068` | ✓ | `git revert 8ed2068` | autobuilder: implement mqo-concept-graph |

## Notes

- `8ed2068` — clean revert
