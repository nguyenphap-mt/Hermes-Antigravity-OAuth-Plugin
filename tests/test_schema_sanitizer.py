import sys
from pathlib import Path

_PLUGIN_DIR = Path(__file__).resolve().parent.parent
if str(_PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_DIR))

import pytest
from bridge.client import _clean_schema_for_gemini, _translate_tools_to_gemini


def test_clean_schema_removes_exclusive_minimum_and_maps():
    input_schema = {
        "type": "object",
        "properties": {
            "size_mm2": {"type": "number", "exclusiveMinimum": 0},
            "ratio": {"type": "number", "exclusiveMaximum": 100},
            "cores": {"type": "integer", "minimum": 1, "exclusiveMinimum": 0},
        },
        "additionalProperties": False,
        "$schema": "http://json-schema.org/draft-07/schema#",
    }

    cleaned = _clean_schema_for_gemini(input_schema)

    assert "additionalProperties" not in cleaned
    assert "$schema" not in cleaned
    assert cleaned["properties"]["size_mm2"] == {"type": "number", "minimum": 0}
    assert cleaned["properties"]["ratio"] == {"type": "number", "maximum": 100}
    # cores already has minimum=1, so exclusiveMinimum=0 should not overwrite minimum=1
    assert cleaned["properties"]["cores"] == {"type": "integer", "minimum": 1}


def test_clean_schema_nested_objects_and_arrays():
    input_schema = {
        "type": "object",
        "properties": {
            "items_list": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "value": {"type": "number", "exclusiveMinimum": 5},
                        "id": {"type": "string", "patternProperties": {".*": {}}},
                    },
                    "additionalProperties": False,
                }
            }
        }
    }

    cleaned = _clean_schema_for_gemini(input_schema)
    item_props = cleaned["properties"]["items_list"]["items"]["properties"]
    assert item_props["value"] == {"type": "number", "minimum": 5}
    assert "patternProperties" not in item_props["id"]
    assert "additionalProperties" not in cleaned["properties"]["items_list"]["items"]


def test_clean_schema_primitives_and_empty():
    assert _clean_schema_for_gemini(None) is None
    assert _clean_schema_for_gemini("string") == "string"
    assert _clean_schema_for_gemini([1, {"exclusiveMinimum": 2}]) == [1, {"minimum": 2}]
    assert _clean_schema_for_gemini({}) == {}


def test_translate_tools_to_gemini_integration():
    tools = [
        {
            "type": "function",
            "function": {
                "name": "benthanh_sales_lookup",
                "description": "Deterministic sales lookup",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "brand": {"type": "string"},
                        "size_mm2": {"type": "number", "exclusiveMinimum": 0},
                    },
                    "additionalProperties": False,
                }
            }
        }
    ]

    translated = _translate_tools_to_gemini(tools)
    assert len(translated) == 1
    assert "functionDeclarations" in translated[0]
    decl = translated[0]["functionDeclarations"][0]
    assert decl["name"] == "benthanh_sales_lookup"
    params = decl["parameters"]
    assert "additionalProperties" not in params
    assert params["properties"]["size_mm2"] == {"type": "number", "minimum": 0}
