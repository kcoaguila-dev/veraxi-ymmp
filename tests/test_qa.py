import json
import pytest
from pathlib import Path
from veraxi_ymmp.template import get_timeline

def test_qa_output_ymmp():
    ymmp_path = "artifacts/final_video.ymmp"
    if not Path(ymmp_path).exists():
        pytest.skip(f"No {ymmp_path} available to test")
        
    with open(ymmp_path, 'r', encoding='utf-8-sig') as f:
        data = json.load(f)
        
    timeline = get_timeline(data)
    items = timeline.get("Items", [])
    
    # 1. Assert no bgm.ogg exists (duplicate BGM)
    has_bgm_ogg = any("bgm.ogg" in str(item) for item in items)
    assert not has_bgm_ogg, "Found duplicated 'bgm.ogg' from template in the output timeline!"
        
    # 2. Assert Zundamon PSD path is injected
    characters = data.get("Characters", [])
    zundamon = next((c for c in characters if "Zundamon" in c.get("Name", "")), None)
    assert zundamon is not None, "Zundamon character not found in project!"
        
    psd_path = zundamon.get("TachieCharacterParameter", {}).get("FilePath")
    assert psd_path, "TachieCharacterParameter.FilePath is missing!"
    assert "YourUser" not in psd_path, f"PSD path is still anonymized! {psd_path}"
    assert Path(psd_path).exists(), f"PSD path does not exist on disk! {psd_path}"
        
    # 3. Assert Subtitles are large
    font_size = zundamon.get("FontSize", 0)
    assert font_size >= 80.0, f"Subtitle font size is {font_size}, expected >= 80.0!"
        
    # 4. Assert layout overrides
    y_pos = zundamon.get("Y", 0)
    assert y_pos == 450.0, f"Subtitle Y position is {y_pos}, expected 450.0!"
