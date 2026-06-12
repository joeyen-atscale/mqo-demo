# Postmortem — mqo-concept-graph

HEAD: `46c7cf929adbeb0d91b6816b0de3e8e3ec112452`

## Iteration breakdown

- total: 3
- baseline: 1
- revert: 2
- receipts on disk: 10
- failure capsules: 0

## results.tsv

| iter | commit | metric | ACs | status | description |
|---|---|---|---|---|---|
| 1 | `8ed2068` | 20 | 4/4 | baseline | initial implementation |
| 2 | `db1dfc6` | 20 | 4/4 | revert | add gate receipts and proof-lanes |
| 3 | `578470f` | 20 | 4/4 | revert | finalize gate receipts |

## Notes

- revert ratio 2/0 suggests the edit-agent is regressing more than improving
