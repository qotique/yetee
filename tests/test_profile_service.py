from __future__ import annotations

import pytest


@pytest.fixture
def profiles_dir(tmp_path):
    """Direct structure: profiles/MOD/*.json."""
    mod = tmp_path / "MOD"
    mod.mkdir()
    (mod / "config.json").write_text("{}")
    (mod / "settings.json").write_text("{}")
    return tmp_path


def test_scan_profiles_direct_structure(profiles_dir):
    from services.profile_service import ProfileService

    svc = ProfileService()
    entities = svc.scan_profiles(str(profiles_dir))
    assert "MOD" in entities
    assert set(entities["MOD"].keys()) == {"config.json", "settings.json"}
    assert entities["MOD"]["config.json"].endswith("config.json")


def test_scan_profiles_nested_structure(tmp_path):
    """Nested structure: profiles/AUTHOR/MOD/*.json."""
    from services.profile_service import ProfileService

    for mod in ("A", "B"):
        d = tmp_path / "AUTHOR" / mod
        d.mkdir(parents=True)
        (d / f"{mod}.json").write_text("{}")

    svc = ProfileService()
    entities = svc.scan_profiles(str(tmp_path))
    assert "AUTHOR" in entities
    assert set(entities["AUTHOR"].keys()) == {"A/A.json", "B/B.json"}


def test_scan_profiles_mixed_structure(tmp_path):
    """Files of one mod scattered across subdirectories keep relative keys."""
    from services.profile_service import ProfileService

    base = tmp_path / "MOD"
    (base / "sub1").mkdir(parents=True)
    (base / "sub2").mkdir(parents=True)
    (base / "sub2" / "deep").mkdir(parents=True)
    (base / "a.json").write_text("{}")
    (base / "sub1" / "b.json").write_text("{}")
    (base / "sub2" / "c.json").write_text("{}")
    (base / "sub2" / "deep" / "d.json").write_text("{}")

    svc = ProfileService()
    entities = svc.scan_profiles(str(tmp_path))
    assert set(entities["MOD"].keys()) == {
        "a.json",
        "sub1/b.json",
        "sub2/c.json",
        "sub2/deep/d.json",
    }


def test_scan_profiles_gathers_xml_json_txt(tmp_path):
    """All supported extensions gathered; others ignored."""
    from services.profile_service import ProfileService

    d = tmp_path / "MOD"
    d.mkdir()
    (d / "a.xml").write_text("<a/>")
    (d / "b.json").write_text("{}")
    (d / "c.txt").write_text("x")
    (d / "readme.md").write_text("ignored")
    (d / "data.bin").write_bytes(b"\x00")

    svc = ProfileService()
    entities = svc.scan_profiles(str(tmp_path))
    assert set(entities["MOD"].keys()) == {"a.xml", "b.json", "c.txt"}


def test_scan_profiles_hidden_entries_skipped(tmp_path):
    from services.profile_service import ProfileService

    d = tmp_path / "MOD"
    d.mkdir()
    (d / "a.json").write_text("{}")
    (tmp_path / ".hidden").mkdir()
    (tmp_path / ".hidden" / "h.json").write_text("{}")

    svc = ProfileService()
    entities = svc.scan_profiles(str(tmp_path))
    assert set(entities.keys()) == {"MOD"}


def test_scan_profiles_empty_dir_skipped(tmp_path):
    from services.profile_service import ProfileService

    (tmp_path / "Empty").mkdir()

    svc = ProfileService()
    entities = svc.scan_profiles(str(tmp_path))
    assert entities == {}


def test_scan_profiles_dir_does_not_exist(tmp_path):
    from services.profile_service import ProfileService

    svc = ProfileService()
    assert svc.scan_profiles(str(tmp_path / "nope")) == {}


def test_scan_profiles_empty_string(tmp_path):
    from services.profile_service import ProfileService

    svc = ProfileService()
    assert svc.scan_profiles("") == {}


def test_scan_profiles_sorted_output(tmp_path):
    """Directory listing order does not affect result."""
    from services.profile_service import ProfileService

    base = tmp_path / "MOD"
    base.mkdir()
    for name in ("z.json", "a.json", "m.json"):
        (base / name).write_text("{}")

    svc = ProfileService()
    assert list(svc.scan_profiles(str(tmp_path))["MOD"].keys()) == [
        "a.json",
        "m.json",
        "z.json",
    ]


def test_collect_entity_files_gathers_files(tmp_path):
    from services.profile_service import ProfileService

    (tmp_path / "sub").mkdir()
    (tmp_path / "a.json").write_text("{}")
    (tmp_path / "sub" / "b.txt").write_text("x")

    svc = ProfileService()
    files = svc.collect_entity_files(str(tmp_path))
    assert set(files.keys()) == {"a.json", "sub/b.txt"}
    assert files["a.json"] == str(tmp_path / "a.json")


def test_collect_entity_files_ignores_unsupported(tmp_path):
    from services.profile_service import ProfileService

    (tmp_path / "a.json").write_text("{}")
    (tmp_path / "readme.md").write_text("ignored")

    svc = ProfileService()
    assert svc.collect_entity_files(str(tmp_path)) == {
        "a.json": str(tmp_path / "a.json")
    }


def test_collect_entity_files_skips_hidden(tmp_path):
    from services.profile_service import ProfileService

    (tmp_path / ".hidden.json").write_text("{}")
    (tmp_path / "ok.json").write_text("{}")

    svc = ProfileService()
    assert set(svc.collect_entity_files(str(tmp_path)).keys()) == {"ok.json"}


def test_collect_entity_files_missing_dir(tmp_path):
    from services.profile_service import ProfileService

    svc = ProfileService()
    assert svc.collect_entity_files(str(tmp_path / "nope")) == {}
    assert svc.collect_entity_files("") == {}
