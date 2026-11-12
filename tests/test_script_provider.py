"""Phase 2: ScriptProvider port + ManualHandoffProvider + CLI --provider flag."""

import json

import pytest

import veraxi_ymmp.app.script_provider as sp
from veraxi_ymmp.app.cli import _cmd_ingest_script
from veraxi_ymmp.app.cli_ideate import cmd_ideate
from veraxi_ymmp.core.ports import ScriptProvider

GOOD_ENTRIES = [
    {
        "character": "zundamon",
        "text": "障害の原因が判明したのだ",
        "emotion": "happy",
        "motion": "none",
        "bgm": None,
        "sfx": None,
        "image": None,
    },
    {
        "character": "metan",
        "text": "根本原因は検証不足です",
        "emotion": "normal",
        "motion": "none",
        "bgm": None,
        "sfx": None,
        "image": None,
    },
]
GOOD_JSON = json.dumps(GOOD_ENTRIES, ensure_ascii=False)

BAD_EMOTION_JSON = json.dumps(
    [dict(GOOD_ENTRIES[0], emotion="super_happy"), GOOD_ENTRIES[1]],
    ensure_ascii=False,
)


def _paste_queue(*replies: str):
    queue = list(replies)
    return lambda: queue.pop(0)


def test_manual_provider_converges_after_bad_json():
    outputs: list = []
    provider = sp.ManualHandoffProvider(
        paste_fn=_paste_queue("this is not json", BAD_EMOTION_JSON, GOOD_JSON),
        output_fn=outputs.append,
    )
    entries = provider.generate_script("Test Topic", "dossier body")
    assert entries == sp.validate_pasted_script(GOOD_JSON)
    joined = "\n".join(outputs)
    assert joined.count("LLM RE-PROMPT BLOCK") == 2
    assert "Test Topic" in joined  # the prompt itself was printed


def test_manual_provider_accepts_fenced_json():
    provider = sp.ManualHandoffProvider(
        paste_fn=_paste_queue(f"Sure! Here you go:\n```json\n{GOOD_JSON}\n```"),
        output_fn=lambda _msg: None,
    )
    assert provider.generate_script("T", "D") == sp.validate_pasted_script(GOOD_JSON)


def test_manual_provider_is_idempotent_for_same_json():
    provider = sp.ManualHandoffProvider(
        paste_fn=lambda: GOOD_JSON, output_fn=lambda _msg: None
    )
    first = provider.generate_script("T", "D")
    second = provider.generate_script("T", "D")
    assert first == second
    assert json.dumps(first, ensure_ascii=False) == json.dumps(second, ensure_ascii=False)


def test_manual_provider_aborts_on_eof_and_empty():
    def eof():
        raise EOFError

    with pytest.raises(ValueError, match="aborted"):
        sp.ManualHandoffProvider(paste_fn=eof, output_fn=lambda _m: None).generate_script(
            "T", "D"
        )
    with pytest.raises(ValueError, match="empty"):
        sp.ManualHandoffProvider(
            paste_fn=lambda: "   ", output_fn=lambda _m: None
        ).generate_script("T", "D")


def test_manual_provider_max_attempts():
    provider = sp.ManualHandoffProvider(
        paste_fn=lambda: BAD_EMOTION_JSON,
        output_fn=lambda _m: None,
        max_attempts=2,
    )
    with pytest.raises(ValueError, match="did not converge after 2"):
        provider.generate_script("T", "D")


def test_manual_provider_satisfies_script_provider_protocol():
    provider = sp.ManualHandoffProvider(paste_fn=lambda: GOOD_JSON)
    assert isinstance(provider, ScriptProvider)


def test_generate_with_provider_dispatch():
    entries = sp.generate_with_provider(
        None, "T", "D", paste_fn=lambda: GOOD_JSON, output_fn=lambda _m: None
    )
    assert entries == sp.validate_pasted_script(GOOD_JSON)
    with pytest.raises(RuntimeError, match="no LLM API key"):
        sp.generate_with_provider("api", "T", "D")
    with pytest.raises(ValueError, match="Unknown script provider"):
        sp.generate_with_provider("bogus", "T", "D")


def test_build_script_prompt_reuses_export_spec_and_embeds_inputs():
    prompt = sp.build_script_prompt("My Topic", "DOSSIER-BODY")
    assert "Available Characters" in prompt
    assert "My Topic" in prompt
    assert "DOSSIER-BODY" in prompt
    assert "Output Contract" in prompt
    assert '"character"' in prompt  # JSON schema is embedded


def test_ideate_provider_manual_writes_validated_script(tmp_path, monkeypatch):
    captured = {}

    def fake_generate(name, topic, dossier, prompt_path=None):
        captured["name"] = name
        captured["prompt_path"] = prompt_path
        return sp.validate_pasted_script(GOOD_JSON)

    monkeypatch.setattr(sp, "generate_with_provider", fake_generate)
    target = tmp_path / "proj"
    cmd_ideate(["Some Topic", "--output", str(target), "--provider", "manual"])
    assert captured["name"] == "manual"
    script = json.loads((target / "script.json").read_text(encoding="utf-8"))
    assert script == sp.validate_pasted_script(GOOD_JSON)


def test_ideate_provider_flag_alone_defaults_to_manual(tmp_path, monkeypatch):
    seen = {}

    def fake_generate(name, topic, dossier, prompt_path=None):
        seen["name"] = name
        return sp.validate_pasted_script(GOOD_JSON)

    monkeypatch.setattr(sp, "generate_with_provider", fake_generate)
    cmd_ideate(["Topic", "--output", str(tmp_path / "p"), "--provider"])
    assert seen["name"] == "manual"


def test_ideate_provider_api_exits_with_clear_error(tmp_path):
    with pytest.raises(SystemExit) as excinfo:
        cmd_ideate(["Topic", "--output", str(tmp_path / "p"), "--provider", "api"])
    assert excinfo.value.code == 2
    assert not (tmp_path / "p" / "script.json").exists()


def test_ingest_script_provider_manual(tmp_path, monkeypatch):
    md = tmp_path / "dialogue_raw.md"
    md.write_text("ずんだもん: こんにちは\n四国めたん: 始めましょう\n", encoding="utf-8")

    def fake_generate(name, topic, dossier, prompt_path=None):
        assert "こんにちは" in dossier
        return sp.validate_pasted_script(GOOD_JSON)

    monkeypatch.setattr(sp, "generate_with_provider", fake_generate)
    _cmd_ingest_script([str(md), "--provider", "manual"])
    script = json.loads((tmp_path / "script.json").read_text(encoding="utf-8"))
    assert script == sp.validate_pasted_script(GOOD_JSON)
