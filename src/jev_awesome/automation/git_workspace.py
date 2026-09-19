"""Git workspace helpers for publisher. Tests use isolated temp remotes — never replace origin."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


class GitError(RuntimeError):
    pass


def run_git(cwd: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        text=True,
        capture_output=True,
    )
    if check and result.returncode != 0:
        raise GitError(
            f"git {' '.join(args)} failed ({result.returncode}): {result.stderr.strip()}"
        )
    return result


@dataclass
class GitWorkspace:
    root: Path
    robot_branch: str = "automation/catalog-update"
    main_branch: str = "main"
    robot_name: str = "jev-awesome-bot"
    robot_email: str = "bot@users.noreply.github.com"
    # Known SHAs produced by this bot in the current session / recorded state
    known_robot_shas: set[str] | None = None

    def ensure_identity(self) -> None:
        run_git(self.root, "config", "user.name", self.robot_name)
        run_git(self.root, "config", "user.email", self.robot_email)

    def head_sha(self, ref: str = "HEAD") -> str:
        return run_git(self.root, "rev-parse", ref).stdout.strip()

    def branch_exists(self, name: str) -> bool:
        r = run_git(self.root, "show-ref", "--verify", f"refs/heads/{name}", check=False)
        return r.returncode == 0

    def remote_branch_sha(self, remote: str, branch: str) -> str | None:
        r = run_git(self.root, "ls-remote", remote, f"refs/heads/{branch}", check=False)
        line = r.stdout.strip().splitlines()
        if not line:
            return None
        return line[0].split()[0]

    def checkout_new_branch_from(self, branch: str, start_point: str) -> None:
        # Force is required because allowlisted catalog files were already
        # staged out of the worktree; we restore them after the switch.
        if self.branch_exists(branch):
            run_git(self.root, "checkout", "-f", branch)
            run_git(self.root, "reset", "--hard", start_point)
        else:
            run_git(self.root, "checkout", "-f", "-B", branch, start_point)
        # Drop leftover untracked allowlisted files that would shadow restore
        run_git(self.root, "clean", "-fd", "--", "data/inbox", "data/events", "data/reports")

    def status_porcelain(self) -> str:
        return run_git(self.root, "status", "--porcelain").stdout

    def diff_names(self, base: str, head: str = "HEAD") -> list[str]:
        out = run_git(self.root, "diff", "--name-status", f"{base}...{head}").stdout
        names: list[str] = []
        for line in out.splitlines():
            if not line.strip():
                continue
            # status\tpath or R100\told\tnew
            parts = line.split("\t")
            if parts[0].startswith("R") or parts[0].startswith("C"):
                names.append(parts[-1])
            else:
                names.append(parts[-1] if len(parts) > 1 else parts[0])
        return names

    def add_paths(self, paths: list[str]) -> None:
        if not paths:
            return
        run_git(self.root, "add", "--", *paths)

    def commit(self, message: str) -> str | None:
        if not self.status_porcelain().strip():
            return None
        run_git(self.root, "commit", "-m", message)
        sha = self.head_sha()
        if self.known_robot_shas is not None:
            self.known_robot_shas.add(sha)
        return sha

    def push(self, remote: str, branch: str, *, force: bool = False) -> None:
        if force:
            raise GitError("force push is forbidden")
        run_git(self.root, "push", remote, f"HEAD:{branch}")

    def fetch(self, remote: str) -> None:
        run_git(self.root, "fetch", remote)

    def manual_edits_suspected(
        self,
        *,
        branch: str,
        expected_robot_sha: str | None,
        remote_sha: str | None,
        dirty_paths_outside_allowlist: list[str],
    ) -> tuple[bool, str]:
        """Detect human edits without trusting author identity alone."""
        if dirty_paths_outside_allowlist:
            return True, "worktree_has_disallowed_paths"
        if expected_robot_sha and remote_sha and remote_sha != expected_robot_sha:
            # Remote advanced differently than last known robot commit
            if self.known_robot_shas is not None and remote_sha not in self.known_robot_shas:
                return True, "remote_sha_not_in_known_robot_commits"
            # If we don't have a known set, compare commit subject / tree carefully
            return True, "remote_sha_diverged_from_expected"
        _ = branch
        return False, ""


def init_bare_remote(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    run_git(path, "init", "--bare", "-b", "main")
    return path


def clone_from_bare(bare: Path, work: Path, branch: str = "main") -> GitWorkspace:
    work.parent.mkdir(parents=True, exist_ok=True)
    run_git(work.parent, "clone", "-b", branch, str(bare), work.name)
    ws = GitWorkspace(root=work, main_branch=branch, known_robot_shas=set())
    ws.ensure_identity()
    return ws


def seed_main_repo(work: Path, files: dict[str, str]) -> str:
    """Initialize a non-bare repo with initial commit (for tests)."""
    run_git(work, "init", "-b", "main")
    ws = GitWorkspace(root=work, known_robot_shas=set())
    ws.ensure_identity()
    for rel, content in files.items():
        p = work / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    run_git(work, "add", "-A")
    run_git(work, "commit", "-m", "seed main")
    return ws.head_sha()
