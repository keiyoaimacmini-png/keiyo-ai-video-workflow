#!/usr/bin/env python3
"""Strict, side-effect-free validator for a portable TikTok product-video payload."""

import argparse
import hashlib
import json
import math
import re
import sys
import unicodedata
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path, PurePosixPath
from urllib.parse import urlparse

MODEL_RE = re.compile(r"^AN-[A-Z0-9]{4,6}$")
SHA_RE = re.compile(r"^[0-9a-f]{64}$")
ASSET_RE = re.compile(r"^asset-[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
PRODUCT_PATH_RE = re.compile(r"^/view/product/([0-9]{12,})$")
CTA = "下からチェック！"
GATES = ("edit", "export", "cloud", "publish", "credit", "send")
ROOT = {"created_at", "manifest", "manifest_ref", "product_info", "product_settings", "goal_axis", "patterns", "facts_used", "hypotheses", "script", "script_review_receipt", "cuts", "captions", "tts", "narration_policy", "voice_policy", "final_visual_policy", "audio", "post_set", "design_quality_qa", "risk_register", "component_hashes", "portable_setup", "delivery", "approval_gates", "routing", "openclaw_prohibition", "camee_tiktok_shop", "integrity", "cleanup_preflight"}
ALIAS_KEYS = {"path", "source_path", "local_path", "file_path", "absolute_path", "asset_hashes", "asset_sha256", "requirements_hash", "required_media_description", "must_show", "must_not_show"}
# Japan Standard Time is permanently UTC+09:00. A fixed offset keeps the
# portable validator independent of the optional IANA tzdata package.
JST = timezone(timedelta(hours=9), name="Asia/Tokyo")
GOAL_AXES = {"watch_continuation", "comment_content_coupling", "reward_stimulation"}
VISIBILITY_ENUMS = {"full", "partial"}
SEMANTIC_KEYS = ("subject", "action", "composition", "product_visibility", "text_visibility")
SEMANTIC_ENUMS = {"action": {"static", "hold", "press", "use", "reveal"}, "composition": {"close_up", "medium", "overhead", "wide"}, "product_visibility": {"none", "full", "partial"}, "text_visibility": {"none", "product_label"}}
QA_MAX = {"hook": 15, "tempo": 10, "emotion": 10, "continuation_design": 15, "save_design": 10, "comment_design": 10, "share_design": 10, "purchase_path_design": 20}
NARRATIVE_ROLES = ("problem_or_hook", "product", "use_or_change", "result", "problem_resolution", "cta")
ORDINAL_MARKERS = ("①", "②", "③", "④", "⑤", "⑥", "⑦", "⑧", "⑨", "⑩", "⑪", "⑫", "⑬", "⑭", "⑮", "⑯", "⑰", "⑱", "⑲", "⑳")
VIDEO_MIME_BY_EXTENSION = {"mp4": "video/mp4", "mov": "video/quicktime", "webm": "video/webm"}


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def is_sha(value):
    return isinstance(value, str) and SHA_RE.fullmatch(value) is not None


def non_empty_string(value):
    return isinstance(value, str) and bool(value.strip())


def valid_time_range(start, end):
    def valid_time_value(value):
        if isinstance(value, bool):
            return False
        if isinstance(value, int):
            return 0 <= value <= 86400
        return isinstance(value, float) and math.isfinite(value) and 0 <= value <= 86400
    return valid_time_value(start) and valid_time_value(end) and start < end


def finite_number(value):
    return not isinstance(value, bool) and isinstance(value, (int, float)) and (not isinstance(value, float) or math.isfinite(value))


def same_number(left, right):
    return finite_number(left) and finite_number(right) and left == right


def decimal_duration(start, end):
    """Compare user-authored decimal timestamps without binary-float drift."""
    return Decimal(str(end)) - Decimal(str(start))


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
    return ";".join(f"{key}={semantics.get(key)}" for key in SEMANTIC_KEYS)


def normalized_spoken_text(value):
    if not isinstance(value, str):
        return None
    return re.sub(r"\s+", "", value)


def production_subject(payload):
    subject = {key: value for key, value in payload.items() if key not in {"integrity", "approval_gates", "openclaw_prohibition", "camee_tiktok_shop"}}
    gates = payload.get("approval_gates")
    if isinstance(gates, dict):
        plan_fields = ("checkpoint", "authorized_actions", "max_first_attempt_tts_count", "drive_delivery_requested", "exact_destination_scope_confirmed", "destination_scope_subject", "destination_scope_sha256", "original_request_subject", "original_request_sha256", "external_scope_subject", "external_scope_sha256")
        subject["authorization_plan"] = {gate: {key: gates[gate].get(key) for key in plan_fields if key in gates[gate]} for gate in GATES if isinstance(gates.get(gate), dict)}
    delivery = subject.get("delivery")
    if isinstance(delivery, dict):
        delivery = dict(delivery)
        delivery["export_status"] = "pending"
        delivery.pop("export_receipt", None)
        delivery["drive_status"] = "pending" if delivery.get("drive_status") in {"pending", "completed"} else "not_requested"
        delivery.pop("drive_receipt", None)
        subject["delivery"] = delivery
    return subject


def visible_subject(payload):
    return {key: payload[key] for key in ("script", "captions", "tts", "post_set") if key in payload}


def expected_hashes(payload):
    return digest(production_subject(payload)), digest(visible_subject(payload))


def errors_for(payload, trusted_product_settings=None):
    errors = []
    unknown(payload, ROOT, "payload", errors)
    assets, model = check_model_and_assets(payload, errors)
    check_product_settings(payload, model, trusted_product_settings, errors)
    cut_ids, additional_needed = check_cuts(payload, assets, model, errors)
    check_canonical_fields(payload, cut_ids, errors)
    check_script_review(payload, assets, cut_ids, errors)
    check_distinct_caption_assets(payload, assets, errors)
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
        errors.append("product_info.product_model must match ^AN-[A-Z0-9]{4,6}$")
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


def check_product_settings(payload, model, trusted, errors):
    hold = "HOLD_PRODUCT_VIDEO_SETTINGS"
    settings = payload.get("product_settings")
    fields = {"status", "product_model", "manifest_material_id", "source_location", "settings_sha256", "schema_version", "resolved_settings", "resolved_values_sha256"}
    resolved_fields = {"cta_text", "default_voice_preset", "base_speed", "fallback_speed_min", "fallback_speed_max", "caption_template_resource_id", "final_cut_asset_id", "final_source_in", "final_source_out"}
    unknown(settings, fields, "product_settings", errors)
    if not isinstance(settings, dict) or set(settings) != fields:
        errors.append(f"product_settings must use the canonical receipt schema; {hold}")
        return

    manifest = payload.get("manifest") if isinstance(payload.get("manifest"), list) else []
    settings_materials = [item for item in manifest if isinstance(item, dict) and item.get("kind") == "product_video_settings"]
    if len(settings_materials) != 1:
        errors.append(f"manifest must contain exactly one product_video_settings material; {hold}")
        return
    material = settings_materials[0]
    expected_location = f"config/product_video_settings_{model}.v1.json" if isinstance(model, str) else None
    receipt_matches_material = (
        settings.get("manifest_material_id") == material.get("material_id")
        and settings.get("source_location") == material.get("source_location")
        and settings.get("settings_sha256") == material.get("sha256")
    )
    material_verified = (
        material.get("source_location") == expected_location
        and normalized_path(material.get("source_location")) == normalized_path(expected_location)
        and material.get("access_status") == "available"
        and material.get("usage_status") == "approved"
        and material.get("analysis_status") == "complete"
        and material.get("observed_product_models") == [model]
        and is_sha(material.get("sha256"))
    )
    if settings.get("status") != "verified" or settings.get("product_model") != model or settings.get("schema_version") != "1" or not receipt_matches_material or not material_verified:
        errors.append(f"product settings model, path, manifest receipt, or SHA-256 mismatch; {hold}")

    resolved = settings.get("resolved_settings")
    unknown(resolved, resolved_fields, "product_settings.resolved_settings", errors)
    if not isinstance(resolved, dict) or set(resolved) != resolved_fields or settings.get("resolved_values_sha256") != digest(resolved):
        errors.append(f"resolved product settings must be exact and hash-bound; {hold}")
        return
    trusted_fields = {"product_model", "source_location", "settings_sha256", "schema_version", "resolved_settings"}
    if not isinstance(trusted, dict) or set(trusted) != trusted_fields or trusted.get("product_model") != model or trusted.get("source_location") != expected_location or trusted.get("settings_sha256") != settings.get("settings_sha256") or trusted.get("schema_version") != settings.get("schema_version") or trusted.get("resolved_settings") != resolved:
        errors.append(f"product settings receipt does not match the trusted canonical file; {hold}")
    numeric = [resolved.get("base_speed"), resolved.get("fallback_speed_min"), resolved.get("fallback_speed_max"), resolved.get("final_source_in"), resolved.get("final_source_out")]
    if any(not finite_number(value) for value in numeric) or resolved.get("cta_text") != CTA or resolved.get("default_voice_preset") != "ホリデーツイスト" or resolved.get("base_speed") != 1.0 or resolved.get("fallback_speed_min") != 1.2 or resolved.get("fallback_speed_max") != 1.5 or not isinstance(resolved.get("caption_template_resource_id"), str) or not resolved["caption_template_resource_id"].strip() or not isinstance(resolved.get("final_cut_asset_id"), str) or not valid_time_range(resolved.get("final_source_in"), resolved.get("final_source_out")):
        errors.append(f"resolved product settings contain unsupported canonical values; {hold}")

    voice = payload.get("voice_policy")
    if isinstance(voice, dict) and voice.get("source") == "default" and voice.get("preset") != f"CapCut official {resolved.get('default_voice_preset')}":
        errors.append(f"default voice does not match product settings; {hold}")
    narration = payload.get("narration_policy")
    if isinstance(narration, dict):
        common_speed = narration.get("common_speed")
        if narration.get("mode") == "required" and (not finite_number(common_speed) or not (resolved.get("base_speed") == common_speed or resolved.get("fallback_speed_min") <= common_speed <= resolved.get("fallback_speed_max"))):
            errors.append(f"common narration speed is outside product settings; {hold}")
        if narration.get("mode") == "none" and common_speed is not None:
            errors.append(f"no-narration mode must not carry a product speed; {hold}")


def load_trusted_product_settings(settings_root, model):
    if not isinstance(model, str) or not MODEL_RE.fullmatch(model):
        return None
    relative_path = f"config/product_video_settings_{model}.v1.json"
    root = Path(settings_root).resolve()
    path = root.joinpath(*PurePosixPath(relative_path).parts)
    try:
        resolved_path = path.resolve(strict=True)
        if path.is_symlink() or not resolved_path.is_file() or root not in resolved_path.parents:
            return None
        raw = resolved_path.read_bytes()
        document = json.loads(raw.decode("utf-8"))
        resolved = {
            "cta_text": document["cta"]["text"],
            "default_voice_preset": document["narration"]["default_voice_preset"],
            "base_speed": document["narration"]["base_speed"],
            "fallback_speed_min": document["narration"]["fallback_speed_min"],
            "fallback_speed_max": document["narration"]["fallback_speed_max"],
            "caption_template_resource_id": document["caption_template"]["resource_id"],
            "final_cut_asset_id": document["final_cut_block"]["asset_id"],
            "final_source_in": document["final_cut_block"]["source_in"],
            "final_source_out": document["final_cut_block"]["source_out"],
        }
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError):
        return None
    if document.get("product_model") != model:
        return None
    return {"product_model": model, "source_location": relative_path, "settings_sha256": hashlib.sha256(raw).hexdigest(), "schema_version": str(document.get("schema_version")), "resolved_settings": resolved}


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


def portable_asset_id_from_catalog(value):
    if not isinstance(value, str) or not value:
        return None
    if ASSET_RE.fullmatch(value):
        return value
    candidate = "asset-" + value.casefold()
    return candidate if ASSET_RE.fullmatch(candidate) else None


def valid_source_location(value):
    if not isinstance(value, str):
        return False
    parsed = urlparse(value)
    return (parsed.scheme == "https" and bool(parsed.hostname) and parsed.username is None and parsed.password is None) or normalized_path(value) is not None


def check_assets(payload, errors):
    delivery = payload.get("delivery")
    unknown(delivery, {"naming_jst_date", "capcut_cloud_project_path", "export_status", "export_receipt", "drive_status", "drive_receipt", "portable_handoff"}, "delivery", errors)
    receipt = delivery.get("export_receipt") if isinstance(delivery, dict) else None
    if receipt is not None:
        unknown(receipt, {"exported_at", "production_ordinal", "completed_video_basename", "file_extension", "mime_type", "completed_video_filename", "prior_completed_exports"}, "delivery.export_receipt", errors)
    drive_receipt = delivery.get("drive_receipt") if isinstance(delivery, dict) else None
    if drive_receipt is not None:
        unknown(drive_receipt, {"file_name", "mime_type", "byte_size", "file_id_sha256", "parent_scope_sha256", "readback_at", "receipt_sha256"}, "delivery.drive_receipt", errors)
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


def check_cuts(payload, assets, model, errors):
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
        if not isinstance(editor, dict) or not isinstance(editor.get("track"), str) or not isinstance(editor.get("layer"), int) or editor.get("transition") not in {"cut", "dissolve", "none"} or editor.get("zoom") not in {"none", "in", "out"} or editor.get("effect") not in {"none", "highlight"} or not finite_number(editor.get("speed")) or editor.get("speed") <= 0:
            errors.append(f"{label}.editor must use canonical timeline fields")
        requirements = cut.get("media_requirements")
        unknown(requirements, {"semantics", "canonical_description", "must_show", "must_not_show"}, f"{label}.media_requirements", errors)
        semantics = requirements.get("semantics") if isinstance(requirements, dict) else None
        unknown(semantics, set(SEMANTIC_KEYS), f"{label}.media_requirements.semantics", errors)
        if not isinstance(semantics, dict) or set(semantics) != set(SEMANTIC_KEYS) or not non_empty_string(semantics.get("subject")) or any(semantics.get(key) not in values for key, values in SEMANTIC_ENUMS.items()) or requirements.get("canonical_description") != semantic_description(semantics):
            errors.append(f"{label}.media_requirements requires a non-empty observed subject and canonical controlled semantics description")
        for field in ("must_show", "must_not_show"):
            values = requirements.get(field) if isinstance(requirements, dict) else None
            if not isinstance(values, list) or (field == "must_show" and not values):
                errors.append(f"{label}.media_requirements.{field} must be structured")
            elif field == "must_show" and any(not isinstance(item, dict) or set(item) != {"subject", "visibility"} or not non_empty_string(item.get("subject")) or item.get("visibility") not in VISIBILITY_ENUMS for item in values):
                errors.append(f"{label}.media_requirements.must_show requires a non-empty observed subject and controlled visibility")
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
    if len(cut_ranges) == len(cut_ids) and cut_ids:
        ordered_ranges = [cut_ranges.get(cut_id) for cut_id in cut_ids]
        if ordered_ranges[0][0] != 0 or any(ordered_ranges[index - 1][1] != ordered_ranges[index][0] for index in range(1, len(ordered_ranges))):
            errors.append("cuts must be chronological, contiguous, and start at zero")
    exact_closure(payload.get("script"), cut_ids, "script", "dialogue", {"cut_id", "dialogue", "timeline_in", "timeline_out", "narrative_role", "narration_target", "fact_refs", "media_evidence_asset_id"}, cut_ranges, errors)
    exact_closure(payload.get("captions"), cut_ids, "captions", "text", {"cut_id", "text", "timeline_in", "timeline_out", "track", "layer", "position", "style", "line_breaks", "template_requirement", "narration_target"}, cut_ranges, errors)
    closure = [("script", "dialogue"), ("captions", "text")]
    scripts = payload.get("script") if isinstance(payload.get("script"), list) else []
    narration_cut_ids = [item.get("cut_id") for item in scripts if isinstance(item, dict) and item.get("narration_target") is True]
    if "tts" in payload:
        exact_closure(payload.get("tts"), narration_cut_ids, "tts", "text", {"cut_id", "text", "voice", "speed", "pitch", "voice_processing", "timeline_in", "timeline_out", "duration_status", "track", "layer"}, cut_ranges, errors)
        closure.append(("tts", "text"))
    check_narration_alignment(payload, cuts, cut_ids, errors)
    check_final_visual_policy(payload, cuts, cut_ids, errors)
    if cut_ids:
        final_id = cut_ids[-1]
        for label, field in closure:
            records = payload.get(label, [])
            record = next((item for item in records if isinstance(item, dict) and item.get("cut_id") == final_id), None)
            if not isinstance(record, dict) or record.get(field) != CTA:
                errors.append(f"final {label} {field} must exactly equal the required CTA")
    if isinstance(model, str):
        for label, field in closure:
            for index, record in enumerate(payload.get(label, [])):
                value = record.get(field) if isinstance(record, dict) else None
                if isinstance(value, str) and model.casefold() in unicodedata.normalize("NFKC", value).casefold():
                    errors.append(f"{label}[{index}].{field} must omit the product model from video-visible content")
    return cut_ids, additional_needed


def check_distinct_caption_assets(payload, assets, errors):
    """Require a distinct source file for each canonical user-visible caption."""
    cuts = payload.get("cuts") if isinstance(payload.get("cuts"), list) else []
    captions = payload.get("captions") if isinstance(payload.get("captions"), list) else []
    cut_by_id = {cut.get("cut_id"): cut for cut in cuts if isinstance(cut, dict) and isinstance(cut.get("cut_id"), str)}
    source_ids, media_shas = [], []
    for caption in captions:
        if not isinstance(caption, dict) or not isinstance(caption.get("cut_id"), str):
            continue
        cut = cut_by_id.get(caption["cut_id"])
        if not isinstance(cut, dict):
            continue
        if cut.get("additional_asset_required") is True and cut.get("source_asset_id") is None:
            continue
        source_asset_id = cut.get("source_asset_id")
        if not isinstance(source_asset_id, str):
            continue
        source_ids.append(source_asset_id)
        asset = assets.get(source_asset_id) if isinstance(assets, dict) else None
        media_sha = asset.get("media_sha256") if isinstance(asset, dict) else None
        if isinstance(media_sha, str):
            media_shas.append(media_sha)
    if len(source_ids) != len(set(source_ids)):
        errors.append("HOLD_DISTINCT_ASSET_PER_CAPTION: each caption cut must use a distinct source_asset_id")
    if len(media_shas) != len(set(media_shas)):
        errors.append("HOLD_DISTINCT_ASSET_PER_CAPTION: each caption cut must use a distinct portable asset media_sha256")


def check_script_review(payload, assets, cut_ids, errors):
    receipt = payload.get("script_review_receipt")
    fields = {"selected_concept", "inspection_artifact_relative_path", "location_label", "cuts"}
    unknown(receipt, fields, "script_review_receipt", errors)
    if not isinstance(receipt, dict) or set(receipt) != fields or not isinstance(receipt.get("selected_concept"), str) or not receipt["selected_concept"].strip() or normalized_path(receipt.get("inspection_artifact_relative_path")) is None or not isinstance(receipt.get("location_label"), str) or not receipt["location_label"].strip() or not isinstance(receipt.get("cuts"), list):
        errors.append("script_review_receipt must be a portable canonical checkpoint-1 record")
        return
    scripts = {item.get("cut_id"): item for item in payload.get("script", []) if isinstance(item, dict)}
    captions = {item.get("cut_id"): item for item in payload.get("captions", []) if isinstance(item, dict)}
    cuts = {item.get("cut_id"): item for item in payload.get("cuts", []) if isinstance(item, dict)}
    facts = {item.get("fact_id") for item in payload.get("facts_used", []) if isinstance(item, dict)}
    seen = []
    for index, item in enumerate(receipt["cuts"]):
        label = f"script_review_receipt.cuts[{index}]"
        item_fields = {"cut_id", "dialogue", "line_breaks", "source_asset_id", "source_in", "source_out", "cut_duration", "unicode_codepoint_count", "estimated_read_seconds", "fact_refs", "media_evidence_asset_id"}
        if not isinstance(item, dict) or set(item) != item_fields:
            errors.append(f"{label} must use the canonical script-review schema")
            continue
        cut_id = item.get("cut_id"); script = scripts.get(cut_id); caption = captions.get(cut_id); cut = cuts.get(cut_id)
        asset_invalid = cut.get("source_asset_id") is not None and item.get("source_asset_id") not in assets
        duration_matches = valid_time_range(cut.get("timeline_in"), cut.get("timeline_out")) and finite_number(item.get("cut_duration")) and Decimal(str(item.get("cut_duration"))) == decimal_duration(cut["timeline_in"], cut["timeline_out"])
        if not isinstance(cut_id, str) or not isinstance(script, dict) or not isinstance(caption, dict) or not isinstance(cut, dict) or item.get("dialogue") != script.get("dialogue") or item.get("line_breaks") != caption.get("line_breaks") or item.get("source_asset_id") != cut.get("source_asset_id") or item.get("media_evidence_asset_id") != cut.get("source_asset_id") or script.get("media_evidence_asset_id") != cut.get("source_asset_id") or item.get("source_in") != cut.get("source_in") or item.get("source_out") != cut.get("source_out") or not duration_matches or item.get("unicode_codepoint_count") != len(script.get("dialogue", "")) or not finite_number(item.get("estimated_read_seconds")) or item["estimated_read_seconds"] <= 0 or item["estimated_read_seconds"] > item["cut_duration"] or item.get("fact_refs") != script.get("fact_refs") or not isinstance(item.get("fact_refs"), list) or not item["fact_refs"] or any(ref not in facts for ref in item["fact_refs"]) or asset_invalid:
            errors.append(f"{label} must exactly evidence the reviewed script, verified facts, and selected source")
        seen.append(cut_id)
    if seen != cut_ids or len(seen) != len(set(seen)):
        errors.append("script_review_receipt must close exactly over script cuts in order")


def check_overflow_evidence(payload, strategy, common_speed, overflow_cut_ids, evidence, cuts, cut_ids, scripts, errors):
    target_ids = [item.get("cut_id") for item in scripts if isinstance(item, dict) and item.get("narration_target") is True]
    expected_steps = {
        "normal": [],
        "common_tts_acceleration": ["common_tts_acceleration"],
        "longer_verified_distinct_source": ["common_tts_acceleration", "longer_verified_distinct_source"],
        "slow_video_and_caption": ["common_tts_acceleration", "longer_verified_distinct_source", "slow_video_and_caption"],
    }.get(strategy)
    if not isinstance(evidence, list) or expected_steps is None or [item.get("step") if isinstance(item, dict) else None for item in evidence] != expected_steps:
        errors.append("overflow_evidence must prove the exact ordered TTS acceleration, longer-source, slowdown sequence")
        return
    if not evidence:
        return
    common = evidence[0]
    common_fields = {"step", "status", "common_speed", "affected_cut_ids", "evidence_sha256"}
    expected_common_status = "applied_sufficient" if strategy == "common_tts_acceleration" else "applied_insufficient"
    common_subject = {key: common.get(key) for key in common_fields - {"evidence_sha256"}}
    if set(common) != common_fields or common.get("status") != expected_common_status or common.get("common_speed") != common_speed or common.get("affected_cut_ids") != target_ids or common.get("evidence_sha256") != digest(common_subject):
        errors.append("overflow_evidence common acceleration must cover every narration target at the policy speed")
    if len(evidence) >= 2:
        longer = evidence[1]
        longer_fields = {"step", "status", "cut_ids", "prior_asset_ids", "prior_media_sha256", "prior_sidecar_sha256", "prior_source_in", "prior_source_out", "prior_available_seconds", "prior_evidence_sha256", "replacement_available_seconds", "replacement_asset_ids", "evidence_sha256"}
        expected_longer_status = "applied_sufficient" if strategy == "longer_verified_distinct_source" else "applied_insufficient"
        longer_subject = {key: longer.get(key) for key in longer_fields - {"evidence_sha256"}}
        if set(longer) != longer_fields or longer.get("status") != expected_longer_status or longer.get("cut_ids") != overflow_cut_ids or longer.get("evidence_sha256") != digest(longer_subject):
            errors.append("overflow_evidence longer-source step has invalid scope, status, or receipt")
        else:
            prior_assets = longer.get("prior_asset_ids")
            prior_media = longer.get("prior_media_sha256")
            prior_sidecars = longer.get("prior_sidecar_sha256")
            prior_in = longer.get("prior_source_in")
            prior_out = longer.get("prior_source_out")
            prior = longer.get("prior_available_seconds")
            prior_hashes = longer.get("prior_evidence_sha256")
            replacement = longer.get("replacement_available_seconds")
            assets = longer.get("replacement_asset_ids")
            portable_assets = {item.get("asset_id"): item for item in payload.get("delivery", {}).get("portable_handoff", {}).get("assets", []) if isinstance(item, dict) and isinstance(item.get("asset_id"), str)}
            if not all(isinstance(value, dict) and set(value) == set(overflow_cut_ids) for value in (prior_assets, prior_media, prior_sidecars, prior_in, prior_out, prior, prior_hashes, replacement, assets)):
                errors.append("overflow_evidence longer-source mappings must close over affected cuts")
            else:
                for cut_id in overflow_cut_ids:
                    cut = cuts[cut_ids.index(cut_id)] if cut_id in cut_ids else {}
                    available = decimal_duration(cut.get("source_in"), cut.get("source_out")) if valid_time_range(cut.get("source_in"), cut.get("source_out")) else None
                    prior_asset = portable_assets.get(prior_assets[cut_id])
                    prior_subject = {"cut_id": cut_id, "asset_id": prior_assets[cut_id], "media_sha256": prior_media[cut_id], "sidecar_sha256": prior_sidecars[cut_id], "source_in": prior_in[cut_id], "source_out": prior_out[cut_id]}
                    prior_duration = decimal_duration(prior_in[cut_id], prior_out[cut_id]) if valid_time_range(prior_in[cut_id], prior_out[cut_id]) else None
                    current_asset_ids = {item.get("source_asset_id") for item in cuts if isinstance(item, dict) and isinstance(item.get("source_asset_id"), str)}
                    current_media_shas = {portable_assets[asset_id].get("media_sha256") for asset_id in current_asset_ids if asset_id in portable_assets}
                    if not isinstance(prior_asset, dict) or prior_asset.get("media_sha256") != prior_media[cut_id] or prior_asset.get("sidecar_sha256") != prior_sidecars[cut_id] or prior_assets[cut_id] in current_asset_ids or prior_media[cut_id] in current_media_shas or prior_duration is None or not finite_number(prior[cut_id]) or Decimal(str(prior[cut_id])) != prior_duration or prior_hashes[cut_id] != digest(prior_subject) or not finite_number(replacement[cut_id]) or prior[cut_id] <= 0 or replacement[cut_id] <= prior[cut_id] or available != Decimal(str(replacement[cut_id])) or assets[cut_id] != cut.get("source_asset_id"):
                        errors.append(f"overflow_evidence {cut_id} must prove a longer verified replacement source")
    if len(evidence) == 3:
        slow = evidence[2]
        slow_fields = {"step", "status", "cut_ids", "video_speeds", "evidence_sha256"}
        speeds = slow.get("video_speeds") if isinstance(slow, dict) else None
        slow_subject = {key: slow.get(key) for key in slow_fields - {"evidence_sha256"}} if isinstance(slow, dict) else {}
        if not isinstance(slow, dict) or set(slow) != slow_fields or slow.get("status") != "applied_sufficient" or slow.get("cut_ids") != overflow_cut_ids or slow.get("evidence_sha256") != digest(slow_subject) or not isinstance(speeds, dict) or set(speeds) != set(overflow_cut_ids):
            errors.append("overflow_evidence slowdown step has invalid scope, status, or receipt")
        else:
            for cut_id in overflow_cut_ids:
                cut = cuts[cut_ids.index(cut_id)] if cut_id in cut_ids else {}
                speed = speeds[cut_id]
                editor_speed = cut.get("editor", {}).get("speed") if isinstance(cut.get("editor"), dict) else None
                if not finite_number(speed) or not 0 < speed < 1 or speed != editor_speed or not valid_time_range(cut.get("source_in"), cut.get("source_out")) or not valid_time_range(cut.get("timeline_in"), cut.get("timeline_out")):
                    errors.append(f"overflow_evidence {cut_id} must use the read-back slowdown speed")
                    continue
                expected_duration = float(decimal_duration(cut["source_in"], cut["source_out"])) / speed
                actual_duration = float(decimal_duration(cut["timeline_in"], cut["timeline_out"]))
                if not math.isclose(expected_duration, actual_duration, rel_tol=0, abs_tol=1e-6):
                    errors.append(f"overflow_evidence {cut_id} slowdown must extend timeline duration from the verified source range")


def check_narration_alignment(payload, cuts, cut_ids, errors):
    policy = payload.get("narration_policy")
    policy_fields = {"mode", "scope", "user_explicit", "receipt", "timing_strategy", "common_speed", "overflow_cut_ids", "overflow_reason", "overflow_evidence"}
    unknown(policy, policy_fields, "narration_policy", errors)
    if not isinstance(policy, dict) or set(policy) != policy_fields:
        errors.append("narration_policy must use the canonical v4 schema")
        return
    mode = policy.get("mode")
    if mode not in {"required", "none"} or policy.get("scope") != "video" or not isinstance(policy.get("user_explicit"), bool) or not isinstance(policy.get("receipt"), str):
        errors.append("narration_policy identity fields are invalid")
        return

    scripts = payload.get("script") if isinstance(payload.get("script"), list) else []
    captions = payload.get("captions") if isinstance(payload.get("captions"), list) else []
    tts_records = payload.get("tts") if isinstance(payload.get("tts"), list) else []
    by_script = {record.get("cut_id"): record for record in scripts if isinstance(record, dict)}
    by_caption = {record.get("cut_id"): record for record in captions if isinstance(record, dict)}
    by_tts = {record.get("cut_id"): record for record in tts_records if isinstance(record, dict)}

    roles = [record.get("narrative_role") for record in scripts if isinstance(record, dict)]
    compressed_roles = [role for index, role in enumerate(roles) if index == 0 or role != roles[index - 1]]
    if compressed_roles != list(NARRATIVE_ROLES):
        errors.append("script must complete problem_or_hook, product, use_or_change, result, problem_resolution, CTA in order")

    if mode == "none":
        if policy.get("user_explicit") is not True or not policy.get("receipt").strip() or policy.get("timing_strategy") != "not_applicable" or policy.get("common_speed") is not None or policy.get("overflow_cut_ids") != [] or policy.get("overflow_reason") != "" or policy.get("overflow_evidence") != []:
            errors.append("narration none requires an explicit video-scoped user receipt")
        if "tts" in payload or "voice_policy" in payload:
            errors.append("narration none forbids TTS and voice_policy")
        if any(record.get("narration_target") is not False for record in scripts + captions if isinstance(record, dict)):
            errors.append("narration none requires all script and caption records to be non-targets")
    else:
        strategy = policy.get("timing_strategy")
        if strategy not in {"normal", "common_tts_acceleration", "longer_verified_distinct_source", "slow_video_and_caption"}:
            errors.append("required narration needs a canonical timing strategy")
        speed = policy.get("common_speed")
        speed_is_number = not isinstance(speed, bool) and isinstance(speed, (int, float))
        speed_is_finite = speed_is_number and (not isinstance(speed, float) or math.isfinite(speed))
        overflow_cut_ids = policy.get("overflow_cut_ids")
        valid_overflow_ids = isinstance(overflow_cut_ids, list) and len(overflow_cut_ids) == len(set(overflow_cut_ids)) and all(cut_id in cut_ids for cut_id in overflow_cut_ids)
        overflow_evidence = policy.get("overflow_evidence")
        if strategy == "normal" and (not speed_is_finite or speed != 1.0 or overflow_cut_ids != [] or policy.get("overflow_reason") != ""):
            errors.append("normal narration must use 1.0x without overflow state")
        if strategy == "common_tts_acceleration" and (not speed_is_finite or not 1.2 <= speed <= 1.5 or overflow_cut_ids != [] or not isinstance(policy.get("overflow_reason"), str) or not policy.get("overflow_reason").strip()):
            errors.append("common TTS acceleration needs one 1.2x-1.5x speed and an overflow reason")
        if strategy in {"longer_verified_distinct_source", "slow_video_and_caption"} and (not speed_is_finite or not 1.2 <= speed <= 1.5 or not valid_overflow_ids or not overflow_cut_ids or not isinstance(policy.get("overflow_reason"), str) or not policy.get("overflow_reason").strip()):
            errors.append("post-acceleration overflow needs common 1.2x-1.5x speed, affected cuts, and a reason")
        if strategy == "slow_video_and_caption":
            if any(cut_id == cut_ids[-1] or not isinstance(cuts[cut_ids.index(cut_id)], dict) or not finite_number(cuts[cut_ids.index(cut_id)].get("editor", {}).get("speed")) or not 0 < cuts[cut_ids.index(cut_id)]["editor"]["speed"] < 1.0 for cut_id in overflow_cut_ids if cut_id in cut_ids):
                errors.append("slow_video_and_caption must slow only affected non-final verified cuts")
        check_overflow_evidence(payload, strategy, speed, overflow_cut_ids, overflow_evidence, cuts, cut_ids, scripts, errors)
        if not any(record.get("narration_target") is True for record in scripts if isinstance(record, dict)) or by_script.get(cut_ids[-1], {}).get("narration_target") is not True:
            errors.append("required narration must target at least one caption and the final CTA")
        voice_policy = payload.get("voice_policy")
        voice_fields = {"preset", "source", "user_explicit", "receipt", "pitch", "voice_processing"}
        unknown(voice_policy, voice_fields, "voice_policy", errors)
        if not isinstance(voice_policy, dict) or set(voice_policy) != voice_fields:
            errors.append("required narration needs canonical voice_policy")
            voice_policy = {}
        source = voice_policy.get("source")
        if source == "default":
            if voice_policy.get("preset") != "CapCut official ホリデーツイスト" or voice_policy.get("user_explicit") is not False or voice_policy.get("receipt") != "default":
                errors.append("default voice must be CapCut official ホリデーツイスト")
        elif source == "user_override":
            if voice_policy.get("user_explicit") is not True or not isinstance(voice_policy.get("receipt"), str) or not voice_policy.get("receipt").strip() or not isinstance(voice_policy.get("preset"), str) or not voice_policy.get("preset").strip():
                errors.append("voice override requires an explicit user receipt")
        else:
            errors.append("voice_policy.source must be default or user_override")
        pitch = voice_policy.get("pitch")
        if isinstance(pitch, bool) or not isinstance(pitch, (int, float)) or (isinstance(pitch, float) and not math.isfinite(pitch)) or not isinstance(voice_policy.get("voice_processing"), str):
            errors.append("voice_policy pitch and processing are invalid")

    for index, cut_id in enumerate(cut_ids):
        cut = cuts[index] if index < len(cuts) and isinstance(cuts[index], dict) else {}
        script, caption = by_script.get(cut_id), by_caption.get(cut_id)
        if not isinstance(script, dict) or not isinstance(caption, dict):
            continue
        if script.get("narrative_role") not in NARRATIVE_ROLES or not isinstance(script.get("narration_target"), bool) or caption.get("narration_target") is not script.get("narration_target"):
            errors.append(f"{cut_id} needs matching narrative role and narration-target metadata")
        if normalized_spoken_text(script.get("dialogue")) != normalized_spoken_text(caption.get("text")):
            errors.append(f"{cut_id} script and caption wording must match")
        cut_start, cut_end = cut.get("timeline_in"), cut.get("timeline_out")
        if script.get("timeline_in") != cut_start or caption.get("timeline_in") != cut_start:
            errors.append(f"{cut_id} script and caption must start at the cut start")
        tts = by_tts.get(cut_id)
        if script.get("narration_target") is False:
            if tts is not None:
                errors.append(f"{cut_id} non-narrated caption forbids TTS")
            continue
        if mode != "required" or not isinstance(tts, dict):
            if mode == "required":
                errors.append(f"{cut_id} narration-target caption needs TTS")
            continue
        if normalized_spoken_text(script.get("dialogue")) != normalized_spoken_text(tts.get("text")):
            errors.append(f"{cut_id} script, caption, and TTS wording must match")
        if tts.get("timeline_in") != cut_start:
            errors.append(f"{cut_id} TTS must start at the cut start")
        if index < len(cut_ids) - 1 and (script.get("timeline_out") != cut_end or caption.get("timeline_out") != cut_end or tts.get("timeline_out") != cut_end):
            errors.append(f"{cut_id} non-final cut, caption, and TTS must share one end")
        voice_policy = payload.get("voice_policy") if isinstance(payload.get("voice_policy"), dict) else {}
        if tts.get("voice") != voice_policy.get("preset") or not same_number(tts.get("speed"), policy.get("common_speed")) or not same_number(tts.get("pitch"), voice_policy.get("pitch")) or tts.get("voice_processing") != voice_policy.get("voice_processing"):
            errors.append(f"{cut_id} TTS must match the common voice and timing policies")


def check_final_visual_policy(payload, cuts, cut_ids, errors):
    policy = payload.get("final_visual_policy")
    fields = {"status", "cut_id", "asset_id", "catalog_asset_id", "mode", "source_duration", "approved_source_in", "approved_source_out", "user_explicit", "receipt", "settings_sha256", "common_narration_speed"}
    unknown(policy, fields, "final_visual_policy", errors)
    if not isinstance(policy, dict) or set(policy) != fields or not cut_ids or policy.get("cut_id") != cut_ids[-1]:
        errors.append("final_visual_policy must use the canonical v4 schema and bind the final cut")
        return
    final = cuts[-1] if cuts and isinstance(cuts[-1], dict) else {}
    settings = payload.get("product_settings") if isinstance(payload.get("product_settings"), dict) else {}
    resolved = settings.get("resolved_settings") if isinstance(settings.get("resolved_settings"), dict) else {}
    narration = payload.get("narration_policy") if isinstance(payload.get("narration_policy"), dict) else {}
    if policy.get("settings_sha256") != settings.get("settings_sha256") or policy.get("common_narration_speed") != narration.get("common_speed"):
        errors.append("final visual reusable block must bind the settings SHA-256 and common narration speed; HOLD_PRODUCT_VIDEO_SETTINGS")
    if policy.get("catalog_asset_id") != resolved.get("final_cut_asset_id"):
        errors.append("final visual reusable block must preserve the canonical catalog asset ID; HOLD_PRODUCT_VIDEO_SETTINGS")
    if policy.get("status") == "hold":
        if final.get("additional_asset_required") is not True or policy.get("asset_id") is not None or policy.get("mode") != "hold" or any(policy.get(key) is not None for key in ("source_duration", "approved_source_in", "approved_source_out")) or policy.get("user_explicit") is not False or policy.get("receipt") != "HOLD_FINAL_VISUAL_NOT_VERIFIED":
            errors.append("held final visual must remain an explicit canonical asset hold")
        return
    if policy.get("status") != "verified" or policy.get("mode") not in {"full_source", "approved_long_range"} or policy.get("user_explicit") is not True or not isinstance(policy.get("receipt"), str) or not policy.get("receipt").strip():
        errors.append("verified final visual needs an explicit user-approved long/full receipt")
        return
    if policy.get("asset_id") != portable_asset_id_from_catalog(resolved.get("final_cut_asset_id")) or policy.get("approved_source_in") != resolved.get("final_source_in") or policy.get("approved_source_out") != resolved.get("final_source_out"):
        errors.append("final visual reusable block must match resolved product settings; HOLD_PRODUCT_VIDEO_SETTINGS")
    values = [policy.get("source_duration"), policy.get("approved_source_in"), policy.get("approved_source_out")]
    if any(isinstance(value, bool) or not isinstance(value, (int, float)) or (isinstance(value, float) and not math.isfinite(value)) for value in values) or not 0 <= values[1] < values[2] <= values[0]:
        errors.append("final visual source duration/range is invalid")
        return
    final_editor_speed = final.get("editor", {}).get("speed")
    if policy.get("asset_id") != final.get("source_asset_id") or final.get("source_in") != values[1] or final.get("source_out") != values[2] or not finite_number(final_editor_speed) or final_editor_speed != 1.0:
        errors.append("final visual policy must bind the actual unsped source range")
    if policy.get("mode") == "full_source" and (values[1] != 0 or values[2] != values[0]):
        errors.append("full-source final visual must use the complete source")
    if valid_time_range(final.get("timeline_in"), final.get("timeline_out")) and decimal_duration(final.get("timeline_in"), final.get("timeline_out")) != decimal_duration(values[1], values[2]):
        errors.append("final visual timeline duration must preserve the approved source range")


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
            template_requirement = record.get("template_requirement")
            if label == "captions" and (record.get("track") != "caption" or not isinstance(record.get("layer"), int) or record.get("position") != "center" or not isinstance(record.get("style"), dict) or set(record["style"]) != {"font", "color", "outline", "shadow", "size", "alignment"} or not isinstance(record.get("line_breaks"), list) or template_requirement != {"provider": "capcut", "source": "official", "resource_type": "text_template", "resource_readback_required": True}):
                errors.append(f"captions[{index}] must contain canonical editor fields")
            if label == "tts" and (not isinstance(record.get("voice"), str) or not finite_number(record.get("speed")) or not finite_number(record.get("pitch")) or not isinstance(record.get("voice_processing"), str) or record.get("duration_status") not in {"planned", "verified"} or record.get("track") != "tts" or not isinstance(record.get("layer"), int)):
                errors.append(f"tts[{index}] must contain canonical editor fields")
            ids.append(record["cut_id"])
    if ids != cut_ids or len(ids) != len(set(ids)):
        errors.append(f"{label} must close exactly over expected cut IDs in timeline order")


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
    if not isinstance(setup, dict) or setup.get("schema_version") != "4" or setup.get("setup_steps") != ["verify_hashes", "import_assets", "create_timeline"]:
        errors.append("portable_setup must provide canonical v4 setup instructions")
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


def aware_datetime(value):
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00")) if isinstance(value, str) else None
    except ValueError:
        parsed = None
    return parsed if parsed and parsed.tzinfo else None


def jst_export_date(value):
    date = jst_date(value)
    return f"{date[:7]}{date[8:]}" if date else None


def check_delivery(payload, model, errors):
    date = jst_date(payload.get("created_at"))
    delivery = payload.get("delivery")
    if date is None:
        errors.append("created_at must be offset-aware for JST naming")
        return
    if not isinstance(delivery, dict):
        return
    if delivery.get("naming_jst_date") != date or delivery.get("capcut_cloud_project_path") != f"Space/{model}/AI作成_{model}_{date}":
        errors.append("CapCut project naming must use the real payload JST date")
    status = delivery.get("export_status")
    receipt = delivery.get("export_receipt")
    if status == "pending":
        check_drive_delivery(payload, delivery, errors)
        if receipt is not None:
            errors.append("pending export must not carry an export receipt")
        return
    if status != "completed" or not isinstance(receipt, dict):
        check_drive_delivery(payload, delivery, errors)
        errors.append("delivery export_status must be pending or completed with an export receipt")
        return
    current_exported_at = aware_datetime(receipt.get("exported_at"))
    export_date = jst_export_date(receipt.get("exported_at"))
    if export_date is None:
        errors.append("export_receipt.exported_at must be offset-aware")
        return
    prior = receipt.get("prior_completed_exports")
    prior_fields = {"status", "jst_export_date", "product_model", "count", "verified_at", "ledger_scope", "ledger_snapshot_sha256", "completed_exports"}
    unknown(prior, prior_fields, "export_receipt.prior_completed_exports", errors)
    completed_exports = prior.get("completed_exports") if isinstance(prior, dict) else None
    verified_at = aware_datetime(prior.get("verified_at")) if isinstance(prior, dict) else None
    if not isinstance(prior, dict) or set(prior) != prior_fields or prior.get("status") != "verified" or prior.get("jst_export_date") != export_date or prior.get("product_model") != model or prior.get("ledger_scope") != f"{export_date}|{model}" or verified_at is None or current_exported_at is None or verified_at >= current_exported_at or isinstance(prior.get("count"), bool) or not isinstance(prior.get("count"), int) or not 0 <= prior["count"] < len(ORDINAL_MARKERS) or not isinstance(completed_exports, list) or prior.get("count") != len(completed_exports) or prior.get("ledger_snapshot_sha256") != digest(completed_exports):
        errors.append("HOLD_PRODUCTION_ORDINAL_UNVERIFIED: export receipt needs a verified prior completed-export count for its JST date and product model")
        return
    seen_basenames = set()
    last_exported_at = None
    for index, item in enumerate(completed_exports):
        item_fields = {"completed_video_basename", "exported_at", "media_sha256", "record_sha256"}
        if not isinstance(item, dict) or set(item) != item_fields:
            errors.append("HOLD_PRODUCTION_ORDINAL_UNVERIFIED: prior completed-export records must use the canonical ledger schema")
            return
        subject = {key: item[key] for key in ("completed_video_basename", "exported_at", "media_sha256")}
        expected_basename = f"{export_date}_{model}_AI作成{ORDINAL_MARKERS[index]}"
        item_exported_at = aware_datetime(item.get("exported_at"))
        if item.get("completed_video_basename") != expected_basename or item["completed_video_basename"] in seen_basenames or jst_export_date(item.get("exported_at")) != export_date or item_exported_at is None or item_exported_at >= current_exported_at or item_exported_at > verified_at or (last_exported_at is not None and item_exported_at <= last_exported_at) or not is_sha(item.get("media_sha256")) or item.get("record_sha256") != digest(subject):
            errors.append("HOLD_PRODUCTION_ORDINAL_UNVERIFIED: prior completed-export records must be ordered, unique, scope-matched, and hash-verified")
            return
        seen_basenames.add(item["completed_video_basename"])
        last_exported_at = item_exported_at
    ordinal = receipt.get("production_ordinal")
    if isinstance(ordinal, bool) or not isinstance(ordinal, int) or not 1 <= ordinal <= len(ORDINAL_MARKERS):
        errors.append("export_receipt.production_ordinal must be an integer from 1 through 20")
        return
    basename = f"{export_date}_{model}_AI作成{ORDINAL_MARKERS[ordinal - 1]}"
    if receipt.get("completed_video_basename") != basename:
        errors.append("completed video naming must use export_receipt.exported_at, model, and production ordinal")
    extension = receipt.get("file_extension")
    if extension not in VIDEO_MIME_BY_EXTENSION or receipt.get("mime_type") != VIDEO_MIME_BY_EXTENSION.get(extension) or receipt.get("completed_video_filename") != f"{basename}.{extension}":
        errors.append("completed export filename, extension, and MIME type must match exactly")
    if ordinal != prior["count"] + 1:
        errors.append("HOLD_PRODUCTION_ORDINAL_UNVERIFIED: production ordinal must equal verified prior count plus one")
    check_drive_delivery(payload, delivery, errors)


def check_drive_delivery(payload, delivery, errors):
    status = delivery.get("drive_status")
    receipt = delivery.get("drive_receipt")
    if status == "not_requested":
        if receipt is not None:
            errors.append("not-requested Drive delivery forbids a read-back receipt")
        return
    if status == "pending":
        if receipt is not None:
            errors.append("pending Drive delivery forbids a read-back receipt")
        return
    if status != "completed" or not isinstance(receipt, dict):
        errors.append("Drive delivery status must be not_requested, pending, or completed with read-back")
        return
    gate = payload.get("approval_gates", {}).get("cloud", {}) if isinstance(payload.get("approval_gates"), dict) else {}
    export_receipt = delivery.get("export_receipt")
    fields = {"file_name", "mime_type", "byte_size", "file_id_sha256", "parent_scope_sha256", "readback_at", "receipt_sha256"}
    subject = {key: receipt.get(key) for key in fields - {"receipt_sha256"}}
    file_name = receipt.get("file_name")
    valid_name = isinstance(file_name, str) and isinstance(export_receipt, dict) and file_name == export_receipt.get("completed_video_filename")
    readback_at = aware_datetime(receipt.get("readback_at"))
    exported_at = aware_datetime(export_receipt.get("exported_at")) if isinstance(export_receipt, dict) else None
    if delivery.get("export_status") != "completed" or set(receipt) != fields or gate.get("status") != "approved" or not valid_name or exported_at is None or readback_at is None or readback_at < exported_at or receipt.get("mime_type") != export_receipt.get("mime_type") or isinstance(receipt.get("byte_size"), bool) or not isinstance(receipt.get("byte_size"), int) or receipt["byte_size"] <= 0 or not is_sha(receipt.get("file_id_sha256")) or receipt.get("parent_scope_sha256") != gate.get("destination_scope_sha256") or receipt.get("receipt_sha256") != digest(subject):
        errors.append("completed Drive delivery requires exact hash-bound file, MIME, byte-size, parent-scope, and read-back evidence")


def hash_bound(value, production_hash, visible_hash, label, errors):
    if not isinstance(value, dict) or value.get("bound_production_payload_sha256") != production_hash or value.get("bound_visible_content_sha256") != visible_hash:
        errors.append(f"{label} must bind current production and visible hashes")


def check_approvals(payload, production_hash, visible_hash, additional_needed, errors):
    gates = payload.get("approval_gates")
    unknown(gates, set(GATES), "approval_gates", errors)
    if not isinstance(gates, dict):
        return
    common_fields = {"status", "receipt", "explicit_approval", "checkpoint", "authorized_actions", "bound_production_payload_sha256", "bound_visible_content_sha256"}
    gate_fields = {
        "edit": common_fields,
        "credit": common_fields | {"max_first_attempt_tts_count"},
        "export": common_fields,
        "cloud": common_fields | {"drive_delivery_requested", "exact_destination_scope_confirmed", "destination_scope_subject", "destination_scope_sha256", "destination_scope_receipt", "original_request_subject", "original_request_sha256"},
        "publish": common_fields | {"external_scope_subject", "external_scope_sha256"},
        "send": common_fields | {"external_scope_subject", "external_scope_sha256"},
    }
    exact_plans = {
        "edit": ("script", ["rough_visual_edit"]),
        "credit": ("rough_edit", ["finish_edit", "apply_official_template", "first_attempt_tts", "first_attempt_ai_credits"]),
        "export": ("final_pre_export", ["new_export"]),
        "publish": ("separate", ["publish"]),
        "send": ("separate", ["external_send"]),
    }
    for gate in GATES:
        value = gates.get(gate)
        unknown(value, gate_fields[gate], f"approval_gates.{gate}", errors)
        status = value.get("status") if isinstance(value, dict) else None
        if status not in {"pending", "approved", "not_applicable"}:
            errors.append(f"approval_gates.{gate}.status is invalid")
            continue
        hash_bound(value, production_hash, visible_hash, f"approval_gates.{gate}", errors)
        if gate in exact_plans:
            checkpoint, actions = exact_plans[gate]
            if value.get("checkpoint") != checkpoint or value.get("authorized_actions") != actions:
                errors.append(f"approval_gates.{gate} must keep its exact checkpoint and action plan before and after approval")
            if gate == "credit":
                targets = [record for record in payload.get("script", []) if isinstance(record, dict) and record.get("narration_target") is True]
                if isinstance(value.get("max_first_attempt_tts_count"), bool) or value.get("max_first_attempt_tts_count") != len(targets):
                    errors.append("rough-edit credit plan must disclose exactly one first attempt per narration target")
            if status != "approved":
                if value.get("receipt") is not None or value.get("explicit_approval") is not False:
                    errors.append(f"unapproved approval_gates.{gate} must not carry an approval receipt")
                continue
            expected_receipt = {"edit": "台本OK", "credit": "粗編集OK", "export": "完成・書き出しOK"}.get(gate)
            if expected_receipt is not None and (value.get("receipt") != expected_receipt or value.get("explicit_approval") is not True):
                errors.append(f"approval_gates.{gate} must use its exact mapped checkpoint receipt and scope")
            if gate == "edit" and additional_needed:
                errors.append("approved rough visual edit requires no additional_asset_required")
            if gate in {"publish", "send"}:
                scope = value.get("external_scope_subject")
                expected_kind = "tiktok_account" if gate == "publish" else "external_recipient"
                scope_fields = {"destination_kind", "destination_label", "visible_content_sha256"}
                if value.get("explicit_approval") is not True or not isinstance(value.get("receipt"), str) or not value["receipt"].strip() or not isinstance(scope, dict) or set(scope) != scope_fields or scope.get("destination_kind") != expected_kind or not isinstance(scope.get("destination_label"), str) or not scope["destination_label"].strip() or scope.get("visible_content_sha256") != visible_hash or value.get("external_scope_sha256") != digest(scope):
                    errors.append(f"approval_gates.{gate} requires a separate exact destination-scoped approval")
            continue

        requested = value.get("drive_delivery_requested") is True or value.get("checkpoint") is not None or value.get("authorized_actions") != []
        if not requested:
            if status == "approved" or value.get("checkpoint") is not None or value.get("authorized_actions") != [] or value.get("receipt") is not None or value.get("explicit_approval") is not False or any(field in value for field in gate_fields["cloud"] - common_fields):
                errors.append("unrequested cloud delivery must remain an empty pending/not-applicable plan")
            continue
        if value.get("checkpoint") != "final_pre_export" or value.get("authorized_actions") != ["new_drive_upload", "drive_upload_readback"]:
            errors.append("approval_gates.cloud must keep its exact final-checkpoint action plan")
        scope = value.get("destination_scope_subject")
        scope_fields = {"destination_kind", "root_scope_label", "product_model", "new_file_only"}
        model = payload.get("product_info", {}).get("product_model") if isinstance(payload.get("product_info"), dict) else None
        request_subject = value.get("original_request_subject")
        expected_request_subject = {"drive_delivery_requested": True, "destination_scope_sha256": digest(scope) if isinstance(scope, dict) else None, "requested_actions": ["new_drive_upload", "drive_upload_readback"]}
        if value.get("exact_destination_scope_confirmed") is not True or not isinstance(scope, dict) or set(scope) != scope_fields or scope.get("destination_kind") != "google_drive_model_folder" or not isinstance(scope.get("root_scope_label"), str) or not scope["root_scope_label"].strip() or scope.get("product_model") != model or scope.get("new_file_only") is not True or value.get("destination_scope_sha256") != digest(scope) or request_subject != expected_request_subject or value.get("original_request_sha256") != digest(request_subject) or not isinstance(value.get("destination_scope_receipt"), str) or not value["destination_scope_receipt"].strip():
            errors.append("cloud checkpoint requires exact hash-bound original-request and Drive destination-scope evidence")
        if status != "approved":
            if value.get("receipt") is not None or value.get("explicit_approval") is not False:
                errors.append("unapproved approval_gates.cloud must not carry an approval receipt")
            continue
        if value.get("receipt") != "完成・書き出しOK" or value.get("explicit_approval") is not True:
            errors.append("approval_gates.cloud must use its exact mapped checkpoint receipt and scope")


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


def fixture(openclaw=False, camee=False, tts=True, additional=False, model="AN-T001", decorative=False, accelerated=False, overflow_strategy=None):
    source_sha = "a" * 64
    settings_sha = "7" * 64
    asset_ids = ["asset-product", "asset-product-02", "asset-product-03", "asset-product-04", "asset-product-05", "asset-product-06"]
    media_shas = [value * 64 for value in ("b", "c", "d", "e", "f", "6")]
    sidecar_shas = [value * 64 for value in ("1", "2", "3", "4", "5", "7")]
    media_paths = [f"media/product-{index:02d}.mp4" for index in range(1, 7)]
    sidecar_paths = [f"media/product-{index:02d}.sidecar.json" for index in range(1, 7)]
    sem1 = {"subject": "product_and_hand", "action": "hold", "composition": "close_up", "product_visibility": "full", "text_visibility": "none"}
    sem2 = {"subject": "product", "action": "reveal", "composition": "medium", "product_visibility": "full", "text_visibility": "product_label"}
    req1 = {"semantics": sem1, "canonical_description": semantic_description(sem1), "must_show": [{"subject": "product", "visibility": "full"}], "must_not_show": []}
    req2 = {"semantics": sem2, "canonical_description": semantic_description(sem2), "must_show": [{"subject": "product", "visibility": "full"}], "must_not_show": ["third_party_logo"]}
    cuts = []
    for index in range(6):
        start = float(index * 2)
        cuts.append({"cut_id": f"cut-{index + 1:02d}", "timeline_in": start, "timeline_out": start + 2.0, "source_asset_id": asset_ids[index], "source_in": 0.0, "source_out": 2.0, "editor": {"track": "video", "layer": 1, "transition": "cut", "zoom": "in" if index == 0 else "none", "effect": "highlight" if index == 0 else "none", "speed": 1.0}, "media_requirements": json.loads(json.dumps(req1 if index % 2 == 0 else req2))})
    if overflow_strategy == "slow_video_and_caption":
        cuts[2]["source_out"] = 1.6
        cuts[2]["editor"]["speed"] = 0.8
    for index, cut in enumerate(cuts):
        if additional and cut["cut_id"] == "cut-01":
            cut["additional_asset_required"] = True
            cut["source_asset_id"] = None
            cut["source_in"] = None
            cut["source_out"] = None
        else:
            cut["matched_sidecar_receipt"] = {"asset_id": asset_ids[index], "sidecar_sha256": sidecar_shas[index], "sidecar_relative_path": sidecar_paths[index], "status": "verified", "requirements_sha256": requirements_hash(cut), "matched_fields": ["canonical_description", "semantics", "must_show", "must_not_show"]}
    assets = [{"asset_id": asset_ids[index], "media_sha256": media_shas[index], "media_relative_path": media_paths[index], "sidecar_sha256": sidecar_shas[index], "sidecar_relative_path": sidecar_paths[index], "classification": {"original": False, "editable_project_dependency": False, "shared": False, "uncertain": False}} for index in range(6)]
    assets.append({"asset_id": "asset-prior", "media_sha256": "9" * 64, "media_relative_path": "media/prior.mp4", "sidecar_sha256": "8" * 64, "sidecar_relative_path": "media/prior.sidecar.json", "classification": {"original": False, "editable_project_dependency": False, "shared": False, "uncertain": False}})
    payload = {"created_at": "2026-08-03T16:00:00+00:00", "manifest": [{"material_id": "material-company", "company_authoritative": True, "access_status": "available", "sha256": source_sha, "observed_product_models": [model]}], "product_info": {"product_model": model, "product_model_provenance": {"status": "verified", "material_ids": ["material-company"], "material_sha256s": {"material-company": source_sha}, "observed_model": model}}, "script": [], "cuts": cuts, "captions": [], "delivery": {"naming_jst_date": "2026_08_04", "capcut_cloud_project_path": f"Space/{model}/AI作成_{model}_2026_08_04", "export_status": "completed", "export_receipt": {"exported_at": "2026-08-26T09:16:24+00:00", "production_ordinal": 1, "completed_video_basename": f"2026_0826_{model}_AI作成①", "file_extension": "mp4", "mime_type": "video/mp4", "completed_video_filename": f"2026_0826_{model}_AI作成①.mp4", "prior_completed_exports": {"status": "verified", "jst_export_date": "2026_0826", "product_model": model, "count": 0, "verified_at": "2026-08-26T09:15:00+00:00", "ledger_scope": f"2026_0826|{model}", "ledger_snapshot_sha256": digest([]), "completed_exports": []}}, "drive_status": "not_requested", "portable_handoff": {"uses_relative_paths": True, "assets": assets}}, "routing": {"openclaw_bound": openclaw, "camee_neo_openclaw_bound": camee}, "cleanup_preflight": {"preflight_only": True, "preserve_originals": True, "preserve_editable_dependencies": True, "preserve_shared_or_uncertain": True, "local_working_download_candidates": [{"asset_id": "asset-product", "media_sha256": media_shas[0], "verified_local_working_download": True, "release_approved": True}]}}
    payload["manifest"] = [
        {"material_id": "material-company", "kind": "product_url", "source_location": "https://example.invalid/product", "provided_by": "user", "observed_at": "2026-08-03T16:00:00+00:00", "byte_size": 1, "sha256": source_sha, "media_type": "text/html", "access_status": "available", "usage_status": "approved", "analysis_status": "complete", "limitations": "none", "company_authoritative": True, "observed_product_models": [model]},
        {"material_id": "material-settings", "kind": "product_video_settings", "source_location": f"config/product_video_settings_{model}.v1.json", "provided_by": "project", "observed_at": "2026-08-03T16:00:00+00:00", "byte_size": 1, "sha256": settings_sha, "media_type": "application/json", "access_status": "available", "usage_status": "approved", "analysis_status": "complete", "limitations": "none", "company_authoritative": False, "observed_product_models": [model]},
    ]
    payload["manifest_ref"] = [{"material_id": item["material_id"], "sha256": item["sha256"]} for item in payload["manifest"]]
    payload.update(goal_axis="watch_continuation", patterns=[{"pattern_key": "pattern-01", "reason": "fit", "reusable_structure": "hook", "not_to_copy": "wording", "confidence": "medium", "source_video_count": 1}], facts_used=[{"fact_id": "fact-01", "classification": "verified_fact", "value": "observed", "material_refs": [{"material_id": "material-company", "sha256": source_sha}]}], hypotheses=[{"hypothesis_id": "hyp-01", "statement": "test", "basis": "pattern", "disproof_condition": "metric"}], audio={key: {"status": "not_applicable", "origin": "none", "rights": "not_applicable", "level": 0, "fade": 0} for key in ("bgm", "se", "source_audio")}, post_set={"title": "title", "post_text": "post", "pinned_comment": "comment", "description": "description", "hashtags": ["#test"]}, design_quality_qa={"axes": [{"axis": axis, "score": 0, "max_score": maximum, "evidence": "none", "counterevidence": "none", "improvement": "next"} for axis, maximum in QA_MAX.items()], "total_score": 0, "metrics": {"watch_retention": "not_measured", "comment_rate": "not_measured", "save_rate": "not_measured", "share_rate": "not_measured", "purchase_rate": "not_measured"}}, risk_register=[{"risk_id": "risk_01", "category": "rights", "status": "open", "mitigation": "review"}], portable_setup={"schema_version": "4", "setup_steps": ["verify_hashes", "import_assets", "create_timeline"]})
    dialogues = ("困りごとを提示", "商品を紹介", "使い方を確認", "結果を確認", "困りごとの解消を確認", CTA)
    payload["script"] = [{"cut_id": cut["cut_id"], "dialogue": dialogues[index], "timeline_in": cut["timeline_in"], "timeline_out": cut["timeline_out"], "narrative_role": NARRATIVE_ROLES[index], "narration_target": tts and not (decorative and index == 1), "fact_refs": ["fact-01"], "media_evidence_asset_id": cut["source_asset_id"]} for index, cut in enumerate(cuts)]
    style = {"font": "sans", "color": "white", "outline": "black", "shadow": "none", "size": 32, "alignment": "center"}
    template_requirement = {"provider": "capcut", "source": "official", "resource_type": "text_template", "resource_readback_required": True}
    payload["captions"] = [{"cut_id": item["cut_id"], "text": item["dialogue"], "timeline_in": item["timeline_in"], "timeline_out": item["timeline_out"], "track": "caption", "layer": 2, "position": "center", "style": style, "line_breaks": [], "template_requirement": template_requirement, "narration_target": item["narration_target"]} for item in payload["script"]]
    payload["script_review_receipt"] = {"selected_concept": "verified selected concept", "inspection_artifact_relative_path": "review/script-plan.md", "location_label": "script review", "cuts": [{"cut_id": cut["cut_id"], "dialogue": item["dialogue"], "line_breaks": [], "source_asset_id": cut["source_asset_id"], "source_in": cut["source_in"], "source_out": cut["source_out"], "cut_duration": cut["timeline_out"] - cut["timeline_in"], "unicode_codepoint_count": len(item["dialogue"]), "estimated_read_seconds": 1.0, "fact_refs": ["fact-01"], "media_evidence_asset_id": cut["source_asset_id"]} for cut, item in zip(cuts, payload["script"])]}
    if tts:
        strategy = overflow_strategy or ("common_tts_acceleration" if accelerated else "normal")
        common_speed = 1.2 if strategy != "normal" else 1.0
        overflow_cut_ids = ["cut-03"] if strategy in {"longer_verified_distinct_source", "slow_video_and_caption"} else []
        evidence = []
        target_ids = [item["cut_id"] for item in payload["script"] if item["narration_target"]]
        if strategy != "normal":
            common_item = {"step": "common_tts_acceleration", "status": "applied_sufficient" if strategy == "common_tts_acceleration" else "applied_insufficient", "common_speed": common_speed, "affected_cut_ids": target_ids}
            evidence.append(dict(common_item, evidence_sha256=digest(common_item)))
        if strategy in {"longer_verified_distinct_source", "slow_video_and_caption"}:
            replacement_seconds = float(decimal_duration(cuts[2]["source_in"], cuts[2]["source_out"]))
            prior_in = 0.0
            prior_out = 1.5 if strategy == "longer_verified_distinct_source" else 1.2
            prior_subject = {"cut_id": "cut-03", "asset_id": "asset-prior", "media_sha256": "9" * 64, "sidecar_sha256": "8" * 64, "source_in": prior_in, "source_out": prior_out}
            longer_item = {"step": "longer_verified_distinct_source", "status": "applied_sufficient" if strategy == "longer_verified_distinct_source" else "applied_insufficient", "cut_ids": overflow_cut_ids, "prior_asset_ids": {"cut-03": "asset-prior"}, "prior_media_sha256": {"cut-03": "9" * 64}, "prior_sidecar_sha256": {"cut-03": "8" * 64}, "prior_source_in": {"cut-03": prior_in}, "prior_source_out": {"cut-03": prior_out}, "prior_available_seconds": {"cut-03": prior_out - prior_in}, "prior_evidence_sha256": {"cut-03": digest(prior_subject)}, "replacement_available_seconds": {"cut-03": replacement_seconds}, "replacement_asset_ids": {"cut-03": cuts[2]["source_asset_id"]}}
            evidence.append(dict(longer_item, evidence_sha256=digest(longer_item)))
        if strategy == "slow_video_and_caption":
            slow_item = {"step": "slow_video_and_caption", "status": "applied_sufficient", "cut_ids": overflow_cut_ids, "video_speeds": {"cut-03": 0.8}}
            evidence.append(dict(slow_item, evidence_sha256=digest(slow_item)))
        payload["narration_policy"] = {"mode": "required", "scope": "video", "user_explicit": False, "receipt": "default_required", "timing_strategy": strategy, "common_speed": common_speed, "overflow_cut_ids": overflow_cut_ids, "overflow_reason": "verified narration exceeded the available visual duration" if strategy != "normal" else "", "overflow_evidence": evidence}
        payload["voice_policy"] = {"preset": "CapCut official ホリデーツイスト", "source": "default", "user_explicit": False, "receipt": "default", "pitch": 1.0, "voice_processing": "none"}
        payload["tts"] = [{"cut_id": item["cut_id"], "text": item["dialogue"], "voice": payload["voice_policy"]["preset"], "speed": common_speed, "pitch": 1.0, "voice_processing": "none", "timeline_in": item["timeline_in"], "timeline_out": item["timeline_out"], "duration_status": "planned", "track": "tts", "layer": 3} for item in payload["script"] if item["narration_target"]]
    else:
        payload["narration_policy"] = {"mode": "none", "scope": "video", "user_explicit": True, "receipt": "user explicitly requested narration none for this video", "timing_strategy": "not_applicable", "common_speed": None, "overflow_cut_ids": [], "overflow_reason": "", "overflow_evidence": []}
    resolved_settings = {"cta_text": CTA, "default_voice_preset": "ホリデーツイスト", "base_speed": 1.0, "fallback_speed_min": 1.2, "fallback_speed_max": 1.5, "caption_template_resource_id": "7580304846847282485", "final_cut_asset_id": asset_ids[-1], "final_source_in": 0.0, "final_source_out": 2.0}
    payload["product_settings"] = {"status": "verified", "product_model": model, "manifest_material_id": "material-settings", "source_location": f"config/product_video_settings_{model}.v1.json", "settings_sha256": settings_sha, "schema_version": "1", "resolved_settings": resolved_settings, "resolved_values_sha256": digest(resolved_settings)}
    payload["final_visual_policy"] = {"status": "verified", "cut_id": cuts[-1]["cut_id"], "asset_id": asset_ids[-1], "catalog_asset_id": asset_ids[-1], "mode": "full_source", "source_duration": 2.0, "approved_source_in": 0.0, "approved_source_out": 2.0, "user_explicit": True, "receipt": "user approved canonical final visual", "settings_sha256": settings_sha, "common_narration_speed": payload["narration_policy"]["common_speed"]}
    payload["component_hashes"] = {"manifest_sha256": digest(payload["manifest"]), "favorite_context_sha256": digest({"goal_axis": payload["goal_axis"], "patterns": payload["patterns"]}), "script_sha256": digest(payload["script"]), "cuts_sha256": digest(cuts), "captions_sha256": digest(payload["captions"]), "tts_sha256": digest(payload.get("tts"))}
    gate_plans = {
        "edit": {"checkpoint": "script", "authorized_actions": ["rough_visual_edit"]},
        "credit": {"checkpoint": "rough_edit", "authorized_actions": ["finish_edit", "apply_official_template", "first_attempt_tts", "first_attempt_ai_credits"], "max_first_attempt_tts_count": len([item for item in payload["script"] if item["narration_target"]])},
        "export": {"checkpoint": "final_pre_export", "authorized_actions": ["new_export"]},
        "cloud": {"checkpoint": None, "authorized_actions": []},
        "publish": {"checkpoint": "separate", "authorized_actions": ["publish"]},
        "send": {"checkpoint": "separate", "authorized_actions": ["external_send"]},
    }
    payload["approval_gates"] = {gate: dict({"status": "pending", "receipt": None, "explicit_approval": False}, **gate_plans[gate]) for gate in GATES}
    production_hash, visible_hash = expected_hashes(payload)
    payload["integrity"] = {"production_payload_sha256": production_hash, "visible_content_sha256": visible_hash}
    for value in payload["approval_gates"].values():
        value["bound_production_payload_sha256"] = production_hash
        value["bound_visible_content_sha256"] = visible_hash
    if openclaw or camee:
        payload["openclaw_prohibition"] = {"passed": True, "checked_last": True, "policy_version": "v1", "attempt": 1, "matched_rule_ids": [], "bound_production_payload_sha256": production_hash, "bound_visible_content_sha256": visible_hash}
    if camee:
        payload["camee_tiktok_shop"] = {"verification_status": "verified", "url": "https://shop.tiktok.com/view/product/123456789012", "product_id": "123456789012", "bound_production_payload_sha256": production_hash, "bound_visible_content_sha256": visible_hash}
    return payload


def self_test():
    def trusted_settings(payload):
        model = payload.get("product_info", {}).get("product_model") if isinstance(payload.get("product_info"), dict) else None
        resolved = {"cta_text": CTA, "default_voice_preset": "ホリデーツイスト", "base_speed": 1.0, "fallback_speed_min": 1.2, "fallback_speed_max": 1.5, "caption_template_resource_id": "7580304846847282485", "final_cut_asset_id": "asset-product-06", "final_source_in": 0.0, "final_source_out": 2.0}
        return {"product_model": model, "source_location": f"config/product_video_settings_{model}.v1.json", "settings_sha256": "7" * 64, "schema_version": "1", "resolved_settings": resolved}

    def refresh_hash_bindings(payload):
        production_hash, visible_hash = expected_hashes(payload)
        payload["integrity"] = {"production_payload_sha256": production_hash, "visible_content_sha256": visible_hash}
        for value in payload.get("approval_gates", {}).values():
            value["bound_production_payload_sha256"] = production_hash
            value["bound_visible_content_sha256"] = visible_hash

    def set_observed_subjects(payload, semantic_subject, must_show_subject):
        requirements = payload["cuts"][0]["media_requirements"]
        requirements["semantics"]["subject"] = semantic_subject
        requirements["canonical_description"] = semantic_description(requirements["semantics"])
        requirements["must_show"][0]["subject"] = must_show_subject
        payload["cuts"][0]["matched_sidecar_receipt"]["requirements_sha256"] = requirements_hash(payload["cuts"][0])
        payload["component_hashes"]["cuts_sha256"] = digest(payload["cuts"])
        refresh_hash_bindings(payload)
        return payload

    if decimal_duration(9.8, 15.366667) != decimal_duration(0.0, 5.566667):
        raise AssertionError("decimal timestamp duration comparison failed")
    pending = fixture()
    pending["delivery"]["export_status"] = "pending"
    pending["delivery"].pop("export_receipt")
    pending_hash, pending_visible_hash = expected_hashes(pending)
    pending["integrity"] = {"production_payload_sha256": pending_hash, "visible_content_sha256": pending_visible_hash}
    for value in pending["approval_gates"].values():
        value["bound_production_payload_sha256"] = pending_hash
        value["bound_visible_content_sha256"] = pending_visible_hash
    second_export = fixture()
    prior_subject = {"completed_video_basename": f"2026_0826_{second_export['product_info']['product_model']}_AI作成①", "exported_at": "2026-08-26T08:00:00+00:00", "media_sha256": "9" * 64}
    prior_record = dict(prior_subject, record_sha256=digest(prior_subject))
    prior_ledger = second_export["delivery"]["export_receipt"]["prior_completed_exports"]
    prior_ledger.update(count=1, completed_exports=[prior_record], ledger_snapshot_sha256=digest([prior_record]))
    second_export["delivery"]["export_receipt"].update(production_ordinal=2, completed_video_basename=f"2026_0826_{second_export['product_info']['product_model']}_AI作成②", completed_video_filename=f"2026_0826_{second_export['product_info']['product_model']}_AI作成②.mp4")
    invalid_longer = fixture(overflow_strategy="longer_verified_distinct_source")
    invalid_longer["narration_policy"]["overflow_evidence"][1]["prior_available_seconds"]["cut-03"] = 2.0
    invalid_prior_same_media = fixture(overflow_strategy="longer_verified_distinct_source")
    same_media_longer = invalid_prior_same_media["narration_policy"]["overflow_evidence"][1]
    current_asset_id = invalid_prior_same_media["cuts"][2]["source_asset_id"]
    current_asset = next(item for item in invalid_prior_same_media["delivery"]["portable_handoff"]["assets"] if item["asset_id"] == current_asset_id)
    prior_asset = next(item for item in invalid_prior_same_media["delivery"]["portable_handoff"]["assets"] if item["asset_id"] == "asset-prior")
    prior_asset["media_sha256"] = current_asset["media_sha256"]
    same_media_longer["prior_media_sha256"]["cut-03"] = current_asset["media_sha256"]
    same_media_subject = {"cut_id": "cut-03", "asset_id": "asset-prior", "media_sha256": current_asset["media_sha256"], "sidecar_sha256": prior_asset["sidecar_sha256"], "source_in": same_media_longer["prior_source_in"]["cut-03"], "source_out": same_media_longer["prior_source_out"]["cut-03"]}
    same_media_longer["prior_evidence_sha256"]["cut-03"] = digest(same_media_subject)
    same_media_longer["evidence_sha256"] = digest({key: same_media_longer[key] for key in same_media_longer if key != "evidence_sha256"})
    refresh_hash_bindings(invalid_prior_same_media)
    invalid_prior_current_asset = fixture(overflow_strategy="longer_verified_distinct_source")
    current_longer = invalid_prior_current_asset["narration_policy"]["overflow_evidence"][1]
    used_asset_id = invalid_prior_current_asset["cuts"][1]["source_asset_id"]
    used_asset = next(item for item in invalid_prior_current_asset["delivery"]["portable_handoff"]["assets"] if item["asset_id"] == used_asset_id)
    current_longer["prior_asset_ids"]["cut-03"] = used_asset_id
    current_longer["prior_media_sha256"]["cut-03"] = used_asset["media_sha256"]
    current_longer["prior_sidecar_sha256"]["cut-03"] = used_asset["sidecar_sha256"]
    current_subject = {"cut_id": "cut-03", "asset_id": used_asset_id, "media_sha256": used_asset["media_sha256"], "sidecar_sha256": used_asset["sidecar_sha256"], "source_in": current_longer["prior_source_in"]["cut-03"], "source_out": current_longer["prior_source_out"]["cut-03"]}
    current_longer["prior_evidence_sha256"]["cut-03"] = digest(current_subject)
    current_longer["evidence_sha256"] = digest({key: current_longer[key] for key in current_longer if key != "evidence_sha256"})
    refresh_hash_bindings(invalid_prior_current_asset)
    invalid_order = fixture(overflow_strategy="slow_video_and_caption")
    invalid_order["narration_policy"]["overflow_evidence"].reverse()
    invalid_slow_duration = fixture(overflow_strategy="slow_video_and_caption")
    invalid_slow_duration["cuts"][2]["source_out"] = 2.0
    invalid_ledger_snapshot = fixture()
    invalid_ledger_snapshot["delivery"]["export_receipt"]["prior_completed_exports"]["ledger_snapshot_sha256"] = "0" * 64
    invalid_prior_after_current = json.loads(json.dumps(second_export))
    late_record = invalid_prior_after_current["delivery"]["export_receipt"]["prior_completed_exports"]["completed_exports"][0]
    late_record["exported_at"] = "2026-08-26T10:00:00+00:00"
    late_record["record_sha256"] = digest({key: late_record[key] for key in ("completed_video_basename", "exported_at", "media_sha256")})
    invalid_prior_after_current["delivery"]["export_receipt"]["prior_completed_exports"]["ledger_snapshot_sha256"] = digest([late_record])
    invalid_future_ledger = fixture()
    invalid_future_ledger["delivery"]["export_receipt"]["prior_completed_exports"]["verified_at"] = "2099-01-01T00:00:00+00:00"
    invalid_equal_ledger_time = fixture()
    invalid_equal_ledger_time["delivery"]["export_receipt"]["prior_completed_exports"]["verified_at"] = invalid_equal_ledger_time["delivery"]["export_receipt"]["exported_at"]
    cases = [("valid six-stage script", fixture(), False), ("valid six-character model", fixture(model="AN-S151TE"), False), ("valid vehicle and landscape subjects", set_observed_subjects(fixture(), "vehicle_and_landscape", "vehicle"), False), ("valid Japanese observed subjects", set_observed_subjects(fixture(), "炎天下の駐車車両", "強い日差しの下の車両"), False), ("reject empty semantic subject", set_observed_subjects(fixture(), "", "vehicle"), True), ("reject whitespace semantic subject", set_observed_subjects(fixture(), " \t", "vehicle"), True), ("reject non-string semantic subject", set_observed_subjects(fixture(), 123, "vehicle"), True), ("reject empty must-show subject", set_observed_subjects(fixture(), "vehicle", ""), True), ("reject whitespace must-show subject", set_observed_subjects(fixture(), "vehicle", " \t"), True), ("reject non-string must-show subject", set_observed_subjects(fixture(), "vehicle", 123), True), ("valid explicit no TTS", fixture(tts=False), False), ("valid explicit decorative caption", fixture(decorative=True), False), ("valid common TTS acceleration", fixture(accelerated=True), False), ("valid longer verified distinct source overflow", fixture(overflow_strategy="longer_verified_distinct_source"), False), ("valid slow video and caption overflow", fixture(overflow_strategy="slow_video_and_caption"), False), ("valid verified second ordinal", second_export, False), ("reject unchanged longer source", invalid_longer, True), ("reject prior source with replacement media SHA", invalid_prior_same_media, True), ("reject prior source still selected by another cut", invalid_prior_current_asset, True), ("reject out-of-order overflow evidence", invalid_order, True), ("reject slowdown without extended duration", invalid_slow_duration, True), ("reject ordinal ledger snapshot mismatch", invalid_ledger_snapshot, True), ("reject prior export after current export", invalid_prior_after_current, True), ("reject future ordinal ledger verification", invalid_future_ledger, True), ("reject ledger verified at export time", invalid_equal_ledger_time, True), ("valid additional-asset hold", fixture(additional=True), False), ("valid OpenClaw Camee", fixture(True, True), False)]
    settings_cases = []
    missing_settings = fixture()
    missing_settings.pop("product_settings")
    settings_cases.append(("reject missing product settings receipt", missing_settings, True))
    duplicate_settings = fixture()
    duplicate = dict(duplicate_settings["manifest"][1], material_id="material-settings-duplicate")
    duplicate_settings["manifest"].append(duplicate)
    duplicate_settings["manifest_ref"].append({"material_id": duplicate["material_id"], "sha256": duplicate["sha256"]})
    duplicate_settings["component_hashes"]["manifest_sha256"] = digest(duplicate_settings["manifest"])
    refresh_hash_bindings(duplicate_settings)
    settings_cases.append(("reject duplicate product settings material", duplicate_settings, True))
    settings_model_mismatch = fixture()
    settings_model_mismatch["product_settings"]["product_model"] = "AN-X999"
    refresh_hash_bindings(settings_model_mismatch)
    settings_cases.append(("reject product settings model mismatch", settings_model_mismatch, True))
    settings_sha_mismatch = fixture()
    settings_sha_mismatch["product_settings"]["settings_sha256"] = "0" * 64
    refresh_hash_bindings(settings_sha_mismatch)
    settings_cases.append(("reject product settings SHA mismatch", settings_sha_mismatch, True))
    settings_values_hash_mismatch = fixture()
    settings_values_hash_mismatch["product_settings"]["resolved_values_sha256"] = "0" * 64
    refresh_hash_bindings(settings_values_hash_mismatch)
    settings_cases.append(("reject resolved product settings hash mismatch", settings_values_hash_mismatch, True))
    final_settings_sha_mismatch = fixture()
    final_settings_sha_mismatch["final_visual_policy"]["settings_sha256"] = "0" * 64
    refresh_hash_bindings(final_settings_sha_mismatch)
    settings_cases.append(("reject final block settings SHA mismatch", final_settings_sha_mismatch, True))
    final_common_speed_mismatch = fixture()
    final_common_speed_mismatch["final_visual_policy"]["common_narration_speed"] = 1.2
    refresh_hash_bindings(final_common_speed_mismatch)
    settings_cases.append(("reject final block common speed mismatch", final_common_speed_mismatch, True))
    forged_template_settings = fixture()
    forged_template_settings["product_settings"]["resolved_settings"]["caption_template_resource_id"] = "forged-template"
    forged_template_settings["product_settings"]["resolved_values_sha256"] = digest(forged_template_settings["product_settings"]["resolved_settings"])
    refresh_hash_bindings(forged_template_settings)
    settings_cases.append(("reject self-consistent template setting forged against canonical file", forged_template_settings, True))
    forged_final_range = fixture()
    forged_resolved = forged_final_range["product_settings"]["resolved_settings"]
    forged_resolved.update(final_source_in=0.5, final_source_out=1.5)
    forged_final_range["product_settings"]["resolved_values_sha256"] = digest(forged_resolved)
    forged_final_range["final_visual_policy"].update(mode="approved_long_range", approved_source_in=0.5, approved_source_out=1.5)
    forged_cut = forged_final_range["cuts"][-1]
    forged_cut.update(source_in=0.5, source_out=1.5, timeline_out=11.0)
    forged_final_range["script"][-1]["timeline_out"] = 11.0
    forged_final_range["captions"][-1]["timeline_out"] = 11.0
    forged_final_range["tts"][-1]["timeline_out"] = 11.0
    forged_review = forged_final_range["script_review_receipt"]["cuts"][-1]
    forged_review.update(source_in=0.5, source_out=1.5, cut_duration=1.0)
    forged_final_range["component_hashes"].update(script_sha256=digest(forged_final_range["script"]), cuts_sha256=digest(forged_final_range["cuts"]), captions_sha256=digest(forged_final_range["captions"]), tts_sha256=digest(forged_final_range["tts"]))
    refresh_hash_bindings(forged_final_range)
    settings_cases.append(("reject self-consistent final range forged against canonical file", forged_final_range, True))
    cases.extend(settings_cases)
    actual_an_s182 = fixture(model="AN-S182")
    actual_settings_sha = "a90ee56e42e8ddfcc9c4fec7970bffcc1e4396bbe6dcd37df9a2f74b399e0afa"
    actual_resolved = {"cta_text": CTA, "default_voice_preset": "ホリデーツイスト", "base_speed": 1.0, "fallback_speed_min": 1.2, "fallback_speed_max": 1.5, "caption_template_resource_id": "7580304846847282485", "final_cut_asset_id": "A064", "final_source_in": 0.0, "final_source_out": 5.566667}
    actual_trusted = {"product_model": "AN-S182", "source_location": "config/product_video_settings_AN-S182.v1.json", "settings_sha256": actual_settings_sha, "schema_version": "1", "resolved_settings": actual_resolved}
    actual_an_s182["manifest"][1]["sha256"] = actual_settings_sha
    actual_an_s182["manifest_ref"][1]["sha256"] = actual_settings_sha
    actual_an_s182["product_settings"].update(settings_sha256=actual_settings_sha, resolved_settings=actual_resolved, resolved_values_sha256=digest(actual_resolved))
    actual_asset = actual_an_s182["delivery"]["portable_handoff"]["assets"][5]
    actual_asset["asset_id"] = "asset-a064"
    actual_cut = actual_an_s182["cuts"][-1]
    actual_cut.update(source_asset_id="asset-a064", source_in=0.0, source_out=5.566667, timeline_out=15.566667)
    actual_cut["matched_sidecar_receipt"]["asset_id"] = "asset-a064"
    actual_an_s182["script"][-1].update(timeline_out=15.566667, media_evidence_asset_id="asset-a064")
    actual_an_s182["captions"][-1]["timeline_out"] = 15.566667
    actual_an_s182["tts"][-1]["timeline_out"] = 15.566667
    actual_review = actual_an_s182["script_review_receipt"]["cuts"][-1]
    actual_review.update(source_asset_id="asset-a064", source_in=0.0, source_out=5.566667, cut_duration=5.566667, media_evidence_asset_id="asset-a064")
    actual_an_s182["final_visual_policy"].update(asset_id="asset-a064", catalog_asset_id="A064", source_duration=5.566667, approved_source_in=0.0, approved_source_out=5.566667, settings_sha256=actual_settings_sha)
    actual_an_s182["component_hashes"].update(manifest_sha256=digest(actual_an_s182["manifest"]), script_sha256=digest(actual_an_s182["script"]), cuts_sha256=digest(actual_an_s182["cuts"]), captions_sha256=digest(actual_an_s182["captions"]), tts_sha256=digest(actual_an_s182["tts"]))
    refresh_hash_bindings(actual_an_s182)
    actual_errors = errors_for(actual_an_s182, actual_trusted)
    if actual_errors:
        raise AssertionError("actual AN-S182 settings fixture failed: " + "; ".join(actual_errors))
    invalid_raw_catalog_id = json.loads(json.dumps(actual_an_s182))
    invalid_raw_catalog_id["final_visual_policy"]["asset_id"] = "A064"
    refresh_hash_bindings(invalid_raw_catalog_id)
    if not errors_for(invalid_raw_catalog_id, actual_trusted):
        raise AssertionError("raw catalog ID was accepted as a portable asset ID")
    live_an_s182 = load_trusted_product_settings(Path.cwd(), "AN-S182")
    if live_an_s182 is not None and live_an_s182 != actual_trusted:
        raise AssertionError("embedded AN-S182 trusted fixture differs from the live canonical settings file")
    pending_edit_broadened = fixture()
    pending_edit_broadened["approval_gates"]["edit"]["authorized_actions"].append("delete")
    refresh_hash_bindings(pending_edit_broadened)
    pending_credit_broadened = fixture()
    pending_credit_broadened["approval_gates"]["credit"]["max_first_attempt_tts_count"] = 999
    refresh_hash_bindings(pending_credit_broadened)
    cases.extend([("reject broadened pending edit plan", pending_edit_broadened, True), ("reject broadened pending credit plan", pending_credit_broadened, True)])
    script_checkpoint = fixture()
    script_checkpoint["approval_gates"]["edit"].update(status="approved", receipt="台本OK", explicit_approval=True, checkpoint="script", authorized_actions=["rough_visual_edit"])
    rough_checkpoint = fixture()
    rough_checkpoint["approval_gates"]["credit"].update(status="approved", receipt="粗編集OK", explicit_approval=True, checkpoint="rough_edit", authorized_actions=["finish_edit", "apply_official_template", "first_attempt_tts", "first_attempt_ai_credits"], max_first_attempt_tts_count=6)
    final_checkpoint = fixture()
    final_checkpoint["approval_gates"]["export"].update(status="approved", receipt="完成・書き出しOK", explicit_approval=True, checkpoint="final_pre_export", authorized_actions=["new_export"])
    final_pending_checkpoint = json.loads(json.dumps(final_checkpoint))
    final_pending_checkpoint["delivery"]["export_status"] = "pending"
    final_pending_checkpoint["delivery"].pop("export_receipt")
    cloud_checkpoint = fixture()
    cloud_scope = {"destination_kind": "google_drive_model_folder", "root_scope_label": "verified completed-video root", "product_model": cloud_checkpoint["product_info"]["product_model"], "new_file_only": True}
    request_subject = {"drive_delivery_requested": True, "destination_scope_sha256": digest(cloud_scope), "requested_actions": ["new_drive_upload", "drive_upload_readback"]}
    cloud_checkpoint["approval_gates"]["cloud"].update(status="approved", receipt="完成・書き出しOK", explicit_approval=True, checkpoint="final_pre_export", authorized_actions=["new_drive_upload", "drive_upload_readback"], drive_delivery_requested=True, exact_destination_scope_confirmed=True, destination_scope_subject=cloud_scope, destination_scope_sha256=digest(cloud_scope), destination_scope_receipt="destination disclosed at checkpoint 3", original_request_subject=request_subject, original_request_sha256=digest(request_subject))
    cloud_checkpoint["delivery"]["drive_status"] = "pending"
    cloud_hash, cloud_visible = expected_hashes(cloud_checkpoint)
    cloud_checkpoint["integrity"] = {"production_payload_sha256": cloud_hash, "visible_content_sha256": cloud_visible}
    for value in cloud_checkpoint["approval_gates"].values():
        value["bound_production_payload_sha256"] = cloud_hash
        value["bound_visible_content_sha256"] = cloud_visible
    cloud_completed = json.loads(json.dumps(cloud_checkpoint))
    drive_subject = {"file_name": f"2026_0826_{cloud_completed['product_info']['product_model']}_AI作成①.mp4", "mime_type": "video/mp4", "byte_size": 123456, "file_id_sha256": "7" * 64, "parent_scope_sha256": digest(cloud_scope), "readback_at": "2026-08-26T09:20:00+00:00"}
    cloud_completed["delivery"]["drive_status"] = "completed"
    cloud_completed["delivery"]["drive_receipt"] = dict(drive_subject, receipt_sha256=digest(drive_subject))
    invalid_drive_name = json.loads(json.dumps(cloud_completed))
    invalid_drive_name["delivery"]["drive_receipt"]["file_name"] = f"2026_0826_{cloud_completed['product_info']['product_model']}_AI作成②.mp4"
    invalid_drive_name_subject = {key: invalid_drive_name["delivery"]["drive_receipt"][key] for key in drive_subject}
    invalid_drive_name["delivery"]["drive_receipt"]["receipt_sha256"] = digest(invalid_drive_name_subject)
    invalid_drive_extension = json.loads(json.dumps(cloud_completed))
    invalid_drive_extension["delivery"]["drive_receipt"]["file_name"] = invalid_drive_extension["delivery"]["drive_receipt"]["file_name"].replace(".mp4", ".exe")
    invalid_drive_extension_subject = {key: invalid_drive_extension["delivery"]["drive_receipt"][key] for key in drive_subject}
    invalid_drive_extension["delivery"]["drive_receipt"]["receipt_sha256"] = digest(invalid_drive_extension_subject)
    invalid_drive_time = json.loads(json.dumps(cloud_completed))
    invalid_drive_time["delivery"]["drive_receipt"]["readback_at"] = "2026-08-26T08:00:00+00:00"
    invalid_drive_time_subject = {key: invalid_drive_time["delivery"]["drive_receipt"][key] for key in drive_subject}
    invalid_drive_time["delivery"]["drive_receipt"]["receipt_sha256"] = digest(invalid_drive_time_subject)
    invalid_drive_without_export = json.loads(json.dumps(cloud_completed))
    invalid_drive_without_export["delivery"]["export_status"] = "pending"
    invalid_drive_without_export["delivery"].pop("export_receipt")
    invalid_authorization_expansion = json.loads(json.dumps(cloud_checkpoint))
    invalid_authorization_expansion["approval_gates"]["cloud"]["destination_scope_subject"]["root_scope_label"] = "different root"
    invalid_publish_scope = fixture()
    invalid_publish_scope["approval_gates"]["publish"].update(status="approved", receipt="publish approved", explicit_approval=True, checkpoint="separate", authorized_actions=["new_export"])
    invalid_publish_hash, invalid_publish_visible = expected_hashes(invalid_publish_scope)
    invalid_publish_scope["integrity"] = {"production_payload_sha256": invalid_publish_hash, "visible_content_sha256": invalid_publish_visible}
    for value in invalid_publish_scope["approval_gates"].values():
        value["bound_production_payload_sha256"] = invalid_publish_hash
        value["bound_visible_content_sha256"] = invalid_publish_visible
    publish_checkpoint = fixture()
    publish_visible = expected_hashes(publish_checkpoint)[1]
    publish_scope = {"destination_kind": "tiktok_account", "destination_label": "verified TikTok account", "visible_content_sha256": publish_visible}
    publish_checkpoint["approval_gates"]["publish"].update(status="approved", receipt="publish approved", explicit_approval=True, checkpoint="separate", authorized_actions=["publish"], external_scope_subject=publish_scope, external_scope_sha256=digest(publish_scope))
    publish_hash, publish_visible = expected_hashes(publish_checkpoint)
    publish_checkpoint["integrity"] = {"production_payload_sha256": publish_hash, "visible_content_sha256": publish_visible}
    for value in publish_checkpoint["approval_gates"].values():
        value["bound_production_payload_sha256"] = publish_hash
        value["bound_visible_content_sha256"] = publish_visible
    invalid_problem_resolution_fact = fixture()
    invalid_problem_resolution_fact["script"][4]["fact_refs"] = ["missing-fact"]
    invalid_problem_resolution_fact["script_review_receipt"]["cuts"][4]["fact_refs"] = ["missing-fact"]
    invalid_problem_resolution_fact["component_hashes"]["script_sha256"] = digest(invalid_problem_resolution_fact["script"])
    problem_hash, problem_visible = expected_hashes(invalid_problem_resolution_fact)
    invalid_problem_resolution_fact["integrity"] = {"production_payload_sha256": problem_hash, "visible_content_sha256": problem_visible}
    for value in invalid_problem_resolution_fact["approval_gates"].values():
        value["bound_production_payload_sha256"] = problem_hash
        value["bound_visible_content_sha256"] = problem_visible
    invalid_problem_resolution_media = fixture()
    invalid_problem_resolution_media["script"][4]["media_evidence_asset_id"] = "asset-does-not-exist"
    invalid_problem_resolution_media["component_hashes"]["script_sha256"] = digest(invalid_problem_resolution_media["script"])
    media_hash, media_visible = expected_hashes(invalid_problem_resolution_media)
    invalid_problem_resolution_media["integrity"] = {"production_payload_sha256": media_hash, "visible_content_sha256": media_visible}
    for value in invalid_problem_resolution_media["approval_gates"].values():
        value["bound_production_payload_sha256"] = media_hash
        value["bound_visible_content_sha256"] = media_visible
    cases += [("valid script checkpoint receipt", script_checkpoint, False), ("valid rough checkpoint receipt", rough_checkpoint, False), ("valid final checkpoint before append-only export outcome", final_pending_checkpoint, False), ("valid final checkpoint after append-only export outcome", final_checkpoint, False), ("valid exact cloud checkpoint scope", cloud_checkpoint, False), ("valid append-only Drive readback", cloud_completed, False), ("valid destination-scoped publish approval", publish_checkpoint, False), ("reject Drive name not matching current export", invalid_drive_name, True), ("reject Drive extension not matching current export", invalid_drive_extension, True), ("reject Drive readback before export", invalid_drive_time, True), ("reject completed Drive without completed export", invalid_drive_without_export, True), ("reject authorization-plan expansion without new binding", invalid_authorization_expansion, True), ("reject publish scope confused with export", invalid_publish_scope, True), ("reject unsupported problem resolution fact", invalid_problem_resolution_fact, True), ("reject disconnected problem resolution media", invalid_problem_resolution_media, True)]
    cases.append(("valid pending export", pending, False))
    cases += [("short model", fixture(model="AN-A12"), True), ("long model", fixture(model="AN-ABCDEFG"), True)]
    mutations = (("model conflict", lambda p: p["manifest"][0].update(observed_product_models=["AN-T001", "AN-X999"])), ("explicit conflict hold", lambda p: p["product_info"]["product_model_provenance"].update(status="conflict")), ("legacy model alias", lambda p: p["product_info"].update(observed_value="AN-T001")), ("missing script closure", lambda p: p["script"].pop(0)), ("no-TTS caption CTA", lambda p: p["captions"][-1].update(text="下からチェック")), ("script exposes model", lambda p: p["script"][0].update(dialogue=p["product_info"]["product_model"])), ("caption exposes model", lambda p: p["captions"][0].update(text=p["product_info"]["product_model"])), ("tts exposes model", lambda p: p["tts"][0].update(text=p["product_info"]["product_model"])), ("legacy cut alias", lambda p: p["cuts"][0].update(required_media_description="x")), ("sidecar unverified", lambda p: p["cuts"][0]["matched_sidecar_receipt"].update(status="pending")), ("sidecar bad path", lambda p: p["cuts"][0]["matched_sidecar_receipt"].update(sidecar_relative_path="media/other.json")), ("additional approved edit", lambda p: p["approval_gates"]["edit"].update(status="approved", receipt="OK")), ("wrong mapped checkpoint receipt", lambda p: p["approval_gates"]["export"].update(status="approved", receipt="完成・書き出しOK", explicit_approval=True, checkpoint="script", authorized_actions=["new_export"])), ("path traversal", lambda p: p["delivery"]["portable_handoff"]["assets"][0].update(media_relative_path="media/../product.mp4")), ("unicode path alias", lambda p: p["delivery"]["portable_handoff"]["assets"].append({"asset_id": "asset-alias", "media_sha256": "d" * 64, "media_relative_path": "MEDIA/Product.MP4", "sidecar_sha256": "e" * 64, "sidecar_relative_path": "MEDIA/Product.sidecar.json", "classification": {"original": False, "editable_project_dependency": False, "shared": False, "uncertain": False}})), ("stale integrity", lambda p: p["integrity"].update(visible_content_sha256="0" * 64)), ("unbound approval", lambda p: p["approval_gates"]["export"].update(bound_visible_content_sha256="0" * 64)), ("cleanup path", lambda p: p["cleanup_preflight"]["local_working_download_candidates"][0].update(path="media/product.mp4")), ("cleanup execute", lambda p: p["cleanup_preflight"].update(execute=True)), ("cleanup original", lambda p: p["delivery"]["portable_handoff"]["assets"][0]["classification"].update(original=True)), ("prohibition matches", lambda p: p["openclaw_prohibition"].update(matched_rule_ids=["rule-1"])), ("prohibition stale hash", lambda p: p["openclaw_prohibition"].update(bound_visible_content_sha256="0" * 64)), ("shop userinfo", lambda p: p["camee_tiktok_shop"].update(url="https://user@shop.tiktok.com/view/product/123456789012")), ("shop nonstandard port", lambda p: p["camee_tiktok_shop"].update(url="https://shop.tiktok.com:444/view/product/123456789012")), ("shop short id", lambda p: p["camee_tiktok_shop"].update(url="https://shop.tiktok.com/view/product/123")), ("shop bad id", lambda p: p["camee_tiktok_shop"].update(product_id="123")), ("shop stale hash", lambda p: p["camee_tiktok_shop"].update(bound_production_payload_sha256="0" * 64)))
    mutations += (("semantic description forged", lambda p: p["cuts"][0]["media_requirements"].update(canonical_description="freeform")), ("must-show none visibility", lambda p: p["cuts"][0]["media_requirements"]["must_show"][0].update(visibility="none")), ("legacy component alias", lambda p: p.update(component_hash="0" * 64)), ("stale component hash", lambda p: p["component_hashes"].update(cuts_sha256="0" * 64)), ("caption editor missing", lambda p: p["captions"][0].pop("style")), ("caption bottom position", lambda p: p["captions"][0].update(position="bottom")), ("caption template missing", lambda p: p["captions"][0].pop("template_requirement")), ("caption template unofficial", lambda p: p["captions"][0]["template_requirement"].update(source="manual")), ("QA axis missing", lambda p: p["design_quality_qa"]["axes"].pop()), ("manifest accounting missing", lambda p: p["manifest"][0].pop("limitations")), ("portable setup altered", lambda p: p["portable_setup"].update(setup_steps=["import_assets"])))
    mutations += (("source receipt mismatch", lambda p: p["cuts"][0]["matched_sidecar_receipt"].update(asset_id="asset-other")), ("additional source present", lambda p: p["cuts"][0].update(source_asset_id="asset-product", source_in=0.0, source_out=2.0)), ("manifest ref reordered", lambda p: p["manifest_ref"].append(dict(p["manifest_ref"][0]))), ("fact source SHA mismatch", lambda p: p["facts_used"][0]["material_refs"][0].update(sha256="0" * 64)), ("caption exceeds cut", lambda p: p["captions"][0].update(timeline_out=3.0)), ("tts exceeds cut", lambda p: p["tts"][0].update(timeline_out=3.0)), ("QA duplicate axis", lambda p: p["design_quality_qa"]["axes"].__setitem__(1, dict(p["design_quality_qa"]["axes"][0]))), ("QA total mismatch", lambda p: p["design_quality_qa"].update(total_score=1)), ("post set missing", lambda p: p.pop("post_set")))
    mutations += (("reused caption source asset", lambda p: p["cuts"][1].update(source_asset_id=p["cuts"][0]["source_asset_id"])), ("same media SHA asset alias", lambda p: p["delivery"]["portable_handoff"]["assets"][1].update(media_sha256=p["delivery"]["portable_handoff"]["assets"][0]["media_sha256"])))
    mutations += (("TTS wording mismatch", lambda p: p["tts"][0].update(text="別の読み上げ")), ("TTS punctuation mismatch", lambda p: p["tts"][-1].update(text="下からチェック!")), ("caption starts mid-cut", lambda p: p["captions"][0].update(timeline_in=0.5)), ("no-narration caption starts mid-cut", lambda p: p["captions"][0].update(timeline_in=0.5)), ("stale five-stage script", lambda p: p["script"].pop(4)), ("script role missing", lambda p: p["script"][2].update(narrative_role="product")), ("script order reversed", lambda p: p["script"].reverse()), ("cuts overlap", lambda p: p["cuts"][1].update(timeline_in=1.5)), ("TTS partial acceleration", lambda p: p["tts"][0].update(speed=1.3)), ("TTS unsupported acceleration", lambda p: [item.update(speed=1.1) for item in p["tts"]]), ("TTS huge acceleration", lambda p: [item.update(speed=10 ** 10000) for item in p["tts"]]), ("TTS boolean speed", lambda p: [item.update(speed=True) for item in p["tts"]]), ("policy and TTS boolean speed", lambda p: (p["narration_policy"].update(common_speed=True), [item.update(speed=True) for item in p["tts"]])), ("TTS boolean pitch", lambda p: [item.update(pitch=True) for item in p["tts"]]), ("TTS voice mismatch", lambda p: p["tts"][0].update(voice="another")), ("default voice replaced", lambda p: p["voice_policy"].update(preset="neutral")), ("stale overflow strategy", lambda p: p["narration_policy"].update(timing_strategy="accelerated_after_visual_fit", common_speed=1.2)), ("slow strategy without slowed cut", lambda p: p["narration_policy"].update(timing_strategy="slow_video_and_caption", common_speed=1.2, overflow_cut_ids=["cut-03"], overflow_reason="still insufficient")), ("short final visual", lambda p: p["cuts"][-1].update(source_out=0.1)), ("final editor boolean speed", lambda p: p["cuts"][-1]["editor"].update(speed=True)), ("non-final editor NaN speed", lambda p: p["cuts"][0]["editor"].update(speed=float("nan"))), ("non-final editor infinity speed", lambda p: p["cuts"][0]["editor"].update(speed=float("inf"))), ("final visual receipt missing", lambda p: p["final_visual_policy"].update(receipt="")), ("old schema version", lambda p: p["portable_setup"].update(schema_version="1")), ("no TTS without explicit exception", lambda p: p.pop("narration_policy")))
    mutations += (("script exceeds cut", lambda p: p["script"][0].update(timeline_out=3.0)), ("fact non-verified", lambda p: p["facts_used"][0].update(classification="review_observation")), ("QA metric alias", lambda p: p["design_quality_qa"].update(metrics={"watch": "not_measured"})), ("manifest source alias", lambda p: p["manifest"][0].update(source_reference="legacy")), ("manifest insecure source", lambda p: p["manifest"][0].update(source_location="http://example.invalid/product")), ("manifest absolute source", lambda p: p["manifest"][0].update(source_location=chr(47) + "local/file")))
    mutations += (("time bool", lambda p: p["cuts"][0].update(timeline_in=True)), ("time string", lambda p: p["cuts"][0].update(timeline_in="0")), ("time none", lambda p: p["cuts"][0].update(timeline_in=None)), ("time NaN", lambda p: p["cuts"][0].update(timeline_in=float("nan"))), ("time infinity", lambda p: p["cuts"][0].update(timeline_out=float("inf"))), ("time negative", lambda p: p["cuts"][0].update(timeline_in=-0.1)), ("time zero", lambda p: p["cuts"][0].update(timeline_in=0.0, timeline_out=0.0)), ("time reversed", lambda p: p["cuts"][0].update(timeline_in=2.0, timeline_out=1.0)), ("source time string", lambda p: p["cuts"][0].update(source_in="0")), ("script time bool", lambda p: p["script"][0].update(timeline_in=True)), ("caption time NaN", lambda p: p["captions"][0].update(timeline_in=float("nan"))), ("TTS time infinity", lambda p: p["tts"][0].update(timeline_out=float("inf"))))
    mutations += (("export timestamp naive", lambda p: p["delivery"]["export_receipt"].update(exported_at="2026-08-26T18:16:24")), ("production ordinal boolean", lambda p: p["delivery"]["export_receipt"].update(production_ordinal=True)), ("production ordinal out of range", lambda p: p["delivery"]["export_receipt"].update(production_ordinal=21)), ("ordinal prior count mismatch", lambda p: p["delivery"]["export_receipt"]["prior_completed_exports"].update(count=1)), ("ordinal prior evidence ambiguous", lambda p: p["delivery"]["export_receipt"]["prior_completed_exports"].update(status="ambiguous")), ("legacy completed basename", lambda p: p["delivery"]["export_receipt"].update(completed_video_basename=f"AI作成_{p['product_info']['product_model']}_2026_08_04")))
    mutations += (("cross-day export timestamp/name mismatch", lambda p: p["delivery"]["export_receipt"].update(exported_at="2026-08-25T09:16:24+00:00")),)
    huge = 10 ** 10000
    mutations += (("cut huge int", lambda p: p["cuts"][0].update(timeline_out=huge)), ("source huge int", lambda p: p["cuts"][0].update(source_out=huge)), ("script huge int", lambda p: p["script"][0].update(timeline_out=huge)), ("caption huge int", lambda p: p["captions"][0].update(timeline_out=huge)), ("TTS huge int", lambda p: p["tts"][0].update(timeline_out=huge)), ("cut over practical maximum", lambda p: p["cuts"][0].update(timeline_out=86401)))
    for name, mutate in mutations:
        no_tts_case = name in {"no-TTS caption CTA", "no-narration caption starts mid-cut", "no TTS without explicit exception"}
        payload = fixture(True, True) if name.startswith(("prohibition", "shop")) else fixture(tts=not no_tts_case, additional=name in {"additional approved edit", "additional source present"})
        mutate(payload)
        cases.append((name, payload, True))
    missing_hold = [name for name, payload, _ in settings_cases if not any("HOLD_PRODUCT_VIDEO_SETTINGS" in error for error in errors_for(payload, trusted_settings(payload)))]
    if missing_hold:
        raise AssertionError("product-settings tests did not emit HOLD_PRODUCT_VIDEO_SETTINGS: " + ", ".join(missing_hold))
    failed = [name for name, payload, reject in cases if bool(errors_for(payload, trusted_settings(payload))) != reject]
    if failed:
        raise AssertionError("self-test failed: " + ", ".join(failed))
    print(f"self-test passed: {len(cases) + 2} cases")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("payload", nargs="?")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--settings-root", default=".", help="project root containing config/product_video_settings_<model>.v1.json")
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
    model = payload.get("product_info", {}).get("product_model") if isinstance(payload.get("product_info"), dict) else None
    trusted_settings = load_trusted_product_settings(args.settings_root, model)
    errors = errors_for(payload, trusted_settings)
    if errors:
        print("INVALID")
        print("\n".join(f"- {error}" for error in errors))
        return 1
    print("VALID")
    return 0


if __name__ == "__main__":
    sys.exit(main())
