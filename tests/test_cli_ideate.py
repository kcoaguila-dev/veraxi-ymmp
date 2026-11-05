import json
from pathlib import Path
from veraxi_ymmp.cli_ideate import cmd_ideate, ARCHETYPES


def test_cli_ideate_creates_expected_artifacts(tmp_path: Path) -> None:
    target_dir = tmp_path / "test_topic"
    argv = [
        "CrowdStrike Kernel Sensor Outage",
        "--archetype", "post_mortem",
        "--output", str(target_dir)
    ]

    cmd_ideate(argv)

    assert target_dir.exists()
    dossier_file = target_dir / "notebooklm_dossier.md"
    manifest_file = target_dir / "sources" / "manifest.json"
    seed_file = target_dir / "script_seed.json"

    assert dossier_file.exists()
    assert manifest_file.exists()
    assert seed_file.exists()

    dossier_text = dossier_file.read_text(encoding="utf-8")
    assert "CrowdStrike Kernel Sensor Outage" in dossier_text
    assert "Evidence Extraction Matrix" in dossier_text
    assert "Strict negative filter" in dossier_text

    manifest_json = json.loads(manifest_file.read_text(encoding="utf-8"))
    assert manifest_json["topic"] == "CrowdStrike Kernel Sensor Outage"
    assert manifest_json["archetype"] == "post_mortem"

    seed_json = json.loads(seed_file.read_text(encoding="utf-8"))
    assert "ずんだもん" in seed_json["characters"]
    assert "四国めたん" in seed_json["characters"]
    assert "春日部つむぎ" in seed_json["characters"]


def test_cli_ideate_all_archetypes(tmp_path: Path) -> None:
    for arch_key in ARCHETYPES.keys():
        target_dir = tmp_path / f"test_{arch_key}"
        argv = [f"Topic {arch_key}", "--archetype", arch_key, "--output", str(target_dir)]
        cmd_ideate(argv)
        assert (target_dir / "notebooklm_dossier.md").exists()
