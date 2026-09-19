from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class PrLifecycle(StrEnum):
    NONE = "none"
    OPEN = "open"
    MERGED = "merged"
    CLOSED = "closed"
    BRANCH_DELETED = "branch_deleted"
    PAUSED_MANUAL_EDITS = "paused_manual_edits"


@dataclass
class RobotPrState:
    branch: str = "automation/catalog-update"
    lifecycle: PrLifecycle = PrLifecycle.NONE
    pr_number: int | None = None
    pr_url: str | None = None
    head_sha: str | None = None
    manual_edits_detected: bool = False
    last_run_id: str | None = None
    pending_write_path: str | None = None
    notes: list[str] = field(default_factory=list)


@dataclass
class FakePull:
    number: int
    state: str  # open, closed
    merged: bool
    head_ref: str
    head_sha: str
    html_url: str
    user_login: str = "github-actions[bot]"


class FakeGitHub:
    """In-memory GitHub for PR state-machine tests (not a live API)."""

    def __init__(self) -> None:
        self.branches: dict[str, str] = {}  # name -> sha
        self.pulls: list[FakePull] = []
        self.manual_files_on_branch: set[str] = set()
        self.actions: list[str] = []

    def get_open_robot_pr(self, branch: str) -> FakePull | None:
        for p in self.pulls:
            if p.head_ref == branch and p.state == "open" and not p.merged:
                return p
        return None

    def create_or_update_pr(
        self,
        *,
        branch: str,
        title: str,
        body: str,
        has_diff: bool,
        branch_has_manual_edits: bool,
        state: RobotPrState,
    ) -> RobotPrState:
        _ = (title, body)
        if branch_has_manual_edits or state.manual_edits_detected:
            state.lifecycle = PrLifecycle.PAUSED_MANUAL_EDITS
            state.manual_edits_detected = True
            state.notes.append("paused: manual edits on robot branch")
            state.pending_write_path = "data/reports/pending-robot-write.json"
            self.actions.append("pause")
            return state

        if not has_diff:
            self.actions.append("no_diff")
            state.notes.append("no material diff; skip commit/PR")
            return state

        existing = self.get_open_robot_pr(branch)
        if existing:
            # Update same PR — do not open another
            existing.head_sha = f"sha-{len(self.actions) + 1}"
            self.branches[branch] = existing.head_sha
            state.lifecycle = PrLifecycle.OPEN
            state.pr_number = existing.number
            state.pr_url = existing.html_url
            state.head_sha = existing.head_sha
            self.actions.append("update_pr")
            return state

        # If last PR was closed without merge, do not harass by reopening identical
        closed = [
            p for p in self.pulls if p.head_ref == branch and p.state == "closed" and not p.merged
        ]
        if closed and state.lifecycle == PrLifecycle.CLOSED:
            state.notes.append("previous PR closed unmerged; pause reopen")
            self.actions.append("skip_reopen")
            return state

        number = len(self.pulls) + 1
        sha = f"sha-{number}"
        pull = FakePull(
            number=number,
            state="open",
            merged=False,
            head_ref=branch,
            head_sha=sha,
            html_url=f"https://github.com/fanly/Jev-awesome/pull/{number}",
        )
        self.pulls.append(pull)
        self.branches[branch] = sha
        state.lifecycle = PrLifecycle.OPEN
        state.pr_number = number
        state.pr_url = pull.html_url
        state.head_sha = sha
        self.actions.append("create_pr")
        return state

    def on_merged(self, state: RobotPrState) -> RobotPrState:
        for p in self.pulls:
            if p.number == state.pr_number:
                p.merged = True
                p.state = "closed"
        state.lifecycle = PrLifecycle.MERGED
        state.notes.append("merged; next run starts from main + history")
        self.actions.append("merged")
        return state

    def on_closed(self, state: RobotPrState) -> RobotPrState:
        for p in self.pulls:
            if p.number == state.pr_number:
                p.state = "closed"
                p.merged = False
        state.lifecycle = PrLifecycle.CLOSED
        state.notes.append("closed without merge; do not auto-reopen identical PR")
        self.actions.append("closed")
        return state

    def on_branch_deleted(self, state: RobotPrState) -> RobotPrState:
        self.branches.pop(state.branch, None)
        state.lifecycle = PrLifecycle.BRANCH_DELETED
        state.head_sha = None
        state.notes.append("branch deleted; recreate on next material run")
        self.actions.append("branch_deleted")
        return state


def merge_inbox_rounds(rounds: list[list[dict[str, Any]]]) -> dict[str, dict[str, Any]]:
    """Simulate three unmerged collect rounds retaining all candidates."""
    catalog: dict[str, dict[str, Any]] = {}
    for round_items in rounds:
        for item in round_items:
            rid = item["id"]
            if rid not in catalog:
                catalog[rid] = dict(item)
            else:
                # Keep earliest discovered_at
                if item.get("first_discovered_at", "") < catalog[rid].get(
                    "first_discovered_at", ""
                ):
                    catalog[rid]["first_discovered_at"] = item["first_discovered_at"]
                catalog[rid]["last_seen_round"] = item.get("round")
    return catalog
