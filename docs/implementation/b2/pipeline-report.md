# B2 Pipeline Handoff Report

Baseline: `df57452c3e1bc52a1afc7423eca9a235c582b543`  
Branch: `fix/b2-pipeline-handoff`

## Fixes

### F1 — Catalog payload handoff
- Added `src/jev_awesome/automation/payload.py` (`SCHEMA_VERSION=1`) with `export_catalog_payload` / `import_catalog_payload`.
- Manifest includes schema_version, repository, source_sha, run_id, attempt, created_at, resource_ids, file_hashes, coverage, dispositions, payload_hash.
- Import validates paths/hashes/repo; loads existing via `CatalogStore.get_resource` **before** `filter_machine_resource_update`; writes inbox only.
- CLI: `jev-awesome payload export --out DIR`; `jev-awesome publish --payload DIR`.
- `collect.yml`: export to `artifacts/catalog-payload/`; upload `collect-report` + `catalog-payload`; publish downloads payload and fails if missing; `payload_ready` output.

### F2 — Schedule `dry_run` stuck true
- Extracted `scripts/resolve_collect_flags.sh`.
- After workflow_dispatch check: `schedule && collector=true` → `dry_run=false`.
- Schedule without collector still skips (`skip=true`, `dry_run=true`).

### F3 — Cold-start robot identity
- Allowlisted `data/automation/` in write policy.
- Publisher persists `data/automation/robot_identity.json` as a second robot commit (last_robot_sha, known_robot_shas, updated_at).
- Hydrate order: worktree → remote robot tip → recovered PR head; `data/cache` is optional acceleration only.
- Tip trusted only when `tip == identity.last` or `parent(tip) == identity.last` (human-on-top rejected).

### F4 — Real GitHub HTTP contract
- `pr_is_merged(pr)`: `merged is True` OR non-null `merged_at` string.
- Publisher lists PRs via `get_json` only (`?state=&head=owner:branch` + page budget); no `getattr` Fake helpers.
- `_robot_pr_merged` returns False while an open robot PR exists; no branch delete/rebuild in that case.
- Fake list responses omit `merged` boolean (shared `normalize_pr_list_item`).

### F5 — Inbox editorial baseline
- `_revalidate_inbox_fields` uses `CatalogStore.get_resource` (resources + inbox).
- Payload import merges against trusted baseline before writing inbox.

## Test nodeids (new / key)

| Area | Nodeids |
|------|---------|
| F2 | `tests/test_workflow_flags.py::test_collect_flags_matrix[...]` (parametrized matrix); `tests/test_workflow_flags.py::test_workflow_uses_flags_script` |
| F1 | `tests/integration/test_payload_handoff.py::test_payload_handoff_two_independent_checkouts`; `tests/integration/test_payload_handoff.py::test_publish_without_payload_fails_when_required` |
| F3 | `tests/integration/test_cold_start_rounds.py::test_cold_start_rounds_no_cache_reuse`; `tests/integration/test_cold_start_rounds.py::test_cold_start_pr_create_fail_then_recover` |
| F4 | `tests/test_github_pr_contract.py::test_pr_is_merged_via_merged_at_without_merged_field`; `::test_fake_list_responses_omit_merged_field`; `::test_historical_merged_plus_open_pr_continues_no_branch_delete`; `::test_publisher_uses_get_json_not_fake_helpers` |
| F5 | `tests/test_payload_inbox_protect.py::test_payload_import_preserves_summary_zh` |

## Verification

```
uv sync --frozen
uv run ruff check .
uv run ruff format --check .
uv run basedpyright
uv run pytest          # 83 passed
uv run jev-awesome validate
uv run jev-awesome render --check
```

Formal catalog data under `data/resources` / curated paths untouched.  
`docs/implementation/bootstrap/` left untracked (B1 evidence).

## Remaining gaps

- Live GitHub Actions schedule path not exercised in this commit (needs `COLLECTOR_ENABLED=true` + real run).
- `expected_source_sha` mismatch on import is strict; publish workflow does not yet pass publish-base SHA as expected (optional hardening).
- Identity is a second robot commit per publish (acceptable; not single-tree tip==last).
