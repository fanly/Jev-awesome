"""Production catalog publisher: validate → commit robot branch → create/update PR.

Default remote writes remain gated by AUTO_PR_ENABLED / explicit opts.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from jev_awesome.automation.git_workspace import GitError, GitWorkspace, run_git
from jev_awesome.automation.github_transport import FakeGitHubTransport, GitHubTransport
from jev_awesome.automation.write_policy import (
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
        self.state_path = state_path or (workspace / "data" / "cache" / "publisher_state.json")
        self._load_state()

    def _load_state(self) -> None:
        if self.state_path.exists():
            data = json.loads(self.state_path.read_text(encoding="utf-8"))
            self.opts.last_robot_sha = data.get("last_robot_sha") or self.opts.last_robot_sha
            shas = data.get("known_robot_shas") or []
            self.git.known_robot_shas = set(shas)
            if data.get("paused"):
                self._paused = True
                self._pause_reason = data.get("pause_reason", "paused")
            else:
                self._paused = False
                self._pause_reason = ""
        else:
            self._paused = False
            self._pause_reason = ""

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

        recovery = self._prepare_robot_catalog(store, root)
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
        restart_after_merge = False
        if self._robot_pr_merged():
            restart_after_merge = True
            remote_sha = None
            opts.last_robot_sha = None

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
            return PublishResult(
                status="no_diff",
                reason="no_material_diff",
                notes=["no allowlisted changes to commit"],
                transport_calls=len(self.transport.calls),
            )

        try:
            validate_write_set(rels, sizes=sizes)
        except WritePolicyError as e:
            return PublishResult(status="failed", reason=str(e))

        self.git.add_paths(rels)
        sha = self.git.commit(f"chore(catalog): automation update {utc_now().strftime('%Y-%m-%d')}")
        if sha is None:
            return PublishResult(status="no_diff", reason="empty_commit_skipped")

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
        pr_result = self._ensure_pr(sha)
        self._save_state()
        pr_result.written_paths = rels
        pr_result.commit_sha = sha
        pr_result.transport_calls = len(self.transport.calls)
        return pr_result

    def _robot_pr_merged(self) -> bool:
        opts = self.opts
        has = getattr(self.transport, "has_merged_robot_pr", None)
        if callable(has):
            return bool(has(opts.robot_branch))
        status, data = self.transport.get_json(
            f"/repos/{opts.owner}/{opts.repo}/pulls?state=closed&per_page=20"
        )
        if status != 200 or not isinstance(data, list):
            return False
        return any(
            (p.get("head") or {}).get("ref") == opts.robot_branch and p.get("merged") for p in data
        )

    def _prepare_robot_catalog(self, store: CatalogStore, root: Path) -> str:
        """Restore unmerged robot catalog when the branch ref is gone.

        Returns: ok | recovered | merged | fresh | recovery_gap
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

        head_sha = None
        getter = getattr(self.transport, "latest_unmerged_head_sha", None)
        if callable(getter):
            head_sha = getter(opts.robot_branch)
        if not head_sha:
            # Probe closed-unmerged via HTTP API shape
            st, closed = self.transport.get_json(
                f"/repos/{opts.owner}/{opts.repo}/pulls?state=closed&per_page=20"
            )
            if st == 200 and isinstance(closed, list):
                for p in closed:
                    if (p.get("head") or {}).get("ref") == opts.robot_branch and not p.get(
                        "merged"
                    ):
                        head_sha = (p.get("head") or {}).get("sha")
                        break
            st2, opened = self.transport.get_json(
                f"/repos/{opts.owner}/{opts.repo}/pulls?state=open&per_page=20"
            )
            if not head_sha and st2 == 200 and isinstance(opened, list):
                for p in opened:
                    if (p.get("head") or {}).get("ref") == opts.robot_branch:
                        head_sha = (p.get("head") or {}).get("sha")
                        break

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
        inbox = root / "data" / "inbox"
        if not inbox.exists():
            return
        for path in inbox.glob("*.json"):
            assert_not_symlink(path)
            data = json.loads(path.read_text(encoding="utf-8"))
            # Load existing from resources if any
            rid = data.get("id", "")
            existing = None
            res_path = (
                root / "data" / "resources" / f"{rid.replace(':', '_').replace('/', '_')}.json"
            )
            if res_path.exists():
                existing = json.loads(res_path.read_text(encoding="utf-8"))
            sanitized = filter_machine_resource_update(existing, data)
            # Validate via model
            Resource.model_validate(sanitized)
            path.write_text(
                json.dumps(sanitized, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
            )

        events = root / "data" / "events"
        if events.exists():
            for path in events.glob("*.json"):
                assert_not_symlink(path)
                ev = json.loads(path.read_text(encoding="utf-8"))
                assert_event_allowed(ev.get("event_type", ""))

    def _ensure_pr(self, head_sha: str) -> PublishResult:
        opts = self.opts
        # List open PRs for this branch
        status, data = self.transport.get_json(
            f"/repos/{opts.owner}/{opts.repo}/pulls?state=open&per_page=20"
        )
        open_robot = []
        if status == 200 and isinstance(data, list):
            for p in data:
                head = (p.get("head") or {}).get("ref")
                if head == opts.robot_branch:
                    open_robot.append(p)

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
        st2, closed = self.transport.get_json(
            f"/repos/{opts.owner}/{opts.repo}/pulls?state=closed&per_page=20"
        )
        if st2 == 200 and isinstance(closed, list):
            for p in closed:
                head = (p.get("head") or {}).get("ref")
                if head == opts.robot_branch and not p.get("merged"):
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
