import json

from veraxi_ymmp.cli import _cmd_export_spec

def test_export_spec_markdown(capsys, tmp_path):
    output_path = tmp_path / "prompt.md"
    _cmd_export_spec(["--format", "markdown", "--output", str(output_path)])

    assert output_path.exists()
    content = output_path.read_text(encoding="utf-8")

    # Check that variables like AVAILABLE CHARACTERS are populated
    assert "Available Characters" in content
    assert "ずんだもん" in content

    # Check that the CLI output reflects the path
    out, err = capsys.readouterr()
    assert f"Exported to {output_path}" in out

def test_export_spec_json(capsys):
    _cmd_export_spec(["--format", "json"])

    out, err = capsys.readouterr()

    # Output should be valid JSON
    schema = json.loads(out)

    assert schema["$schema"] == "http://json-schema.org/draft-07/schema#"
    assert schema["type"] == "array"
    assert "character" in schema["items"]["properties"]
    assert "text" in schema["items"]["properties"]
    assert "emotion" in schema["items"]["properties"]
