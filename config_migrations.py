from __future__ import annotations

import json
from typing import Any

from . import config

def migrate_legacy_keys() -> bool:
    cfg = config._load_config()
    if not isinstance(cfg, dict):
        return False

    changed = False

    legacy_linker = cfg.get("note_linker")
    if isinstance(legacy_linker, dict):
        cur_mass = cfg.get("mass_linker")
        mass: dict[str, Any] = dict(cur_mass) if isinstance(cur_mass, dict) else {}

        if "enabled" not in mass and "enabled" in legacy_linker:
            mass["enabled"] = bool(legacy_linker.get("enabled"))
            changed = True
        if "label_field" not in mass and "copy_label_field" in legacy_linker:
            mass["label_field"] = str(legacy_linker.get("copy_label_field") or "").strip()
            changed = True

        legacy_rules = legacy_linker.get("rules")
        if isinstance(legacy_rules, dict):
            mass_rules = mass.get("rules")
            mass_rules_out: dict[str, Any] = (
                dict(mass_rules) if isinstance(mass_rules, dict) else {}
            )
            for nt_id, rule in legacy_rules.items():
                key = str(nt_id)
                if key not in mass_rules_out:
                    mass_rules_out[key] = rule
                    changed = True
            mass["rules"] = mass_rules_out

        if cfg.get("mass_linker") != mass:
            cfg["mass_linker"] = mass
            changed = True

        if "note_linker" in cfg:
            del cfg["note_linker"]
            changed = True

    mass_linker = cfg.get("mass_linker")
    if isinstance(mass_linker, dict):
        mass_out = dict(mass_linker)
        if "label_field" not in mass_out and "copy_label_field" in mass_out:
            mass_out["label_field"] = str(mass_out.get("copy_label_field") or "").strip()
            changed = True
        if "copy_label_field" in mass_out:
            del mass_out["copy_label_field"]
            changed = True
        if mass_out != mass_linker:
            cfg["mass_linker"] = mass_out
            changed = True

    family = cfg.get("family_gate")
    card_stages = cfg.get("card_stages")
    card_stages_out: dict[str, Any] = dict(card_stages) if isinstance(card_stages, dict) else {}

    if "enabled" not in card_stages_out:
        card_stages_out["enabled"] = True
        changed = True
    if "run_on_sync" not in card_stages_out:
        card_stages_out["run_on_sync"] = True
        changed = True
    if "note_types" not in card_stages_out:
        card_stages_out["note_types"] = {}
        changed = True

    if isinstance(family, dict):
        family_out = dict(family)
        if "link_css_selector" in family_out:
            del family_out["link_css_selector"]
            changed = True

        fam_note_types = family_out.get("note_types")
        if isinstance(fam_note_types, dict):
            has_stage_payload = any(
                isinstance(v, dict) and isinstance(v.get("stages"), list)
                for v in fam_note_types.values()
            )
            if has_stage_payload and not isinstance(card_stages_out.get("note_types"), dict):
                card_stages_out["note_types"] = dict(fam_note_types)
                changed = True
            elif has_stage_payload and not card_stages_out.get("note_types"):
                card_stages_out["note_types"] = dict(fam_note_types)
                changed = True

            fam_note_types_out: dict[str, Any] = {}
            for nt_id in fam_note_types.keys():
                sid = str(nt_id).strip()
                if sid:
                    fam_note_types_out[sid] = {}
            if fam_note_types_out != fam_note_types:
                family_out["note_types"] = fam_note_types_out
                changed = True

        if family_out != family:
            cfg["family_gate"] = family_out
            changed = True

    if not isinstance(cfg.get("card_stages"), dict) or cfg.get("card_stages") != card_stages_out:
        cfg["card_stages"] = card_stages_out
        changed = True

    example = cfg.get("example_gate")
    if isinstance(example, dict):
        ex_out = dict(example)
        key_field = str(
            ex_out.get(
                "key_field",
                ex_out.get("example_key_field", ex_out.get("vocab_key_field", "Vocab")),
            )
            or "Vocab"
        ).strip()
        if not key_field:
            key_field = "Vocab"
        if ex_out.get("key_field") != key_field:
            ex_out["key_field"] = key_field
            changed = True
        if "vocab_key_field" in ex_out:
            del ex_out["vocab_key_field"]
            changed = True
        if "example_key_field" in ex_out:
            del ex_out["example_key_field"]
            changed = True
        if ex_out != example:
            cfg["example_gate"] = ex_out
            changed = True

    kanji = cfg.get("kanji_gate")
    if isinstance(kanji, dict):
        kg_out = dict(kanji)
        if "kanji_fields" not in kg_out:
            fields: list[str] = []
            first = str(kg_out.get("kanji_field") or "").strip()
            second = str(kg_out.get("kanji_alt_field") or "").strip()
            if first:
                fields.append(first)
            if second and second not in fields:
                fields.append(second)
            kg_out["kanji_fields"] = fields
            changed = True
        if "kanji_field" in kg_out:
            del kg_out["kanji_field"]
            changed = True
        if "kanji_alt_field" in kg_out:
            del kg_out["kanji_alt_field"]
            changed = True
        if "stability_aggregation" in kg_out:
            del kg_out["stability_aggregation"]
            changed = True
        if "component_threshold" in kg_out:
            del kg_out["component_threshold"]
            changed = True
        if kg_out != kanji:
            cfg["kanji_gate"] = kg_out
            changed = True

    card_sorter = cfg.get("card_sorter")
    if isinstance(card_sorter, dict):
        cs_out = dict(card_sorter)
        if "run_on_sync" not in cs_out:
            start = bool(cs_out.get("run_on_sync_start", True))
            finish = bool(cs_out.get("run_on_sync_finish", True))
            cs_out["run_on_sync"] = bool(start or finish)
            changed = True
        if "run_on_sync_start" in cs_out:
            del cs_out["run_on_sync_start"]
            changed = True
        if "run_on_sync_finish" in cs_out:
            del cs_out["run_on_sync_finish"]
            changed = True
        note_types = cs_out.get("note_types")
        if isinstance(note_types, dict):
            nts_out: dict[str, Any] = {}
            for nt_id, nt_cfg in note_types.items():
                if not isinstance(nt_cfg, dict):
                    nts_out[str(nt_id)] = nt_cfg
                    continue
                nt_out = dict(nt_cfg)
                if str(nt_out.get("mode", "by_template")).strip() == "by_template":
                    if "default_deck" in nt_out:
                        del nt_out["default_deck"]
                        changed = True
                nts_out[str(nt_id)] = nt_out
            if nts_out != note_types:
                cs_out["note_types"] = nts_out
                changed = True
        if cs_out != card_sorter:
            cfg["card_sorter"] = cs_out
            changed = True

    if "stability" in cfg:
        del cfg["stability"]
        changed = True

    if changed:
        try:
            with open(config.CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=2, ensure_ascii=False)
        except Exception:
            return False
    return changed


def migrate_note_type_names_to_ids() -> bool:
    try:
        from aqt import mw  # type: ignore
    except Exception:
        mw = None  # type: ignore

    if mw is None or not getattr(mw, "col", None):
        return False

    col = mw.col
    cfg = config._load_config()
    if not isinstance(cfg, dict):
        return False

    def _note_type_id_from_ident(col, ident: Any) -> str:
        if ident is None:
            return ""
        s = str(ident).strip()
        if not s:
            return ""
        if s.isdigit():
            return s
        try:
            model = col.models.by_name(s)
        except Exception:
            model = None
        if not model:
            return s
        try:
            return str(int(model.get("id")))
        except Exception:
            return s

    def _get_path(path: str) -> Any:
        cur: Any = cfg
        for part in path.split("."):
            if not isinstance(cur, dict):
                return None
            cur = cur.get(part)
            if cur is None:
                return None
        return cur

    changed = False

    def _map_dict_keys_path(path: str) -> None:
        nonlocal changed
        raw = _get_path(path)
        if not isinstance(raw, dict):
            return
        out: dict[str, Any] = {}
        for k, v in raw.items():
            key = _note_type_id_from_ident(col, k)
            if not key:
                continue
            if key != str(k):
                changed = True
            out[key] = v
        if out != raw:
            config._cfg_set(cfg, path, out)
            changed = True

    def _map_value_path(path: str) -> None:
        nonlocal changed
        raw = _get_path(path)
        if raw is None:
            return
        key = _note_type_id_from_ident(col, raw)
        if key and key != str(raw):
            config._cfg_set(cfg, path, key)
            changed = True

    _map_dict_keys_path("family_gate.note_types")
    _map_dict_keys_path("card_stages.note_types")
    _map_dict_keys_path("kanji_gate.vocab_note_types")
    _map_dict_keys_path("card_sorter.note_types")
    _map_dict_keys_path("mass_linker.rules")
    _map_value_path("kanji_gate.kanji_note_type")
    _map_value_path("kanji_gate.radical_note_type")

    if changed:
        try:
            with open(config.CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=2, ensure_ascii=False)
        except Exception:
            return False
    return changed


def migrate_template_names_to_ords() -> bool:
    try:
        from aqt import mw  # type: ignore
    except Exception:
        mw = None  # type: ignore

    if mw is None or not getattr(mw, "col", None):
        return False

    col = mw.col
    cfg = config._load_config()
    if not isinstance(cfg, dict):
        return False

    def _note_type_id_from_ident(col, ident: Any) -> str:
        if ident is None:
            return ""
        s = str(ident).strip()
        if not s:
            return ""
        if s.isdigit():
            return s
        try:
            model = col.models.by_name(s)
        except Exception:
            model = None
        if not model:
            return s
        try:
            return str(int(model.get("id")))
        except Exception:
            return s

    def _template_ord_from_ident(note_type_id: Any, ident: Any) -> str:
        s = str(ident).strip()
        if not s:
            return ""
        if s.isdigit():
            return s
        nt_id = _note_type_id_from_ident(col, note_type_id)
        if not nt_id or not nt_id.isdigit():
            return ""
        try:
            model = col.models.get(int(nt_id))
        except Exception:
            model = None
        if not model:
            return ""
        tmpls = model.get("tmpls", []) if isinstance(model, dict) else []
        for i, t in enumerate(tmpls):
            if not isinstance(t, dict):
                continue
            name = t.get("name")
            if name and str(name) == s:
                return str(i)
        return ""

    def _get_path(path: str) -> Any:
        cur: Any = cfg
        for part in path.split("."):
            if not isinstance(cur, dict):
                return None
            cur = cur.get(part)
            if cur is None:
                return None
        return cur

    changed = False

    def _map_template_list(note_type_id: Any, raw_list: Any) -> list[Any]:
        nonlocal changed
        if not isinstance(raw_list, list):
            return []
        out: list[Any] = []
        for val in raw_list:
            ord_val = _template_ord_from_ident(note_type_id, val)
            if ord_val:
                if ord_val != str(val):
                    changed = True
                out.append(ord_val)
            else:
                out.append(val)
        if out != raw_list:
            changed = True
        return out

    # card_stages.note_types -> stages templates
    card_stages = _get_path("card_stages.note_types")
    if isinstance(card_stages, dict):
        card_stages_out: dict[str, Any] = {}
        for nt_id, nt_cfg in card_stages.items():
            if not isinstance(nt_cfg, dict):
                card_stages_out[str(nt_id)] = nt_cfg
                continue
            stages = nt_cfg.get("stages") or []
            out_stages: list[Any] = []
            for st in stages:
                if isinstance(st, dict):
                    tmpls = _map_template_list(nt_id, st.get("templates") or [])
                    st_new = dict(st)
                    st_new["templates"] = tmpls
                    out_stages.append(st_new)
                elif isinstance(st, list):
                    out_stages.append(_map_template_list(nt_id, st))
                else:
                    out_stages.append(st)
            if out_stages != stages:
                changed = True
            nt_new = dict(nt_cfg)
            nt_new["stages"] = out_stages
            card_stages_out[str(nt_id)] = nt_new
        if card_stages_out != card_stages:
            config._cfg_set(cfg, "card_stages.note_types", card_stages_out)
            changed = True

    # mass_linker.rules -> templates
    rules = _get_path("mass_linker.rules")
    if isinstance(rules, dict):
        rules_out: dict[str, Any] = {}
        for nt_id, rule in rules.items():
            if not isinstance(rule, dict):
                rules_out[str(nt_id)] = rule
                continue
            if "templates" in rule:
                tmpls = _map_template_list(nt_id, rule.get("templates") or [])
                rule_new = dict(rule)
                rule_new["templates"] = tmpls
                rules_out[str(nt_id)] = rule_new
            else:
                rules_out[str(nt_id)] = rule
        if rules_out != rules:
            config._cfg_set(cfg, "mass_linker.rules", rules_out)
            changed = True

    # kanji_gate.vocab_note_types -> base/kanji templates
    vocab = _get_path("kanji_gate.vocab_note_types")
    if isinstance(vocab, dict):
        vocab_out: dict[str, Any] = {}
        for nt_id, nt_cfg in vocab.items():
            if not isinstance(nt_cfg, dict):
                vocab_out[str(nt_id)] = nt_cfg
                continue
            nt_new = dict(nt_cfg)
            if "base_templates" in nt_cfg:
                nt_new["base_templates"] = _map_template_list(
                    nt_id, nt_cfg.get("base_templates") or []
                )
            if "kanji_templates" in nt_cfg:
                nt_new["kanji_templates"] = _map_template_list(
                    nt_id, nt_cfg.get("kanji_templates") or []
                )
            vocab_out[str(nt_id)] = nt_new
        if vocab_out != vocab:
            config._cfg_set(cfg, "kanji_gate.vocab_note_types", vocab_out)
            changed = True

    # card_sorter.note_types -> by_template keys
    sorter = _get_path("card_sorter.note_types")
    if isinstance(sorter, dict):
        sorter_out: dict[str, Any] = {}
        for nt_id, nt_cfg in sorter.items():
            if not isinstance(nt_cfg, dict):
                sorter_out[str(nt_id)] = nt_cfg
                continue
            by_template = nt_cfg.get("by_template")
            if isinstance(by_template, dict):
                by_out: dict[str, Any] = {}
                for key, val in by_template.items():
                    ord_key = _template_ord_from_ident(nt_id, key)
                    new_key = ord_key or str(key)
                    if ord_key and ord_key != str(key):
                        changed = True
                    by_out[new_key] = val
                nt_new = dict(nt_cfg)
                nt_new["by_template"] = by_out
                sorter_out[str(nt_id)] = nt_new
            else:
                sorter_out[str(nt_id)] = nt_cfg
        if sorter_out != sorter:
            config._cfg_set(cfg, "card_sorter.note_types", sorter_out)
            changed = True

    if changed:
        try:
            with open(config.CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=2, ensure_ascii=False)
        except Exception:
            return False
    return changed



