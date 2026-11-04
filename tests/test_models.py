import pytest

from scanner.analysis import schemas
from scanner.llm.models import build_model, output_mode, supported_parameters


def test_uses_schema_when_supported():
    assert output_mode({"structured_outputs", "response_format"}) == "schema"


def test_falls_back_to_json_mode():
    assert output_mode({"response_format"}) == "json"


def test_falls_back_to_free_text():
    assert output_mode(set()) == "text"


def test_without_model_list_assumes_support():
    assert supported_parameters(None, "any/model") is None
    assert output_mode(None) == "schema"


def test_models_are_written_as_provider_slash_model_id():
    config = {"providers": {"anthropic": {}}, "run": {"max_tokens": 1}}
    with pytest.raises(SystemExit, match="<provider>/<model id>"):
        build_model(config, "claude-sonnet-5-5")          # no provider
    with pytest.raises(SystemExit, match="anthropic"):
        build_model(config, "groq/some-model")            # unknown provider; the message lists the known ones


def test_schemas_are_strict_compatible():
    def check(node):
        if node.get("type") == "object":
            assert node["additionalProperties"] is False
            assert set(node["required"]) == set(node["properties"])
            for child in node["properties"].values():
                check(child)
        if node.get("type") == "array":
            check(node["items"])

    for schema in [schemas.FINDINGS, schemas.LESSONS, schemas.categories(["a", "other"])]:
        check(schema["schema"])
