from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import types
from pathlib import Path


def _load_modules():
    repo_root = Path(__file__).resolve().parent.parent
    pkg_name = "ajpc_tools_dev_pkg"

    pkg = types.ModuleType(pkg_name)
    pkg.__path__ = [str(repo_root)]  # type: ignore[attr-defined]
    sys.modules[pkg_name] = pkg

    cfg_spec = importlib.util.spec_from_file_location(
        f"{pkg_name}.config",
        repo_root / "config.py",
    )
    if cfg_spec is None or cfg_spec.loader is None:
        raise RuntimeError("failed to load config.py spec")
    config_mod = importlib.util.module_from_spec(cfg_spec)
    sys.modules[cfg_spec.name] = config_mod
    cfg_spec.loader.exec_module(config_mod)

    mig_spec = importlib.util.spec_from_file_location(
        f"{pkg_name}.config_migrations",
        repo_root / "config_migrations.py",
    )
    if mig_spec is None or mig_spec.loader is None:
        raise RuntimeError("failed to load config_migrations.py spec")
    mig_mod = importlib.util.module_from_spec(mig_spec)
    sys.modules[mig_spec.name] = mig_mod
    mig_spec.loader.exec_module(mig_mod)
    return config_mod, mig_mod


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _assert(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)


def _test_legacy_key_migration(config_mod, mig_mod) -> None:
    with tempfile.TemporaryDirectory() as td:
        cfg_path = Path(td) / "config.json"
        payload = {
            "note_linker": {
                "enabled": False,
                "copy_label_field": "FromNoteLinker",
                "rules": {
                    "111": {"a": 1},
                },
            },
            "mass_linker": {
                "copy_label_field": "LegacyMassCopy",
                "rules": {
                    "222": {"b": 2},
                },
            },
            "stability": {"foo": "bar"},
        }
        _write_json(cfg_path, payload)
        config_mod.CONFIG_PATH = str(cfg_path)

        changed = mig_mod.migrate_legacy_keys()
        _assert(changed is True, "expected legacy migration to change config")

        out = _read_json(cfg_path)
        _assert("note_linker" not in out, "note_linker must be removed")
        _assert("stability" not in out, "stability block must be removed")

        mass = out.get("mass_linker") or {}
        _assert(mass.get("enabled") is False, "mass_linker.enabled must be migrated from note_linker")
        _assert(
            mass.get("label_field") == "FromNoteLinker",
            "mass_linker.label_field must prefer migrated note_linker copy_label_field",
        )
        _assert("copy_label_field" not in mass, "mass_linker.copy_label_field must be removed")
        rules = mass.get("rules") or {}
        _assert("111" in rules and "222" in rules, "mass_linker.rules must merge legacy and existing rules")


def _test_example_key_migration(config_mod, mig_mod) -> None:
    with tempfile.TemporaryDirectory() as td:
        cfg_path = Path(td) / "config.json"
        payload = {
            "example_gate": {
                "example_key_field": "ExampleKey",
                "vocab_key_field": "VocabKey",
            }
        }
        _write_json(cfg_path, payload)
        config_mod.CONFIG_PATH = str(cfg_path)

        changed = mig_mod.migrate_legacy_keys()
        _assert(changed is True, "expected example key migration to change config")

        out = _read_json(cfg_path)
        ex = out.get("example_gate") or {}
        _assert(ex.get("key_field") == "ExampleKey", "example_gate.key_field must be canonicalized")
        _assert("example_key_field" not in ex, "example_gate.example_key_field must be removed")
        _assert("vocab_key_field" not in ex, "example_gate.vocab_key_field must be removed")


def _test_non_anki_fallbacks(mig_mod) -> None:
    r1 = mig_mod.migrate_note_type_names_to_ids()
    r2 = mig_mod.migrate_template_names_to_ords()
    _assert(r1 is False, "migrate_note_type_names_to_ids must return False without Anki runtime")
    _assert(r2 is False, "migrate_template_names_to_ords must return False without Anki runtime")


def _test_config_core_is_agnostic(config_mod) -> None:
    disallowed = [
        "FAMILY_PRIORITY_ENABLED",
        "CARD_STAGES_ENABLED",
        "EXAMPLE_GATE_ENABLED",
        "KANJI_GATE_ENABLED",
        "MASS_LINKER_ENABLED",
    ]
    for key in disallowed:
        _assert(not hasattr(config_mod, key), f"config.py must not expose module-specific key: {key}")


def main() -> int:
    config_mod, mig_mod = _load_modules()
    _test_legacy_key_migration(config_mod, mig_mod)
    _test_example_key_migration(config_mod, mig_mod)
    _test_non_anki_fallbacks(mig_mod)
    _test_config_core_is_agnostic(config_mod)
    print("OK check_config_migrations")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
