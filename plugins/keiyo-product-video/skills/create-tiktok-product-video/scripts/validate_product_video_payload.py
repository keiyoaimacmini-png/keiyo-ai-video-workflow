#!/usr/bin/env python3
"""Strict, side-effect-free validator for a portable TikTok product-video payload."""

import argparse
import hashlib
import json
import math
import re
import sys
import unicodedata
from datetime import datetime
from pathlib import Path, PurePosixPath
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

MODEL_RE = re.compile(r"^AN-[A-Z0-9]{4}$")
SHA_RE = re.compile(r"^[0-9a-f]{64}$")
ASSET_RE = re.compile(r"^asset-[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
PRODUCT_PATH_RE = re.compile(r"^/view/product/([0-9]{12,})$")
CTA = "下のカートからチェック"
GATES = ("edit", "export", "cloud", "publish", "credit", "send")
ROOT = {"created_at", "manifest", "manifest_ref", "product_info", "goal_axis", "patterns", "facts_used", "hypotheses", "script", "cuts", "captions", "tts", "audio", "post_set", "design_quality_qa", "risk_register", "component_hashes", "portable_setup", "delivery", "approval_gates", "routing", "openclaw_prohibition", "camee_tiktok_shop", "integrity", "cleanup_preflight"}
ALIAS_KEYS = {"path", "source_path", "local_path", "file_path", "absolute_path", "asset_hashes", "asset_sha256", "requirements_hash", "required_media_description", "must_show", "must_not_show"}
JST = ZoneInfo("Asia/Tokyo")
GOAL_AXES = {"watch_continuation", "comment_content_coupling", "reward_stimulation"}
SEMANTIC_ENUMS = {"subject": {"product", "hand", "person", "product_and_hand"}, "action": {"static", "hold", "press", "use", "reveal"}, "composition": {"close_up", "medium", "overhead", "wide"}, "product_visibility": {"full", "partial"}, "text_visibility": {"none", "product_label"}}
QA_MAX = {"hook": 15, "tempo": 10, "emotion": 10, "continuation_design": 15, "save_design": 10, "comment_design": 10, "share_design": 10, "purchase_path_design": 20}


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def is_sha(value):
    return isinstance(value, str) and SHA_RE.fullmatch(value) is not None


def valid_time_range(start, end):
    def valid_time_value(value):
        if isinstance(value, bool):
            return False
        if isinstance(value, int):
            return 0 <= value <= 86400
        return isinstance(value, float) and math.isfinite(value) and 0 <= value <= 86400
    return valid_time_value(start) and valid_time_value(end) and start < end


def unknown(mapping, allowed, label, errors):
    if not isinstance(mapping, dict):
        errors.append(f"{label} must be an object")
        return False
    extra = set(mapping) - allowed
    if extra:
        errors.append(f"{label} has unknown fields: {', '.join(sorted(extra))}")
    return not extra


def requirements_hash(cut):
    return digest({"cut_id": cut.get("cut_id"), "media_requirements": cut.get("media_requirements")})


def semantic_description(semantics):
    return ";".join(f"{key}={semantics.get(key)}" for key in ("subject", "action", "composition", "product_visibility", "text_visibility"))


def production_subject(payload):
    return {key: value for key, value in payload.items() if key not in {"integrity", "approval_gates", "openclaw_prohibition", "camee_tiktok_shop"}}


def visible_subject(payload):
    return {key: payload[key] for key in ("script", "captions", "tts", "post_set") if key in payload}


def expected_hashes(payload):
    return digest(production_subject(payload)), digest(visible_subject(payload))


def errors_for(payload):
    errors = []
    unknown(payload, ROOT, "payload", errors)
    assets, model = check_model_and_assets(payload, errors)
    cut_ids, additional_needed = check_cuts(payload, assets, errors)
    check_canonical_fields(payload, cut_ids, errors)
    try:
        production_hash, visible_hash = expected_hashes(payload)
    except (OverflowError, TypeError, ValueError):
        production_hash, visible_hash = "", ""
        errors.append("payload cannot be canonically hashed")
    check_integrity(payload, production_hash, visible_hash, errors)
    check_delivery(payload, model, errors)
    check_approvals(payload, production_hash, visible_hash, additional_needed, errors)
    check_routing(payload, production_hash, visible_hash, errors)
    check_cleanup(payload, assets, errors)
    reject_portability_aliases(payload, "", errors)
    return errors


def check_model_and_assets(payload, errors):
    materials = {}
    manifest = payload.get("manifest")
    if not isinstance(manifest, list) or not manifest:
        errors.append("manifest must be a non-empty list")
    else:
        for index, material in enumerate(manifest):
            label = f"manifest[{index}]"
            unknown(material, {"material_id", "kind", "source_location", "provided_by", "observed_at", "byte_size", "sha256", "media_type", "access_status", "usage_status", "analysis_status", "limitations", "company_authoritative", "observed_product_models"}, label, errors)
            if not isinstance(material, dict) or not isinstance(material.get("material_id"), str) or material["material_id"] in materials:
                errors.append(f"{label}.material_id must be unique")
                continue
            materials[material["material_id"]] = material
            if not is_sha(material.get("sha256")):
                errors.append(f"{label}.sha256 must be lowercase SHA-256")
            if any(not isinstance(material.get(key), str) for key in ("kind", "source_location", "provided_by", "observed_at", "media_type", "access_status", "usage_status", "analysis_status", "limitations")) or not valid_source_location(material.get("source_location")) or not isinstance(material.get("byte_size"), int) or material["byte_size"] < 0:
                errors.append(f"{label} must contain the full canonical manifest accounting fields")
            if material.get("company_authoritative") is True and (material.get("access_status") != "available" or not valid_models(material.get("observed_product_models"))):
                errors.append(f"{label} must have available authoritative model observations")
    product = payload.get("product_info")
    unknown(product, {"product_model", "product_model_provenance"}, "product_info", errors)
    model = product.get("product_model") if isinstance(product, dict) else None
    if not isinstance(model, str) or not MODEL_RE.fullmatch(model):
        errors.append("product_info.product_model must match ^AN-[A-Z0-9]{4}$")
    provenance = product.get("product_model_provenance") if isinstance(product, dict) else None
    unknown(provenance, {"status", "material_ids", "material_sha256s", "observed_model"}, "product_model_provenance", errors)
    official = {mid: item for mid, item in materials.items() if item.get("company_authoritative") is True and item.get("access_status") == "available"}
    observed = {value for item in official.values() for value in item.get("observed_product_models", [])}
    if not isinstance(provenance, dict):
        errors.append("product_model_provenance is required")
    elif observed == {model} and official and provenance.get("status") == "verified" and isinstance(provenance.get("material_ids"), list) and len(provenance["material_ids"]) == len(set(provenance["material_ids"])) and set(provenance["material_ids"]) == set(official) and provenance.get("observed_model") == model and provenance.get("material_sha256s") == {mid: item["sha256"] for mid, item in official.items()}:
        pass
    elif provenance.get("status") == "conflict":
        errors.append("company model observations conflict; HOLD_MODEL_UNVERIFIED")
    else:
        errors.append("product model provenance must close verified company observations")
    return check_assets(payload, errors), model


def valid_models(values):
    return isinstance(values, list) and values and all(isinstance(value, str) and MODEL_RE.fullmatch(value) for value in values)


def normalized_path(value):
    if not isinstance(value, str) or not value:
        return None
    value = unicodedata.normalize("NFKC", value)
    if "\\" in value or "//" in value or value.startswith(("/", "~", "\\")) or re.match(r"^[A-Za-z]:", value):
        return None
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        return None
    return str(PurePosixPath(value.casefold()))


def valid_source_location(value):
    if not isinstance(value, str):
        return False
    parsed = urlparse(value)
    return (parsed.scheme == "https" and bool(parsed.hostname) and parsed.username is None and parsed.password is None) or normalized_path(value) is not None


def check_assets(payload, errors):
    delivery = payload.get("delivery")
    unknown(delivery, {"naming_jst_date", "capcut_cloud_project_path", "completed_video_basename", "portable_handoff"}, "delivery", errors)
    handoff = delivery.get("portable_handoff") if isinstance(delivery, dict) else None
    unknown(handoff, {"uses_relative_paths", "assets"}, "delivery.portable_handoff", errors)
    assets, aliases = {}, set()
    values = handoff.get("assets") if isinstance(handoff, dict) else None
    if not isinstance(handoff, dict) or handoff.get("uses_relative_paths") is not True or not isinstance(values, list) or not values:
        errors.append("portable_handoff needs uses_relative_paths=true and non-empty assets")
        return assets
    for index, asset in enumerate(values):
        label = f"portable_handoff.assets[{index}]"
        unknown(asset, {"asset_id", "media_sha256", "media_relative_path", "sidecar_sha256", "sidecar_relative_path", "classification"}, label, errors)
        if not isinstance(asset, dict) or not ASSET_RE.fullmatch(asset.get("asset_id", "")) or asset["asset_id"] in assets:
            errors.append(f"{label}.asset_id must be unique and stable")
            continue
        assets[asset["asset_id"]] = asset
        if not is_sha(asset.get("media_sha256")) or not is_sha(asset.get("sidecar_sha256")):
            errors.append(f"{label} must have media and sidecar SHA-256")
        for field in ("media_relative_path", "sidecar_relative_path"):
            alias = normalized_path(asset.get(field))
            if alias is None or alias in aliases:
                errors.append(f"{label}.{field} must be safe and non-aliasing")
            else:
                aliases.add(alias)
        classification = asset.get("classification")
        unknown(classification, {"original", "editable_project_dependency", "shared", "uncertain"}, f"{label}.classification", errors)
        if not isinstance(classification, dict) or any(classification.get(key) not in {True, False} for key in ("original", "editable_project_dependency", "shared", "uncertain")):
            errors.append(f"{label}.classification needs four boolean flags")
    return assets


def check_cuts(payload, assets, errors):
    cuts = payload.get("cuts")
    if not isinstance(cuts, list) or not cuts:
        errors.append("cuts must be a non-empty list")
        return [], False
    cut_ids, additional_needed = [], False
    for index, cut in enumerate(cuts):
        label = f"cuts[{index}]"
        unknown(cut, {"cut_id", "timeline_in", "timeline_out", "source_asset_id", "source_in", "source_out", "editor", "media_requirements", "matched_sidecar_receipt", "additional_asset_required"}, label, errors)
        if not isinstance(cut, dict) or not isinstance(cut.get("cut_id"), str) or not cut["cut_id"]:
            errors.append(f"{label}.cut_id is required")
            continue
        cut_ids.append(cut["cut_id"])
        additional = cut.get("additional_asset_required") is True
        source_absent = cut.get("source_asset_id") is None and cut.get("source_in") is None and cut.get("source_out") is None
        bad_range = not valid_time_range(cut.get("timeline_in"), cut.get("timeline_out"))
        if (not additional and (not valid_time_range(cut.get("source_in"), cut.get("source_out")) or not isinstance(cut.get("source_asset_id"), str))) or (additional and not source_absent) or bad_range:
            errors.append(f"{label} needs valid timeline/source ranges")
        editor = cut.get("editor")
        unknown(editor, {"track", "layer", "transition", "zoom", "effect", "speed"}, f"{label}.editor", errors)
        if not isinstance(editor, dict) or not isinstance(editor.get("track"), str) or not isinstance(editor.get("layer"), int) or editor.get("transition") not in {"cut", "dissolve", "none"} or editor.get("zoom") not in {"none", "in", "out"} or editor.get("effect") not in {"none", "highlight"} or not isinstance(editor.get("speed"), (int, float)):
            errors.append(f"{label}.editor must use canonical timeline fields")
        requirements = cut.get("media_requirements")
        unknown(requirements, {"semantics", "canonical_description", "must_show", "must_not_show"}, f"{label}.media_requirements", errors)
        semantics = requirements.get("semantics") if isinstance(requirements, dict) else None
        unknown(semantics, set(SEMANTIC_ENUMS), f"{label}.media_requirements.semantics", errors)
        if not isinstance(semantics, dict) or any(semantics.get(key) not in values for key, values in SEMANTIC_ENUMS.items()) or requirements.get("canonical_description") != semantic_description(semantics):
            errors.append(f"{label}.media_requirements requires canonical enum description")
        for field in ("must_show", "must_not_show"):
            values = requirements.get(field) if isinstance(requirements, dict) else None
            if not isinstance(values, list) or (field == "must_show" and not values):
                errors.append(f"{label}.media_requirements.{field} must be structured")
            elif field == "must_show" and any(not isinstance(item, dict) or set(item) != {"subject", "visibility"} or item.get("subject") not in SEMANTIC_ENUMS["subject"] or item.get("visibility") not in SEMANTIC_ENUMS["product_visibility"] for item in values):
                errors.append(f"{label}.media_requirements.must_show requires controlled subject/visibility")
            elif field == "must_not_show" and any(item not in {"third_party_logo", "face", "qr", "plate"} for item in values):
                errors.append(f"{label}.media_requirements.must_not_show requires controlled risk enums")
        receipt = cut.get("matched_sidecar_receipt")
        if isinstance(receipt, dict) == additional:
            errors.append(f"{label} needs exactly one sidecar receipt or additional_asset_required")
        if additional:
            additional_needed = True
        if isinstance(receipt, dict):
            unknown(receipt, {"asset_id", "sidecar_sha256", "sidecar_relative_path", "status", "requirements_sha256", "matched_fields"}, f"{label}.matched_sidecar_receipt", errors)
            asset = assets.get(receipt.get("asset_id"))
            if not isinstance(asset, dict) or receipt.get("asset_id") != cut.get("source_asset_id") or receipt.get("sidecar_sha256") != asset.get("sidecar_sha256") or receipt.get("sidecar_relative_path") != asset.get("sidecar_relative_path"):
                errors.append(f"{label}.matched_sidecar_receipt must bind known sidecar SHA/path")
            if receipt.get("status") != "verified" or receipt.get("requirements_sha256") != requirements_hash(cut) or receipt.get("matched_fields") != ["canonical_description", "semantics", "must_show", "must_not_show"]:
                errors.append(f"{label}.matched_sidecar_receipt must be verified and semantically complete")
    if len(cut_ids) != len(set(cut_ids)):
        errors.append("cut IDs must be unique")
    cut_ranges = {cut["cut_id"]: (cut["timeline_in"], cut["timeline_out"]) for cut in cuts if isinstance(cut, dict) and isinstance(cut.get("cut_id"), str) and valid_time_range(cut.get("timeline_in"), cut.get("timeline_out"))}
    exact_closure(payload.get("script"), cut_ids, "script", "dialogue", {"cut_id", "dialogue", "timeline_in", "timeline_out"}, cut_ranges, errors)
    exact_closure(payload.get("captions"), cut_ids, "captions", "text", {"cut_id", "text", "timeline_in", "timeline_out", "track", "layer", "position", "style", "line_breaks"}, cut_ranges, errors)
    closure = [("script", "dialogue"), ("captions", "text")]
    if "tts" in payload:
        exact_closure(payload.get("tts"), cut_ids, "tts", "text", {"cut_id", "text", "voice", "speed", "timeline_in", "timeline_out", "duration_status", "track", "layer"}, cut_ranges, errors)
        closure.append(("tts", "text"))
    if cut_ids:
        final_id = cut_ids[-1]
        for label, field in closure:
            records = payload.get(label, [])
            record = next((item for item in records if isinstance(item, dict) and item.get("cut_id") == final_id), None)
            if not isinstance(record, dict) or record.get(field) != CTA:
                errors.append(f"final {label} {field} must exactly equal the required CTA")
    return cut_ids, additional_needed


def exact_closure(records, cut_ids, label, field, allowed, cut_ranges, errors):
    if not isinstance(records, list):
        errors.append(f"{label} must be a list")
        return
    ids = []
    for index, record in enumerate(records):
        if not isinstance(record, dict) or set(record) != allowed or not isinstance(record.get("cut_id"), str) or not isinstance(record.get(field), str) or not valid_time_range(record.get("timeline_in"), record.get("timeline_out")):
            errors.append(f"{label}[{index}] must contain canonical timeline fields")
        else:
            if label in {"script", "captions", "tts"} and (record["timeline_in"] < cut_ranges.get(record["cut_id"], (float("inf"), -float("inf")))[0] or record["timeline_out"] > cut_ranges.get(record["cut_id"], (float("inf"), -float("inf")))[1]):
                errors.append(f"{label}[{index}] must be contained in its cut timeline")
            if label == "captions" and (record.get("track") != "caption" or not isinstance(record.get("layer"), int) or record.get("position") not in {"top", "center", "bottom"} or not isinstance(record.get("style"), dict) or set(record["style"]) != {"font", "color", "outline", "shadow", "size", "alignment"} or not isinstance(record.get("line_breaks"), list)):
                errors.append(f"captions[{index}] must contain canonical editor fields")
            if label == "tts" and (not isinstance(record.get("voice"), str) or not isinstance(record.get("speed"), (int, float)) or record.get("duration_status") not in {"planned", "verified"} or record.get("track") != "tts" or not isinstance(record.get("layer"), int)):
                errors.append(f"tts[{index}] must contain canonical editor fields")
            ids.append(record["cut_id"])
    if len(ids) != len(cut_ids) or len(ids) != len(set(ids)) or set(ids) != set(cut_ids):
        errors.append(f"{label} must close exactly over all cut IDs")


def check_canonical_fields(payload, cut_ids, errors):
    if payload.get("goal_axis") not in GOAL_AXES:
        errors.append("goal_axis must be one active canonical axis")
    manifest = payload.get("manifest") if isinstance(payload.get("manifest"), list) else []
    refs = payload.get("manifest_ref")
    expected_refs = [{"material_id": item.get("material_id"), "sha256": item.get("sha256")} for item in manifest if isinstance(item, dict)]
    if not isinstance(refs, list) or refs != expected_refs or len({item["material_id"] for item in refs if isinstance(item, dict) and "material_id" in item}) != len(refs) or any(not isinstance(item, dict) or set(item) != {"material_id", "sha256"} for item in refs):
        errors.append("manifest_ref must close exactly over manifest IDs and hashes")
    for label, required in (("patterns", {"pattern_key", "reason", "reusable_structure", "not_to_copy", "confidence", "source_video_count"}), ("facts_used", {"fact_id", "classification", "value", "material_refs"}), ("hypotheses", {"hypothesis_id", "statement", "basis", "disproof_condition"}), ("risk_register", {"risk_id", "category", "status", "mitigation"})):
        values = payload.get(label)
        if not isinstance(values, list) or any(not isinstance(item, dict) or set(item) != required for item in values):
            errors.append(f"{label} must use its canonical record schema")
    known_refs = {(item.get("material_id"), item.get("sha256")) for item in manifest if isinstance(item, dict)}
    for fact in payload.get("facts_used", []) if isinstance(payload.get("facts_used"), list) else []:
        refs = fact.get("material_refs") if isinstance(fact, dict) else None
        if fact.get("classification") != "verified_fact" or not isinstance(refs, list) or not refs or any(not isinstance(ref, dict) or set(ref) != {"material_id", "sha256"} or (ref.get("material_id"), ref.get("sha256")) not in known_refs for ref in refs):
            errors.append("facts_used material_refs must close over manifest ID and SHA")
    audio = payload.get("audio")
    unknown(audio, {"bgm", "se", "source_audio"}, "audio", errors)
    if not isinstance(audio, dict) or any(not isinstance(audio.get(key), dict) or set(audio[key]) != {"status", "origin", "rights", "level", "fade"} for key in ("bgm", "se", "source_audio")):
        errors.append("audio must contain canonical BGM/SE/source-audio records")
    check_post_set(payload, errors)
    qa = payload.get("design_quality_qa")
    unknown(qa, {"axes", "total_score", "metrics"}, "design_quality_qa", errors)
    axes = qa.get("axes") if isinstance(qa, dict) else None
    if not isinstance(axes, list) or len(axes) != 8 or len({item.get("axis") for item in axes if isinstance(item, dict)}) != 8 or {item.get("axis") for item in axes if isinstance(item, dict)} != set(QA_MAX) or any(not isinstance(item, dict) or set(item) != {"axis", "score", "max_score", "evidence", "counterevidence", "improvement"} or item.get("max_score") != QA_MAX.get(item.get("axis")) or not isinstance(item.get("score"), int) or not 0 <= item["score"] <= item["max_score"] for item in axes):
        errors.append("design_quality_qa must contain all eight canonical axes")
    elif qa.get("total_score") != sum(item["score"] for item in axes) or qa.get("metrics") != {"watch_retention": "not_measured", "comment_rate": "not_measured", "save_rate": "not_measured", "share_rate": "not_measured", "purchase_rate": "not_measured"}:
        errors.append("design_quality_qa total/metrics are invalid")
    setup = payload.get("portable_setup")
    unknown(setup, {"schema_version", "setup_steps"}, "portable_setup", errors)
    if not isinstance(setup, dict) or not isinstance(setup.get("schema_version"), str) or setup.get("setup_steps") != ["verify_hashes", "import_assets", "create_timeline"]:
        errors.append("portable_setup must provide canonical setup instructions")
    check_component_hashes(payload, errors)


def check_post_set(payload, errors):
    post_set = payload.get("post_set")
    if post_set is None:
        errors.append("post_set is required")
        return
    unknown(post_set, {"title", "post_text", "pinned_comment", "description", "hashtags"}, "post_set", errors)
    if not isinstance(post_set, dict) or any(not isinstance(post_set.get(key), str) for key in ("title", "post_text", "pinned_comment", "description")) or not isinstance(post_set.get("hashtags"), list) or any(not isinstance(tag, str) for tag in post_set["hashtags"]):
        errors.append("post_set must use the canonical visible-content fields")


def check_component_hashes(payload, errors):
    hashes = payload.get("component_hashes")
    keys = {"manifest_sha256", "favorite_context_sha256", "script_sha256", "cuts_sha256", "captions_sha256", "tts_sha256"}
    unknown(hashes, keys, "component_hashes", errors)
    expected = {"manifest_sha256": digest(payload.get("manifest")), "favorite_context_sha256": digest({"goal_axis": payload.get("goal_axis"), "patterns": payload.get("patterns")}), "script_sha256": digest(payload.get("script")), "cuts_sha256": digest(payload.get("cuts")), "captions_sha256": digest(payload.get("captions")), "tts_sha256": digest(payload.get("tts"))}
    if not isinstance(hashes, dict) or hashes != expected:
        errors.append("component_hashes must equal canonical component hashes")


def check_integrity(payload, production_hash, visible_hash, errors):
    integrity = payload.get("integrity")
    unknown(integrity, {"production_payload_sha256", "visible_content_sha256"}, "integrity", errors)
    if not isinstance(integrity, dict) or integrity.get("production_payload_sha256") != production_hash or integrity.get("visible_content_sha256") != visible_hash:
        errors.append("integrity hashes must equal validator-computed canonical hashes")


def jst_date(value):
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00")) if isinstance(value, str) else None
    except ValueError:
        parsed = None
    return parsed.astimezone(JST).strftime("%Y_%m_%d") if parsed and parsed.tzinfo else None


def check_delivery(payload, model, errors):
    date = jst_date(payload.get("created_at"))
    delivery = payload.get("delivery")
    if date is None:
        errors.append("created_at must be offset-aware for JST naming")
    elif not isinstance(delivery, dict) or delivery.get("naming_jst_date") != date or delivery.get("completed_video_basename") != f"AI作成_{model}_{date}" or delivery.get("capcut_cloud_project_path") != f"Space/{model}/AI作成_{model}_{date}":
        errors.append("delivery naming must use the real JST date")


def hash_bound(value, production_hash, visible_hash, label, errors):
    if not isinstance(value, dict) or value.get("bound_production_payload_sha256") != production_hash or value.get("bound_visible_content_sha256") != visible_hash:
        errors.append(f"{label} must bind current production and visible hashes")


def check_approvals(payload, production_hash, visible_hash, additional_needed, errors):
    gates = payload.get("approval_gates")
    unknown(gates, set(GATES), "approval_gates", errors)
    if not isinstance(gates, dict):
        return
    for gate in GATES:
        value = gates.get(gate)
        unknown(value, {"status", "receipt", "explicit_approval", "bound_production_payload_sha256", "bound_visible_content_sha256"}, f"approval_gates.{gate}", errors)
        status = value.get("status") if isinstance(value, dict) else None
        if status not in {"pending", "approved", "not_applicable"}:
            errors.append(f"approval_gates.{gate}.status is invalid")
            continue
        hash_bound(value, production_hash, visible_hash, f"approval_gates.{gate}", errors)
        if status == "approved" and gate == "edit" and (value.get("receipt") != "OK" or additional_needed):
            errors.append("approved edit requires exact OK and no additional_asset_required")
        if status == "approved" and gate != "edit" and value.get("explicit_approval") is not True:
            errors.append(f"approval_gates.{gate} requires its own explicit approval")


def check_routing(payload, production_hash, visible_hash, errors):
    routing = payload.get("routing")
    unknown(routing, {"openclaw_bound", "camee_neo_openclaw_bound"}, "routing", errors)
    if not isinstance(routing, dict) or any(routing.get(key) not in {True, False} for key in ("openclaw_bound", "camee_neo_openclaw_bound")):
        errors.append("routing needs two booleans")
        return
    required = routing["openclaw_bound"] or routing["camee_neo_openclaw_bound"]
    prohibition = payload.get("openclaw_prohibition")
    if required:
        unknown(prohibition, {"passed", "checked_last", "policy_version", "attempt", "matched_rule_ids", "bound_production_payload_sha256", "bound_visible_content_sha256"}, "openclaw_prohibition", errors)
        if not isinstance(prohibition, dict) or prohibition.get("passed") is not True or prohibition.get("checked_last") is not True or not isinstance(prohibition.get("policy_version"), str) or not prohibition["policy_version"] or prohibition.get("attempt") not in {1, 2, 3} or prohibition.get("matched_rule_ids") != []:
            errors.append("OpenClaw prohibition receipt must pass checked-last with no matches")
        else:
            hash_bound(prohibition, production_hash, visible_hash, "openclaw_prohibition", errors)
    elif prohibition is not None:
        errors.append("openclaw_prohibition is forbidden when routing is not OpenClaw-bound")
    if routing["camee_neo_openclaw_bound"]:
        receipt = payload.get("camee_tiktok_shop")
        unknown(receipt, {"verification_status", "url", "product_id", "bound_production_payload_sha256", "bound_visible_content_sha256"}, "camee_tiktok_shop", errors)
        if not isinstance(receipt, dict) or receipt.get("verification_status") != "verified" or not valid_shop_url(receipt.get("url"), receipt.get("product_id")):
            errors.append("Camee receipt must verify a real HTTPS TikTok Shop product URL")
        else:
            hash_bound(receipt, production_hash, visible_hash, "camee_tiktok_shop", errors)
    elif payload.get("camee_tiktok_shop") is not None:
        errors.append("camee_tiktok_shop is forbidden outside Camee Neo/OpenClaw routing")


def valid_shop_url(value, product_id):
    if not isinstance(value, str) or not isinstance(product_id, str):
        return False
    parsed = urlparse(value)
    match = PRODUCT_PATH_RE.fullmatch(parsed.path)
    try:
        port = parsed.port
    except ValueError:
        return False
    return parsed.scheme == "https" and parsed.hostname == "shop.tiktok.com" and parsed.username is None and parsed.password is None and port in {None, 443} and not parsed.params and not parsed.fragment and match is not None and match.group(1) == product_id


def check_cleanup(payload, assets, errors):
    cleanup = payload.get("cleanup_preflight")
    allowed = {"preflight_only", "preserve_originals", "preserve_editable_dependencies", "preserve_shared_or_uncertain", "local_working_download_candidates"}
    unknown(cleanup, allowed, "cleanup_preflight", errors)
    if not isinstance(cleanup, dict) or cleanup.get("preflight_only") is not True:
        errors.append("cleanup_preflight must be preflight-only")
        return
    if any(cleanup.get(key) is not True for key in ("preserve_originals", "preserve_editable_dependencies", "preserve_shared_or_uncertain")):
        errors.append("cleanup preflight must preserve originals/dependencies/shared/uncertain")
    candidates = cleanup.get("local_working_download_candidates")
    if not isinstance(candidates, list):
        errors.append("cleanup candidates must be a list")
        return
    for index, candidate in enumerate(candidates):
        label = f"cleanup candidates[{index}]"
        unknown(candidate, {"asset_id", "media_sha256", "verified_local_working_download", "release_approved"}, label, errors)
        asset = assets.get(candidate.get("asset_id")) if isinstance(candidate, dict) else None
        flags = asset.get("classification") if isinstance(asset, dict) else None
        if not isinstance(candidate, dict) or not isinstance(asset, dict) or candidate.get("media_sha256") != asset.get("media_sha256") or candidate.get("verified_local_working_download") is not True or candidate.get("release_approved") is not True or not isinstance(flags, dict) or any(flags.get(key) is not False for key in ("original", "editable_project_dependency", "shared", "uncertain")):
            errors.append(f"{label} must be an approved verified non-protected asset cross-check")


def reject_portability_aliases(value, label, errors):
    if isinstance(value, dict):
        for key, child in value.items():
            child_label = f"{label}.{key}" if label else key
            allowed_semantic_key = label.endswith("media_requirements") and key in {"must_show", "must_not_show"}
            if key in ALIAS_KEYS and not allowed_semantic_key:
                errors.append(f"legacy or forbidden alias key: {child_label}")
            reject_portability_aliases(child, child_label, errors)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            reject_portability_aliases(child, f"{label}[{index}]", errors)
    elif isinstance(value, str):
        normalized = unicodedata.normalize("NFKC", value)
        if normalized.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:", normalized):
            errors.append(f"portable payload forbids cross-platform absolute path: {label}")


def fixture(openclaw=False, camee=False, tts=True, additional=False):
    source_sha, media_sha, sidecar_sha = "a" * 64, "b" * 64, "c" * 64
    sem1 = {"subject": "product_and_hand", "action": "hold", "composition": "close_up", "product_visibility": "full", "text_visibility": "none"}
    sem2 = {"subject": "product", "action": "reveal", "composition": "medium", "product_visibility": "full", "text_visibility": "product_label"}
    req1 = {"semantics": sem1, "canonical_description": semantic_description(sem1), "must_show": [{"subject": "product", "visibility": "full"}], "must_not_show": []}
    req2 = {"semantics": sem2, "canonical_description": semantic_description(sem2), "must_show": [{"subject": "product", "visibility": "full"}], "must_not_show": ["third_party_logo"]}
    cuts = [{"cut_id": "cut-01", "timeline_in": 0.0, "timeline_out": 2.0, "source_asset_id": "asset-product", "source_in": 0.0, "source_out": 2.0, "editor": {"track": "video", "layer": 1, "transition": "cut", "zoom": "in", "effect": "highlight", "speed": 1.0}, "media_requirements": req1}, {"cut_id": "cut-02", "timeline_in": 2.0, "timeline_out": 4.0, "source_asset_id": "asset-product", "source_in": 2.0, "source_out": 4.0, "editor": {"track": "video", "layer": 1, "transition": "cut", "zoom": "none", "effect": "none", "speed": 1.0}, "media_requirements": req2}]
    for cut in cuts:
        if additional and cut["cut_id"] == "cut-01":
            cut["additional_asset_required"] = True
            cut["source_asset_id"] = None
            cut["source_in"] = None
            cut["source_out"] = None
        else:
            cut["matched_sidecar_receipt"] = {"asset_id": "asset-product", "sidecar_sha256": sidecar_sha, "sidecar_relative_path": "media/product.sidecar.json", "status": "verified", "requirements_sha256": requirements_hash(cut), "matched_fields": ["canonical_description", "semantics", "must_show", "must_not_show"]}
    payload = {"created_at": "2026-08-03T16:00:00+00:00", "manifest": [{"material_id": "material-company", "company_authoritative": True, "access_status": "available", "sha256": source_sha, "observed_product_models": ["AN-T001"]}], "product_info": {"product_model": "AN-T001", "product_model_provenance": {"status": "verified", "material_ids": ["material-company"], "material_sha256s": {"material-company": source_sha}, "observed_model": "AN-T001"}}, "script": [{"cut_id": "cut-01", "dialogue": "特徴を確認"}, {"cut_id": "cut-02", "dialogue": CTA}], "cuts": cuts, "captions": [{"cut_id": "cut-01", "text": "特徴を確認"}, {"cut_id": "cut-02", "text": CTA}], "delivery": {"naming_jst_date": "2026_08_04", "capcut_cloud_project_path": "Space/AN-T001/AI作成_AN-T001_2026_08_04", "completed_video_basename": "AI作成_AN-T001_2026_08_04", "portable_handoff": {"uses_relative_paths": True, "assets": [{"asset_id": "asset-product", "media_sha256": media_sha, "media_relative_path": "media/product.mp4", "sidecar_sha256": sidecar_sha, "sidecar_relative_path": "media/product.sidecar.json", "classification": {"original": False, "editable_project_dependency": False, "shared": False, "uncertain": False}}]}}, "routing": {"openclaw_bound": openclaw, "camee_neo_openclaw_bound": camee}, "cleanup_preflight": {"preflight_only": True, "preserve_originals": True, "preserve_editable_dependencies": True, "preserve_shared_or_uncertain": True, "local_working_download_candidates": [{"asset_id": "asset-product", "media_sha256": media_sha, "verified_local_working_download": True, "release_approved": True}]}}
    payload["manifest"] = [{"material_id": "material-company", "kind": "product_url", "source_location": "https://example.invalid/product", "provided_by": "user", "observed_at": "2026-08-03T16:00:00+00:00", "byte_size": 1, "sha256": source_sha, "media_type": "text/html", "access_status": "available", "usage_status": "approved", "analysis_status": "complete", "limitations": "none", "company_authoritative": True, "observed_product_models": ["AN-T001"]}]
    payload["manifest_ref"] = [{"material_id": "material-company", "sha256": source_sha}]
    payload.update(goal_axis="watch_continuation", patterns=[{"pattern_key": "pattern-01", "reason": "fit", "reusable_structure": "hook", "not_to_copy": "wording", "confidence": "medium", "source_video_count": 1}], facts_used=[{"fact_id": "fact-01", "classification": "verified_fact", "value": "observed", "material_refs": [{"material_id": "material-company", "sha256": source_sha}]}], hypotheses=[{"hypothesis_id": "hyp-01", "statement": "test", "basis": "pattern", "disproof_condition": "metric"}], audio={key: {"status": "not_applicable", "origin": "none", "rights": "not_applicable", "level": 0, "fade": 0} for key in ("bgm", "se", "source_audio")}, post_set={"title": "title", "post_text": "post", "pinned_comment": "comment", "description": "description", "hashtags": ["#test"]}, design_quality_qa={"axes": [{"axis": axis, "score": 0, "max_score": maximum, "evidence": "none", "counterevidence": "none", "improvement": "next"} for axis, maximum in QA_MAX.items()], "total_score": 0, "metrics": {"watch_retention": "not_measured", "comment_rate": "not_measured", "save_rate": "not_measured", "share_rate": "not_measured", "purchase_rate": "not_measured"}}, risk_register=[{"risk_id": "risk_01", "category": "rights", "status": "open", "mitigation": "review"}], portable_setup={"schema_version": "1", "setup_steps": ["verify_hashes", "import_assets", "create_timeline"]})
    payload["script"] = [{"cut_id": cut["cut_id"], "dialogue": "特徴を確認" if cut["cut_id"] == "cut-01" else CTA, "timeline_in": cut["timeline_in"], "timeline_out": cut["timeline_out"]} for cut in cuts]
    style = {"font": "sans", "color": "white", "outline": "black", "shadow": "none", "size": 32, "alignment": "center"}
    payload["captions"] = [{"cut_id": item["cut_id"], "text": item["dialogue"], "timeline_in": item["timeline_in"], "timeline_out": item["timeline_out"], "track": "caption", "layer": 2, "position": "bottom", "style": style, "line_breaks": []} for item in payload["script"]]
    if tts:
        payload["tts"] = [{"cut_id": item["cut_id"], "text": item["dialogue"], "voice": "neutral", "speed": 1.2, "timeline_in": item["timeline_in"], "timeline_out": item["timeline_out"], "duration_status": "planned", "track": "tts", "layer": 3} for item in payload["script"]]
    payload["component_hashes"] = {"manifest_sha256": digest(payload["manifest"]), "favorite_context_sha256": digest({"goal_axis": payload["goal_axis"], "patterns": payload["patterns"]}), "script_sha256": digest(payload["script"]), "cuts_sha256": digest(cuts), "captions_sha256": digest(payload["captions"]), "tts_sha256": digest(payload.get("tts"))}
    production_hash, visible_hash = expected_hashes(payload)
    payload["integrity"] = {"production_payload_sha256": production_hash, "visible_content_sha256": visible_hash}
    payload["approval_gates"] = {gate: {"status": "pending", "bound_production_payload_sha256": production_hash, "bound_visible_content_sha256": visible_hash} for gate in GATES}
    if openclaw or camee:
        payload["openclaw_prohibition"] = {"passed": True, "checked_last": True, "policy_version": "v1", "attempt": 1, "matched_rule_ids": [], "bound_production_payload_sha256": production_hash, "bound_visible_content_sha256": visible_hash}
    if camee:
        payload["camee_tiktok_shop"] = {"verification_status": "verified", "url": "https://shop.tiktok.com/view/product/123456789012", "product_id": "123456789012", "bound_production_payload_sha256": production_hash, "bound_visible_content_sha256": visible_hash}
    return payload


def self_test():
    cases = [("valid", fixture(), False), ("valid no TTS", fixture(tts=False), False), ("valid additional-asset hold", fixture(additional=True), False), ("valid OpenClaw Camee", fixture(True, True), False)]
    mutations = (("model conflict", lambda p: p["manifest"][0].update(observed_product_models=["AN-T001", "AN-X999"])), ("explicit conflict hold", lambda p: p["product_info"]["product_model_provenance"].update(status="conflict")), ("legacy model alias", lambda p: p["product_info"].update(observed_value="AN-T001")), ("missing script closure", lambda p: p["script"].pop(0)), ("no-TTS caption CTA", lambda p: p["captions"][-1].update(text="下のカートをチェック")), ("legacy cut alias", lambda p: p["cuts"][0].update(required_media_description="x")), ("sidecar unverified", lambda p: p["cuts"][0]["matched_sidecar_receipt"].update(status="pending")), ("sidecar bad path", lambda p: p["cuts"][0]["matched_sidecar_receipt"].update(sidecar_relative_path="media/other.json")), ("additional approved edit", lambda p: p["approval_gates"]["edit"].update(status="approved", receipt="OK")), ("path traversal", lambda p: p["delivery"]["portable_handoff"]["assets"][0].update(media_relative_path="media/../product.mp4")), ("unicode path alias", lambda p: p["delivery"]["portable_handoff"]["assets"].append({"asset_id": "asset-alias", "media_sha256": "d" * 64, "media_relative_path": "MEDIA/Product.MP4", "sidecar_sha256": "e" * 64, "sidecar_relative_path": "MEDIA/Product.sidecar.json", "classification": {"original": False, "editable_project_dependency": False, "shared": False, "uncertain": False}})), ("stale integrity", lambda p: p["integrity"].update(visible_content_sha256="0" * 64)), ("unbound approval", lambda p: p["approval_gates"]["export"].update(bound_visible_content_sha256="0" * 64)), ("cleanup path", lambda p: p["cleanup_preflight"]["local_working_download_candidates"][0].update(path="media/product.mp4")), ("cleanup execute", lambda p: p["cleanup_preflight"].update(execute=True)), ("cleanup original", lambda p: p["delivery"]["portable_handoff"]["assets"][0]["classification"].update(original=True)), ("prohibition matches", lambda p: p["openclaw_prohibition"].update(matched_rule_ids=["rule-1"])), ("prohibition stale hash", lambda p: p["openclaw_prohibition"].update(bound_visible_content_sha256="0" * 64)), ("shop userinfo", lambda p: p["camee_tiktok_shop"].update(url="https://user@shop.tiktok.com/view/product/123456789012")), ("shop nonstandard port", lambda p: p["camee_tiktok_shop"].update(url="https://shop.tiktok.com:444/view/product/123456789012")), ("shop short id", lambda p: p["camee_tiktok_shop"].update(url="https://shop.tiktok.com/view/product/123")), ("shop bad id", lambda p: p["camee_tiktok_shop"].update(product_id="123")), ("shop stale hash", lambda p: p["camee_tiktok_shop"].update(bound_production_payload_sha256="0" * 64)))
    mutations += (("semantic description forged", lambda p: p["cuts"][0]["media_requirements"].update(canonical_description="freeform")), ("legacy component alias", lambda p: p.update(component_hash="0" * 64)), ("stale component hash", lambda p: p["component_hashes"].update(cuts_sha256="0" * 64)), ("caption editor missing", lambda p: p["captions"][0].pop("style")), ("QA axis missing", lambda p: p["design_quality_qa"]["axes"].pop()), ("manifest accounting missing", lambda p: p["manifest"][0].pop("limitations")), ("portable setup altered", lambda p: p["portable_setup"].update(setup_steps=["import_assets"])))
    mutations += (("source receipt mismatch", lambda p: p["cuts"][0]["matched_sidecar_receipt"].update(asset_id="asset-other")), ("additional source present", lambda p: p["cuts"][0].update(source_asset_id="asset-product", source_in=0.0, source_out=2.0)), ("manifest ref reordered", lambda p: p["manifest_ref"].append(dict(p["manifest_ref"][0]))), ("fact source SHA mismatch", lambda p: p["facts_used"][0]["material_refs"][0].update(sha256="0" * 64)), ("caption exceeds cut", lambda p: p["captions"][0].update(timeline_out=3.0)), ("tts exceeds cut", lambda p: p["tts"][0].update(timeline_out=3.0)), ("QA duplicate axis", lambda p: p["design_quality_qa"]["axes"].__setitem__(1, dict(p["design_quality_qa"]["axes"][0]))), ("QA total mismatch", lambda p: p["design_quality_qa"].update(total_score=1)), ("post set missing", lambda p: p.pop("post_set")))
    mutations += (("script exceeds cut", lambda p: p["script"][0].update(timeline_out=3.0)), ("fact non-verified", lambda p: p["facts_used"][0].update(classification="review_observation")), ("QA metric alias", lambda p: p["design_quality_qa"].update(metrics={"watch": "not_measured"})), ("manifest source alias", lambda p: p["manifest"][0].update(source_reference="legacy")), ("manifest insecure source", lambda p: p["manifest"][0].update(source_location="http://example.invalid/product")), ("manifest absolute source", lambda p: p["manifest"][0].update(source_location=chr(47) + "local/file")))
    mutations += (("time bool", lambda p: p["cuts"][0].update(timeline_in=True)), ("time string", lambda p: p["cuts"][0].update(timeline_in="0")), ("time none", lambda p: p["cuts"][0].update(timeline_in=None)), ("time NaN", lambda p: p["cuts"][0].update(timeline_in=float("nan"))), ("time infinity", lambda p: p["cuts"][0].update(timeline_out=float("inf"))), ("time negative", lambda p: p["cuts"][0].update(timeline_in=-0.1)), ("time zero", lambda p: p["cuts"][0].update(timeline_in=0.0, timeline_out=0.0)), ("time reversed", lambda p: p["cuts"][0].update(timeline_in=2.0, timeline_out=1.0)), ("source time string", lambda p: p["cuts"][0].update(source_in="0")), ("script time bool", lambda p: p["script"][0].update(timeline_in=True)), ("caption time NaN", lambda p: p["captions"][0].update(timeline_in=float("nan"))), ("TTS time infinity", lambda p: p["tts"][0].update(timeline_out=float("inf"))))
    huge = 10 ** 10000
    mutations += (("cut huge int", lambda p: p["cuts"][0].update(timeline_out=huge)), ("source huge int", lambda p: p["cuts"][0].update(source_out=huge)), ("script huge int", lambda p: p["script"][0].update(timeline_out=huge)), ("caption huge int", lambda p: p["captions"][0].update(timeline_out=huge)), ("TTS huge int", lambda p: p["tts"][0].update(timeline_out=huge)), ("cut over practical maximum", lambda p: p["cuts"][0].update(timeline_out=86401)))
    for name, mutate in mutations:
        payload = fixture(True, True) if name.startswith(("prohibition", "shop")) else fixture(tts=name != "no-TTS caption CTA", additional=name in {"additional approved edit", "additional source present"})
        mutate(payload)
        cases.append((name, payload, True))
    failed = [name for name, payload, reject in cases if bool(errors_for(payload)) != reject]
    if failed:
        raise AssertionError("self-test failed: " + ", ".join(failed))
    print(f"self-test passed: {len(cases)} cases")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("payload", nargs="?")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    if not args.payload:
        parser.error("payload is required unless --self-test is used")
    try:
        payload = json.loads(Path(args.payload).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"invalid input: {exc}", file=sys.stderr)
        return 2
    errors = errors_for(payload)
    if errors:
        print("INVALID")
        print("\n".join(f"- {error}" for error in errors))
        return 1
    print("VALID")
    return 0


if __name__ == "__main__":
    sys.exit(main())
