import json
from pathlib import Path

from lab_v4_dev.nlu.language_adapter import adapt
from lab_v4_dev.nlu.semantic_normalizer import normalize_text
from lab_v4_dev.nlu.entity_extractor import extract_component, extract
from lab_v4_dev.nlu.context_resolver import resolve


def test_semantic_normalizer_taa_normalization():
    assert normalize_text("مدرسة") == "مدرسه"
    assert normalize_text("مدرسة كبيرة") == "مدرسه كبيره"


def test_language_adapter_normalizes_common_arabic_variants():
    assert adapt("ماذا يفعل هذا؟") == "ما يفعل هذا"


def test_generic_english_word_is_not_component():
    assert extract_component("what is this") is None
    assert extract_component("how does it work") is None


def test_snake_case_component_is_component():
    assert extract_component("اشرح orchestrator_manager") == "orchestrator_manager"


def test_file_entity_has_priority():
    result = extract("حلل الملف orchestrator.py", "analyze_code")
    assert result["type"] == "FILE"
    assert result["value"] == "orchestrator.py"


def test_context_file_entity_can_be_inherited():
    result = resolve({
        "intent": "read_file",
        "target": "",
        "entity": {
            "type": "UNKNOWN",
            "value": "",
            "confidence": 0.0,
        },
    })
    assert isinstance(result, dict)


def test_context_does_not_inherit_version_for_file_intent(monkeypatch):
    import lab_v4_dev.nlu.context_resolver as cr

    monkeypatch.setattr(
        cr,
        "get_last_entity",
        lambda: {
            "action": "current_version",
            "entity": "v5.9.13",
            "entity_type": "VERSION",
        },
    )

    result = cr.resolve({
        "intent": "read_file",
        "target": "",
        "entity": {
            "type": "UNKNOWN",
            "value": "",
            "confidence": 0.0,
        },
    })

    assert result.get("target", "") == ""
    assert result.get("context_inherited", False) is False


def test_context_can_inherit_compatible_file(monkeypatch):
    import lab_v4_dev.nlu.context_resolver as cr

    monkeypatch.setattr(
        cr,
        "get_last_entity",
        lambda: {
            "action": "read_file",
            "entity": "orchestrator.py",
            "entity_type": "FILE",
        },
    )

    result = cr.resolve({
        "intent": "analyze_code",
        "target": "",
        "entity": {
            "type": "UNKNOWN",
            "value": "",
            "confidence": 0.0,
        },
    })

    assert result["target"] == "orchestrator.py"
    assert result["context_inherited"] is True


def test_nlu_data_files_are_valid_json():
    base = Path("lab_v4_dev/nlu")

    for name in (
        "language_patterns.json",
        "semantic_actions.json",
        "user_language.json",
        "nlu_context.json",
    ):
        json.loads((base / name).read_text(encoding="utf-8"))
