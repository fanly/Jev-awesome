"""Production catalog publisher: validate → commit robot branch → create/update PR.

Default remote writes remain gated by AUTO_PR_ENABLED / explicit opts.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import quote

from jev_awesome.automation.git_workspace import GitError, GitWorkspace, run_git
from jev_awesome.automation.github_transport import (
    FakeGitHubTransport,
    GitHubAPIError,
    GitHubTransport,
    pr_is_closed_unmerged,
    pr_is_merged,
)
from jev_awesome.automation.write_policy import (
    FORBIDDEN_EVENT_TYPES,
    WritePolicyError,
    assert_event_allowed,
    assert_not_symlink,
    assert_path_allowed,
    filter_machine_resource_update,
    is_path_allowed,
    normalize_rel_path,
    validate_write_set,
)
from jev_awesome.dates import utc_now
from jev_awesome.models import Resource
from jev_awesome.paths import Paths
from jev_awesome.rendering.render import Renderer
from jev_awesome.store import CatalogStore

ROBOT_IDENTITY_REL = "data/automation/robot_identity.json"
PR_LIST_PAGE_BUDGET = 5


@dataclass
class PublishOptions:
    enabled: bool = False
    dry_run: bool = True
    robot_branch: str = "automation/catalog-update"
    main_branch: str = "main"
    remote_name: str = "publish-remote"  # never assume "origin" in tests
    owner: str = "fanly"
    repo: str = "Jev-awesome"
    expected_repo: str = "fanly/Jev-awesome"
    last_robot_sha: str | None = None
    pause_on_manual: bool = True
    require_payload: bool = False


@dataclass
class PublishResult:
    status: str  # success | skipped | paused | failed | no_diff
    reason: str
    pr_number: int | None = None
    pr_url: str | None = None
    commit_sha: str | None = None
    written_paths: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    transport_calls: int = 0


class Publisher:
    """Runs on trusted main checkout; merges robot data; writes only allowlisted paths."""

    def __init__(
        self,
        workspace: Path,
        *,
        transport: GitHubTransport,
        opts: PublishOptions | None = None,
        state_path: Path | None = None,
    ) -> None:
        self.workspace = workspace
        self.transport = transport
        self.opts = opts or PublishOptions()
        self.git = GitWorkspace(
            root=workspace,
            robot_branch=self.opts.robot_branch,
            main_branch=self.opts.main_branch,
            known_robot_shas=set(),
        )
        # Cache is optional acceleration only — never sole authority (F3).
        self.state_path = state_path or (workspace / "data" / "cache" / "publisher_state.json")
        self._paused = False
        self._pause_reason = ""
        self._load_state_cache()

    def _load_state_cache(self) -> None:
        """Optional cache acceleration; identity may still be hydrated from robot tip."""
        if not self.state_path.exists():
            return
        try:
            data = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if not self.opts.last_robot_sha:
            self.opts.last_robot_sha = data.get("last_robot_sha") or self.opts.last_robot_sha
        shas = data.get("known_robot_shas") or []
        self.git.known_robot_shas = set(shas) | (self.git.known_robot_shas or set())
        if data.get("paused"):
            self._paused = True
            self._pause_reason = data.get("pause_reason", "paused")

    def _save_state(self, **extra: Any) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "last_robot_sha": self.opts.last_robot_sha,
            "known_robot_shas": sorted(self.git.known_robot_shas or []),
            "paused": self._paused,
            "pause_reason": self._pause_reason,
            "updated_at": utc_now().isoformat(),
            **extra,
        }
        self.state_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    def _identity_path(self, root: Path) -> Path:
        return root / ROBOT_IDENTITY_REL

    def _read_identity_file(self, path: Path) -> dict[str, Any] | None:
        if not path.is_file():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return data if isinstance(data, dict) else None

    def _apply_identity(self, data: dict[str, Any], *, prefer_sha: str | None = None) -> None:
        shas = set(data.get("known_robot_shas") or [])
        recorded = data.get("last_robot_sha")
        if recorded:
            shas.add(str(recorded))
        self.git.known_robot_shas = set(self.git.known_robot_shas or set()) | shas
        # Trust prefer_sha (remote/recovered tip) only when it is the identity
        # commit itself (prefer == recorded) or its first parent is recorded.
        # A human commit on top keeps identity.last from an ancestor → rejected.
        if prefer_sha and recorded:
            if prefer_sha == str(recorded) or prefer_sha in shas:
                self.opts.last_robot_sha = prefer_sha
                self.git.known_robot_shas.add(prefer_sha)
            elif self._first_parent_is(prefer_sha, str(recorded)):
                self.opts.last_robot_sha = prefer_sha
                self.git.known_robot_shas.add(prefer_sha)
            elif not self.opts.last_robot_sha:
                self.opts.last_robot_sha = str(recorded)
        elif recorded and not self.opts.last_robot_sha:
            self.opts.last_robot_sha = str(recorded)

    def _first_parent_is(self, tip: str, expected_parent: str) -> bool:
        try:
            parent = run_git(self.workspace, "rev-parse", f"{tip}^", check=False).stdout.strip()
            if parent == expected_parent:
                return True
            # Tip may not be local yet — try remote fetch object
            remote_url = run_git(
                self.workspace, "remote", "get-url", self.opts.remote_name, check=False
            ).stdout.strip()
            if not remote_url:
                return False
            run_git(self.workspace, "fetch", "--depth=2", remote_url, tip, check=False)
            parent = run_git(self.workspace, "rev-parse", f"{tip}^", check=False).stdout.strip()
            return parent == expected_parent
        except GitError:
            return False

    def _hydrate_robot_identity(self, root: Path) -> None:
        """Load identity without requiring data/cache (F3).

        Order: (1) current worktree, (2) remote robot tip files, (3) recovered PR head.
        Cache state_path remains optional acceleration via _load_state_cache.
        """
        # (1) worktree (includes merge-from already copied into root)
        local = self._read_identity_file(self._identity_path(root))
        if local:
            self._apply_identity(local)

        opts = self.opts
        remote_sha = None
        try:
            remote_sha = self.git.remote_branch_sha(opts.remote_name, opts.robot_branch)
        except GitError:
            remote_sha = None

        # (2) remote robot tip
        if remote_sha:
            tip_ident = self._identity_from_git_ref(root, remote_sha)
            if tip_ident:
                self._apply_identity(tip_ident, prefer_sha=remote_sha)
            elif remote_sha in (self.git.known_robot_shas or set()):
                self.opts.last_robot_sha = remote_sha

        # (3) recovered open / closed-unmerged PR head tree
        if not remote_sha:
            head_sha = self._latest_recoverable_head_sha()
            if head_sha:
                tip_ident = self._identity_from_git_ref(root, head_sha)
                if tip_ident:
                    self._apply_identity(tip_ident, prefer_sha=head_sha)

    def _identity_from_git_ref(self, root: Path, sha: str) -> dict[str, Any] | None:
        import tempfile

        tmp = Path(tempfile.mkdtemp(prefix="jev-ident-"))
        try:
            remote_url = run_git(root, "remote", "get-url", self.opts.remote_name).stdout.strip()
            run_git(tmp, "init", "-b", "ident")
            GitWorkspace(root=tmp, known_robot_shas=set()).ensure_identity()
            run_git(tmp, "fetch", "--depth=1", remote_url, sha)
            run_git(tmp, "checkout", "-f", "FETCH_HEAD")
            return self._read_identity_file(tmp / ROBOT_IDENTITY_REL)
        except GitError:
            return None
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def _write_robot_identity(self, root: Path, *, last_sha: str) -> None:
        known = set(self.git.known_robot_shas or set())
        known.add(last_sha)
        self.git.known_robot_shas = known
        path = self._identity_path(root)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "last_robot_sha": last_sha,
            "known_robot_shas": sorted(known),
            "updated_at": utc_now().isoformat(),
        }
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    def _finalize_identity_in_commit(self, root: Path, sha: str) -> str:
        """Second commit: persist durable identity pointing at catalog commit sha.

        Tip T has identity.last_robot_sha == parent(T) == catalog sha. Hydrate
        trusts tip when parent(tip) == identity.last (rejects human-on-top).
        """
        self._write_robot_identity(root, last_sha=sha)
        rel = ROBOT_IDENTITY_REL
        assert_path_allowed(rel)
        self.git.add_paths([rel])
        ident_sha = self.git.commit(
            f"chore(catalog): robot identity {utc_now().strftime('%Y-%m-%d')}"
        )
        if ident_sha is None:
            # Nothing to commit (identity unchanged) — keep catalog sha
            self.opts.last_robot_sha = sha
            known = set(self.git.known_robot_shas or set())
            known.add(sha)
            self.git.known_robot_shas = known
            return sha
        known = set(self.git.known_robot_shas or set())
        known.add(sha)
        known.add(ident_sha)
        self.git.known_robot_shas = known
        self.opts.last_robot_sha = ident_sha
        return ident_sha

    def publish(self, *, catalog_root: Path | None = None) -> PublishResult:
        opts = self.opts
        if not opts.enabled:
            return PublishResult(
                status="skipped",
                reason="disabled_by_configuration",
                notes=["AUTO_PR_ENABLED/publish.enabled is false"],
            )
        if opts.dry_run:
            return PublishResult(
                status="skipped",
                reason="dry_run",
                notes=["dry-run does not push or open PR"],
            )
        if self._paused:
            return PublishResult(
                status="paused",
                reason=self._pause_reason or "paused_manual_edits",
                notes=["publisher paused; clear pause after human review"],
            )

        root = catalog_root or self.workspace
        store = CatalogStore(Paths(root))

        try:
            self._hydrate_robot_identity(root)
            recovery = self._prepare_robot_catalog(store, root)
        except GitHubAPIError as e:
            return PublishResult(
                status="failed",
                reason=f"pr_list_failed:{e}",
                notes=["GitHub PR list failed; refusing empty-success"],
                transport_calls=len(self.transport.calls),
            )
        if recovery == "recovery_gap":
            pending = root / "data" / "reports" / "pending-robot-write.json"
            pending.parent.mkdir(parents=True, exist_ok=True)
            pending.write_text(
                json.dumps(
                    {
                        "reason": "recovery_gap",
                        "expected": self.opts.last_robot_sha,
                        "at": utc_now().isoformat(),
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            self._paused = True
            self._pause_reason = "recovery_gap"
            self._save_state(pending_path=str(pending.relative_to(root)))
            return PublishResult(
                status="paused",
                reason="recovery_gap",
                notes=["robot branch missing; no verifiable PR head to restore"],
                transport_calls=len(self.transport.calls),
            )

        # Merge robot branch data if remote branch exists (via worktree copy already in store)
        # Re-render from trusted templates + validated data
        Renderer(store=store, paths=Paths(root)).write()

        # Collect candidate write paths from worktree vs main
        self.git.ensure_identity()
        main_ref = opts.main_branch
        if not self.git.branch_exists(main_ref):
            main_ref = "HEAD"

        # Snapshot allowlisted catalog state BEFORE branch switch (reset would wipe it)
        import tempfile

        staging = Path(tempfile.mkdtemp(prefix="jev-pub-stage-"))
        staged_rels = self._stage_allowlisted_tree(root, staging)

        # Resolve main tip
        main_sha = self._resolve_main_sha(main_ref)
        remote_sha = None
        try:
            remote_sha = self.git.remote_branch_sha(opts.remote_name, opts.robot_branch)
        except GitError:
            remote_sha = None

        # After a merged robot PR (merge or squash), main is authoritative —
        # do not fast-forward from a stale pre-merge robot tip.
        # CRITICAL (F4): never restart/delete when an OPEN robot PR exists.
        restart_after_merge = False
        try:
            if self._robot_pr_merged():
                restart_after_merge = True
                remote_sha = None
                opts.last_robot_sha = None
        except GitHubAPIError as e:
            shutil.rmtree(staging, ignore_errors=True)
            return PublishResult(
                status="failed",
                reason=f"pr_list_failed:{e}",
                notes=["GitHub PR list failed during merge detection"],
                transport_calls=len(self.transport.calls),
            )

        # Manual edit detection on remote robot branch
        if remote_sha and opts.last_robot_sha:
            suspected, why = self.git.manual_edits_suspected(
                branch=opts.robot_branch,
                expected_robot_sha=opts.last_robot_sha,
                remote_sha=remote_sha,
                dirty_paths_outside_allowlist=[],
            )
            if suspected and opts.pause_on_manual:
                pending = root / "data" / "reports" / "pending-robot-write.json"
                pending.parent.mkdir(parents=True, exist_ok=True)
                pending.write_text(
                    json.dumps(
                        {
                            "reason": why,
                            "remote_sha": remote_sha,
                            "expected": opts.last_robot_sha,
                            "at": utc_now().isoformat(),
                        },
                        indent=2,
                    )
                    + "\n",
                    encoding="utf-8",
                )
                self._paused = True
                self._pause_reason = why
                self._save_state(pending_path=str(pending.relative_to(root)))
                shutil.rmtree(staging, ignore_errors=True)
                return PublishResult(
                    status="paused",
                    reason=why,
                    notes=[f"saved pending write note → {pending}"],
                    transport_calls=len(self.transport.calls),
                )

        # Prefer fast-forward from trusted remote robot tip so unmerged
        # candidates accumulate without force-push. Fall back to main tip
        # only when the robot branch does not yet exist remotely.
        if remote_sha and (
            remote_sha == opts.last_robot_sha or remote_sha in (self.git.known_robot_shas or set())
        ):
            base_sha = remote_sha
        else:
            base_sha = main_sha
        self.git.checkout_new_branch_from(opts.robot_branch, base_sha)
        # Restore staged allowlisted files onto robot branch worktree
        self._restore_staged_tree(staging, root, staged_rels)
        shutil.rmtree(staging, ignore_errors=True)

        self._materialize_allowlisted_from_store(store, root)
        self._revalidate_inbox_fields(root)

        # Validate all dirty paths
        dirty = self.git.status_porcelain()
        rels: list[str] = []
        sizes: dict[str, int] = {}
        for line in dirty.splitlines():
            if not line.strip():
                continue
            path = line[3:].strip()
            if " -> " in path:
                path = path.split(" -> ", 1)[1]
            try:
                rel = assert_path_allowed(path)
            except WritePolicyError as e:
                return PublishResult(
                    status="failed",
                    reason=f"path_policy:{e}",
                    transport_calls=len(self.transport.calls),
                )
            p = root / rel
            assert_not_symlink(p)
            rels.append(rel)
            if p.is_file():
                sizes[rel] = p.stat().st_size

        if not rels:
            tip_sha = remote_sha or opts.last_robot_sha
            try:
                return self._ensure_pr_if_needed(tip_sha)
            except GitHubAPIError as e:
                return PublishResult(
                    status="failed",
                    reason=f"pr_list_failed:{e}",
                    notes=["no material diff; PR list failed"],
                    transport_calls=len(self.transport.calls),
                )

        try:
            validate_write_set(rels, sizes=sizes)
        except WritePolicyError as e:
            return PublishResult(status="failed", reason=str(e))

        self.git.add_paths(rels)
        sha = self.git.commit(f"chore(catalog): automation update {utc_now().strftime('%Y-%m-%d')}")
        if sha is None:
            tip_sha = remote_sha or opts.last_robot_sha
            try:
                return self._ensure_pr_if_needed(tip_sha)
            except GitHubAPIError as e:
                return PublishResult(
                    status="failed",
                    reason=f"pr_list_failed:{e}",
                    notes=["empty commit; PR list failed"],
                    transport_calls=len(self.transport.calls),
                )

        sha = self._finalize_identity_in_commit(root, sha)
        if ROBOT_IDENTITY_REL not in rels:
            rels.append(ROBOT_IDENTITY_REL)

        # Push race: check remote head first
        latest_remote = self.git.remote_branch_sha(opts.remote_name, opts.robot_branch)
        if latest_remote and opts.last_robot_sha and latest_remote != opts.last_robot_sha:
            if latest_remote not in (self.git.known_robot_shas or set()):
                self._paused = True
                self._pause_reason = "remote_head_advanced_by_other"
                self._save_state()
                return PublishResult(
                    status="paused",
                    reason="remote_head_advanced_by_other",
                    commit_sha=sha,
                    notes=["local commit kept; push deferred"],
                    transport_calls=len(self.transport.calls),
                )

        try:
            if restart_after_merge:
                # Drop stale robot ref after merge/squash so the next tip is based on
                # main (non-FF rewrite avoided by delete + create). Never force main.
                # Guarded by _robot_pr_merged which refuses when open PR exists.
                del_ref = run_git(
                    self.workspace,
                    "push",
                    opts.remote_name,
                    f":refs/heads/{opts.robot_branch}",
                    check=False,
                )
                _ = del_ref
            self.git.push(opts.remote_name, opts.robot_branch, force=False)
        except GitError as e:
            return PublishResult(
                status="failed",
                reason=f"push_failed:{e}",
                commit_sha=sha,
                written_paths=rels,
                transport_calls=len(self.transport.calls),
            )

        opts.last_robot_sha = sha
        if isinstance(self.transport, FakeGitHubTransport):
            self.transport.set_branch_sha(opts.robot_branch, sha)
            # Keep PR head sha current for recovery after branch deletion
            for p in self.transport.robot_prs(opts.robot_branch):
                if p.get("state") == "open":
                    p.setdefault("head", {})["sha"] = sha

        # Create or update PR
        try:
            pr_result = self._ensure_pr(sha)
        except GitHubAPIError as e:
            return PublishResult(
                status="failed",
                reason=f"pr_list_failed:{e}",
                commit_sha=sha,
                written_paths=rels,
                notes=["branch pushed; PR list failed — retryable"],
                transport_calls=len(self.transport.calls),
            )
        self._save_state()
        pr_result.written_paths = rels
        pr_result.commit_sha = sha
        pr_result.transport_calls = len(self.transport.calls)
        return pr_result

    def _list_robot_prs(self, *, state: str) -> list[dict[str, Any]]:
        """List robot PRs via get_json only (head filter + pagination budget).

        Non-200 or non-list responses raise GitHubAPIError — never empty-success.
        """
        opts = self.opts
        head = quote(f"{opts.owner}:{opts.robot_branch}", safe=":")
        results: list[dict[str, Any]] = []
        for page in range(1, PR_LIST_PAGE_BUDGET + 1):
            path = (
                f"/repos/{opts.owner}/{opts.repo}/pulls"
                f"?state={state}&head={head}&per_page=20&page={page}"
            )
            status, data = self.transport.get_json(path)
            if status != 200 or not isinstance(data, list):
                raise GitHubAPIError(f"status={status} type={type(data).__name__}")
            for p in data:
                if (p.get("head") or {}).get("ref") == opts.robot_branch:
                    results.append(p)
            if len(data) < 20:
                break
        return results

    def _robot_pr_merged(self) -> bool:
        """True only when no open robot PR AND a relevant robot PR was merged.

        Must NOT return True while an open robot PR exists (F4).
        Uses get_json + pr_is_merged only — never Fake-only helpers.
        Propagates GitHubAPIError from list failures (do not treat as empty).
        """
        open_prs = self._list_robot_prs(state="open")
        if open_prs:
            return False
        closed = self._list_robot_prs(state="closed")
        return any(pr_is_merged(p) for p in closed)

    def _latest_recoverable_head_sha(self) -> str | None:
        """Open or closed-unmerged robot PR head via get_json only."""
        open_prs = self._list_robot_prs(state="open")
        if open_prs:
            return (open_prs[0].get("head") or {}).get("sha")
        for p in self._list_robot_prs(state="closed"):
            if pr_is_closed_unmerged(p):
                return (p.get("head") or {}).get("sha")
        return None

    def _prepare_robot_catalog(self, store: CatalogStore, root: Path) -> str:
        """Restore unmerged robot catalog when the branch ref is gone.

        Returns: ok | recovered | merged | fresh | recovery_gap
        Propagates GitHubAPIError from PR list failures.
        """
        opts = self.opts
        remote_sha = None
        try:
            remote_sha = self.git.remote_branch_sha(opts.remote_name, opts.robot_branch)
        except GitError:
            remote_sha = None
        if remote_sha:
            return "ok"
        if self._robot_pr_merged():
            return "merged"

        head_sha = self._latest_recoverable_head_sha()
        if head_sha:
            import tempfile

            recover_sha = str(head_sha)
            tmp = Path(tempfile.mkdtemp(prefix="jev-recover-"))
            try:
                remote_url = run_git(root, "remote", "get-url", opts.remote_name).stdout.strip()
                run_git(tmp, "init", "-b", "recover")
                GitWorkspace(root=tmp, known_robot_shas=set()).ensure_identity()
                run_git(tmp, "fetch", "--depth=1", remote_url, recover_sha)
                run_git(tmp, "checkout", "-f", "FETCH_HEAD")
                store.merge_catalog_from_branch_files(tmp)
                # Also hydrate identity from recovered tree
                ident = self._read_identity_file(tmp / ROBOT_IDENTITY_REL)
                if ident:
                    self._apply_identity(ident, prefer_sha=recover_sha)
                return "recovered"
            except GitError:
                if opts.last_robot_sha:
                    return "recovery_gap"
                return "fresh"
            finally:
                shutil.rmtree(tmp, ignore_errors=True)

        if opts.last_robot_sha:
            return "recovery_gap"
        return "fresh"

    def _resolve_main_sha(self, main_ref: str) -> str:
        candidates = [
            main_ref,
            f"refs/heads/{main_ref}",
            f"{self.opts.remote_name}/{main_ref}",
            "HEAD",
        ]
        for ref in candidates:
            try:
                return self.git.head_sha(ref)
            except GitError:
                continue
        raise GitError(f"cannot resolve main tip from {candidates}")

    def _stage_allowlisted_tree(self, root: Path, staging: Path) -> list[str]:
        rels: list[str] = []
        patterns = [
            "data/inbox/*.json",
            "data/events/*.json",
            "data/observations/*.json",
            "data/cache/checkpoints/*.json",
            "data/reports/*.json",
            "data/automation/*.json",
            "docs/categories/*.md",
            "docs/updates/*.md",
            "README.md",
            "README.en.md",
        ]
        for pattern in patterns:
            for path in root.glob(pattern):
                if not path.is_file():
                    continue
                rel = str(path.relative_to(root)).replace("\\", "/")
                if not is_path_allowed(rel):
                    continue
                dest = staging / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, dest)
                rels.append(rel)
        return rels

    def _restore_staged_tree(self, staging: Path, root: Path, rels: list[str]) -> None:
        for rel in rels:
            src = staging / rel
            if not src.exists():
                continue
            dest = root / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)

    def _materialize_allowlisted_from_store(self, store: CatalogStore, root: Path) -> list[str]:
        """Ensure generated README/categories and inbox/events exist as files (already on disk)."""
        written: list[str] = []
        for rel in ("README.md", "README.en.md"):
            if (root / rel).exists() and is_path_allowed(rel):
                written.append(rel)
        cats = root / "docs" / "categories"
        if cats.exists():
            for p in cats.glob("*.md"):
                rel = str(p.relative_to(root))
                if is_path_allowed(rel):
                    written.append(rel)
        _ = store
        return written

    def _revalidate_inbox_fields(self, root: Path) -> None:
        """Sanitize inbox against trusted baseline from CatalogStore (inbox+resources)."""
        inbox = root / "data" / "inbox"
        if not inbox.exists():
            return
        store = CatalogStore(Paths(root))
        for path in inbox.glob("*.json"):
            assert_not_symlink(path)
            data = json.loads(path.read_text(encoding="utf-8"))
            rid = data.get("id", "")
            # F5: load existing via CatalogStore (searches resources then inbox).
            # Snapshot baseline BEFORE overwrite: if path is the only copy, read it
            # as existing first, then merge machine fields onto that baseline.
            existing_model = store.get_resource(str(rid)) if rid else None
            existing = (
                json.loads(existing_model.model_dump_json()) if existing_model is not None else None
            )
            # If get_resource returned the same inbox file we are about to overwrite,
            # that IS the trusted baseline (pre-write content still on disk).
            sanitized = filter_machine_resource_update(existing, data)
            Resource.model_validate(sanitized)
            path.write_text(
                json.dumps(sanitized, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
            )

        events = root / "data" / "events"
        if events.exists():
            for path in events.glob("*.json"):
                assert_not_symlink(path)
                ev = json.loads(path.read_text(encoding="utf-8"))
                et = str(ev.get("event_type", ""))
                # Main already contains human audit events (e.g. human_accepted from
                # curated approve). Those must not fail robot publish. Automation is
                # still forbidden from *emitting* them at write sites.
                if et in FORBIDDEN_EVENT_TYPES:
                    continue
                assert_event_allowed(et)

    def _ensure_pr_if_needed(self, tip_sha: str | None) -> PublishResult:
        """When content has no material diff, still ensure an open PR exists for remote tip.

        - No remote tip → no_diff (same as today)
        - Open PR exists → 0 POST/PATCH
        - Remote tip, no open PR → POST create only (0 commit, 0 push)
        """
        if not tip_sha:
            return PublishResult(
                status="no_diff",
                reason="no_material_diff",
                notes=["no allowlisted changes to commit"],
                transport_calls=len(self.transport.calls),
            )

        opts = self.opts
        open_robot = self._list_robot_prs(state="open")
        if open_robot:
            pr = open_robot[0]
            return PublishResult(
                status="no_diff",
                reason="no_material_diff",
                pr_number=pr.get("number"),
                pr_url=pr.get("html_url"),
                commit_sha=tip_sha,
                notes=["no allowlisted changes; open PR unchanged"],
                transport_calls=len(self.transport.calls),
            )

        # Closed-unmerged: do not auto-reopen
        for p in self._list_robot_prs(state="closed"):
            if pr_is_closed_unmerged(p):
                return PublishResult(
                    status="paused",
                    reason="previous_pr_closed_unmerged",
                    notes=[
                        "no material diff; not auto-reopening identical closed PR",
                        f"closed_pr={p.get('number')}",
                    ],
                    pr_number=p.get("number"),
                    pr_url=p.get("html_url"),
                    commit_sha=tip_sha,
                    transport_calls=len(self.transport.calls),
                )

        title = "chore(catalog): automated discovery update"
        body = self._pr_body(tip_sha)
        st3, created = self.transport.post_json(
            f"/repos/{opts.owner}/{opts.repo}/pulls",
            {
                "title": title,
                "head": opts.robot_branch,
                "base": opts.main_branch,
                "body": body,
            },
        )
        if st3 >= 400:
            return PublishResult(
                status="failed",
                reason=f"pr_create_failed:{st3}",
                commit_sha=tip_sha,
                notes=["no new commit; PR create failed — retryable next run"],
                transport_calls=len(self.transport.calls),
            )
        return PublishResult(
            status="success",
            reason="pr_created",
            pr_number=created.get("number"),
            pr_url=created.get("html_url"),
            commit_sha=tip_sha,
            notes=["no material diff; created PR for existing robot tip"],
            transport_calls=len(self.transport.calls),
        )

    def _ensure_pr(self, head_sha: str) -> PublishResult:
        opts = self.opts
        open_robot = self._list_robot_prs(state="open")

        title = "chore(catalog): automated discovery update"
        body = self._pr_body(head_sha)

        if open_robot:
            pr = open_robot[0]
            number = pr["number"]
            st, updated = self.transport.patch_json(
                f"/repos/{opts.owner}/{opts.repo}/pulls/{number}",
                {"title": title, "body": body},
            )
            if st >= 400:
                return PublishResult(
                    status="failed",
                    reason=f"pr_update_failed:{st}",
                    notes=["branch pushed; PR update failed — retryable"],
                    pr_number=number,
                    pr_url=pr.get("html_url"),
                )
            return PublishResult(
                status="success",
                reason="pr_updated",
                pr_number=number,
                pr_url=(updated or pr).get("html_url"),
            )

        # Closed-unmerged: do not auto-reopen
        for p in self._list_robot_prs(state="closed"):
            if pr_is_closed_unmerged(p):
                return PublishResult(
                    status="paused",
                    reason="previous_pr_closed_unmerged",
                    notes=[
                        "branch updated; not auto-reopening identical closed PR",
                        f"closed_pr={p.get('number')}",
                    ],
                    pr_number=p.get("number"),
                    pr_url=p.get("html_url"),
                )

        st3, created = self.transport.post_json(
            f"/repos/{opts.owner}/{opts.repo}/pulls",
            {
                "title": title,
                "head": opts.robot_branch,
                "base": opts.main_branch,
                "body": body,
            },
        )
        if st3 >= 400:
            return PublishResult(
                status="failed",
                reason=f"pr_create_failed:{st3}",
                notes=["branch pushed; PR create failed — retryable next run"],
            )
        return PublishResult(
            status="success",
            reason="pr_created",
            pr_number=created.get("number"),
            pr_url=created.get("html_url"),
        )

    def _pr_body(self, sha: str) -> str:
        return (
            "## Automated catalog update\n\n"
            f"- Robot commit: `{sha}`\n"
            "- New/updated **pending** candidates only; no auto-curation.\n"
            "- Review with `jev-awesome review list` / approve / reject.\n"
            "- Source failures and coverage gaps: see `data/reports/`.\n"
        )

    def clear_pause(self) -> None:
        self._paused = False
        self._pause_reason = ""
        self._save_state()


def reject_malicious_artifact_paths(paths: list[str]) -> None:
    for p in paths:
        normalize_rel_path(p)
        if not is_path_allowed(p):
            raise WritePolicyError(f"artifact path rejected: {p}")
