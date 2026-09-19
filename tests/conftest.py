from __future__ import annotations

from pathlib import Path

import pytest

from jev_awesome.paths import Paths
from jev_awesome.store import CatalogStore


@pytest.fixture
def tmp_paths(tmp_path: Path) -> Paths:
    (tmp_path / "config").mkdir()
    (tmp_path / "templates").mkdir()
    (tmp_path / "pyproject.toml").write_text("[project]\nname='t'\n", encoding="utf-8")
    (tmp_path / "src" / "jev_awesome").mkdir(parents=True)
    paths = Paths(tmp_path)
    paths.ensure_data_dirs()
    (paths.templates / "README.md.j2").write_text(
        "{{ generated_start }}\ncurated={{ curated|length }}\n{{ generated_end }}\n",
        encoding="utf-8",
    )
    (paths.templates / "README.en.md.j2").write_text(
        "{{ generated_start }}\nen={{ curated|length }}\n{{ generated_end }}\n",
        encoding="utf-8",
    )
    (paths.templates / "category.md.j2").write_text(
        "{{ generated_start }}\n{{ meta.slug }}:{{ items|length }}\n{{ generated_end }}\n",
        encoding="utf-8",
    )
    return paths


@pytest.fixture
def store(tmp_paths: Paths) -> CatalogStore:
    return CatalogStore(tmp_paths)
