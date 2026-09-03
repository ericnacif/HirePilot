"""Testes de migração de pasta de dados legada."""

from __future__ import annotations

import sys

from cv_apply.config import _migrate_legacy_data


def test_migrate_legacy_data_moves_tree(tmp_path):
    old = tmp_path / "VagaMatch"
    data = old / "data"
    data.mkdir(parents=True)
    (data / "profile.json").write_text('{"name":"Ana"}', encoding="utf-8")

    new = tmp_path / "Vaga em Vista"
    _migrate_legacy_data(new, legacy_bases=[old])

    assert (new / "data" / "profile.json").read_text(encoding="utf-8") == '{"name":"Ana"}'
    assert (new / ".migrated_from_legacy").read_text(encoding="utf-8") == str(old)
    assert not old.exists()


def test_migrate_legacy_data_skips_when_marker_exists(tmp_path):
    old = tmp_path / "VagaMatch"
    old.mkdir()
    (old / "keep.txt").write_text("x", encoding="utf-8")
    new = tmp_path / "Vaga em Vista"
    new.mkdir()
    (new / ".migrated_from_legacy").write_text("done", encoding="utf-8")

    _migrate_legacy_data(new, legacy_bases=[old])

    assert (old / "keep.txt").exists()
    assert not (new / "keep.txt").exists()


def test_migrate_legacy_data_does_not_overwrite_existing(tmp_path):
    old = tmp_path / "VagaMatch"
    (old / "data").mkdir(parents=True)
    (old / "data" / "x.txt").write_text("old", encoding="utf-8")

    new = tmp_path / "Vaga em Vista"
    (new / "data").mkdir(parents=True)
    (new / "data" / "x.txt").write_text("new", encoding="utf-8")

    _migrate_legacy_data(new, legacy_bases=[old])

    assert (new / "data" / "x.txt").read_text(encoding="utf-8") == "new"
    assert (old / "data" / "x.txt").read_text(encoding="utf-8") == "old"


def test_user_writable_base_windows(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

    from cv_apply.config import _user_writable_base

    assert _user_writable_base() == tmp_path / "Vaga em Vista"


def test_migrate_hirepilot_data_to_new_brand(tmp_path):
    old = tmp_path / "HirePilot"
    (old / "data").mkdir(parents=True)
    (old / "data" / "jobs.db").write_text("legacy", encoding="utf-8")

    new = tmp_path / "Vaga em Vista"
    _migrate_legacy_data(new, legacy_bases=[old])

    assert (new / "data" / "jobs.db").read_text(encoding="utf-8") == "legacy"
    assert not old.exists()
