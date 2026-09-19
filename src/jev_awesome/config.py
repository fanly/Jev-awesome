from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from jev_awesome.paths import Paths
from jev_awesome.store import load_yaml


@dataclass
class RuntimeConfig:
    timezone: str = "Asia/Shanghai"
    collector_enabled: bool = False
    auto_pr_enabled: bool = False
    pages_enabled: bool = False
    classifier_mode: str = "rules"
    typesafe_max_requests: int = 50
    github_token_env: str = "GITHUB_TOKEN"
    dry_run_default: bool = True
    robot_branch: str = "automation/catalog-update"
    expected_repo: str = "fanly/Jev-awesome"
    site_base_path: str = "/Jev-awesome/"
    request_timeout_seconds: float = 30.0
    max_response_bytes: int = 2_000_000
    max_redirects: int = 5


@dataclass
class AppConfig:
    sources: dict[str, Any] = field(default_factory=dict)
    policy: dict[str, Any] = field(default_factory=dict)
    runtime: RuntimeConfig = field(default_factory=RuntimeConfig)
    paths: Paths = field(default_factory=Paths)

    @classmethod
    def load(cls, root: Path | None = None) -> AppConfig:
        paths = Paths(root) if root else Paths()
        sources = load_yaml(paths.config / "sources.yaml") if (paths.config / "sources.yaml").exists() else {}
        policy = load_yaml(paths.config / "policy.yaml") if (paths.config / "policy.yaml").exists() else {}
        raw_runtime = (
            load_yaml(paths.config / "runtime.yaml")
            if (paths.config / "runtime.yaml").exists()
            else {}
        )
        runtime = RuntimeConfig(
            **{k: v for k, v in raw_runtime.items() if k in RuntimeConfig.__dataclass_fields__}
        )
        return cls(sources=sources, policy=policy, runtime=runtime, paths=paths)
