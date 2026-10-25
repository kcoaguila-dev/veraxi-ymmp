import json
import pytest
from pathlib import Path
from veraxi_ymmp.history import (
    backup_project_script,
    list_script_history,
    restore_script_history,
    prune_history,
    cleanup_stale_audio,
)
from veraxi_ymmp.mcp_server import save_project_script


def test_backup_and_restore_cycle(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("veraxi_ymmp.mcp_server.workspace_path", lambda p: tmp_path / p)

    proj_dir = tmp_path / "projects" / "test_proj"
    proj_dir.mkdir(parents=True, exist_ok=True)

    # Initial script with 3 cuts
    initial_script = [
        {"character": "ずんだもん", "text": "初期のセリフ1なのだ！", "emotion": "happy", "motion": "none", "bgm": None, "sfx": None, "image": None},
        {"character": "四国めたん", "text": "初期のセリフ2ですわ。", "emotion": "normal", "motion": "none", "bgm": None, "sfx": None, "image": None},
        {"character": "ずんだもん", "text": "初期のセリフ3なのだ！", "emotion": "excited", "motion": "none", "bgm": None, "sfx": None, "image": None},
    ]
    (proj_dir / "script.json").write_text(json.dumps(initial_script, ensure_ascii=False), encoding="utf-8")
    (proj_dir / "broll_manifest.json").write_text(json.dumps([{"slide": 1}]), encoding="utf-8")

    # 1. Take a backup
    snap_id = backup_project_script(proj_dir, reason="manual_backup")
    assert snap_id is not None

    # Verify history list
    history = list_script_history(proj_dir)
    assert len(history) == 1
    assert history[0]["id"] == snap_id
    assert history[0]["cut_count"] == 3
    assert history[0]["has_broll"] is True
    assert "初期のセリフ1" in history[0]["preview"]

    # 2. Simulate overriding from GUI with a completely different script
    new_script = [
        {"character": "ずんだもん", "text": "上書きされた新しいセリフなのだ！", "emotion": "surprised", "motion": "none", "bgm": None, "sfx": None, "image": None}
    ]
    res_save = save_project_script("projects/test_proj", json.dumps(new_script, ensure_ascii=False))
    assert res_save["success"] is True
    assert res_save.get("backup_created") is not None

    # Current script on disk should now be the new script
    current_disk_script = json.loads((proj_dir / "script.json").read_text(encoding="utf-8"))
    assert len(current_disk_script) == 1
    assert current_disk_script[0]["text"] == "上書きされた新しいセリフなのだ！"

    # History should now have 2 snapshots
    history_after = list_script_history(proj_dir)
    assert len(history_after) == 2

    # 3. Restore the first snapshot
    restore_res = restore_script_history(proj_dir, snap_id)
    assert restore_res["success"] is True
    assert restore_res["cut_count"] == 3
    assert restore_res["restored_broll"] is True

    # Verification: script.json was restored to the initial 3 cuts
    restored_disk_script = json.loads((proj_dir / "script.json").read_text(encoding="utf-8"))
    assert len(restored_disk_script) == 3
    assert restored_disk_script[0]["text"] == "初期のセリフ1なのだ！"

    # Restore itself created a pre-restore backup, so history is now 3
    history_final = list_script_history(proj_dir)
    assert len(history_final) == 3


def test_cleanup_stale_audio_on_override(tmp_path: Path) -> None:
    proj_dir = tmp_path / "audio_proj"
    audio_dir = proj_dir / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)

    # Create dummy audio files for cuts 0, 1, 2, 3, 4
    for i in range(5):
        (audio_dir / f"{i:03d}_zundamon.wav").write_bytes(b"RIFFdummy")
        (audio_dir / f"{i:03d}_zundamon.meta.json").write_text("{}", encoding="utf-8")

    assert len(list(audio_dir.glob("*.wav"))) == 5

    # If the new script only has 2 cuts (0 and 1), cuts 2, 3, 4 should be cleaned up
    cleaned = cleanup_stale_audio(proj_dir, active_cut_count=2)
    # 3 wav files + 3 meta files = 6 files removed
    assert cleaned == 6
    remaining_wavs = sorted([f.name for f in audio_dir.glob("*.wav")])
    assert remaining_wavs == ["000_zundamon.wav", "001_zundamon.wav"]


def test_prune_history(tmp_path: Path) -> None:
    proj_dir = tmp_path / "prune_proj"
    proj_dir.mkdir(parents=True, exist_ok=True)
    script_file = proj_dir / "script.json"
    script_file.write_text(json.dumps([{"character": "a", "text": "b"}]), encoding="utf-8")

    # Create 5 snapshots
    import time
    for i in range(5):
        backup_project_script(proj_dir, reason=f"test_{i}", max_history=10)
        time.sleep(0.01)

    assert len(list_script_history(proj_dir)) == 5

    # Prune to max 2
    removed = prune_history(proj_dir, max_history=2)
    assert removed == 3
    remaining = list_script_history(proj_dir)
    assert len(remaining) == 2


def test_invalid_history_id_rejection(tmp_path: Path) -> None:
    proj_dir = tmp_path / "bad_proj"
    proj_dir.mkdir(parents=True, exist_ok=True)

    with pytest.raises(ValueError, match="Invalid history ID"):
        restore_script_history(proj_dir, "../../../evil_id")
