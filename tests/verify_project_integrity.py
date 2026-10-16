"""
Standalone verification script for generated YMMP project files.
Inspects audio, tachie, characters, subtitles, and layout bounds.
"""
import json
import sys
import base64
import brotli
from pathlib import Path

def verify_project(ymmp_path_str: str):
    ymmp_path = Path(ymmp_path_str)
    if not ymmp_path.exists():
        print(f"FAIL: File {ymmp_path} does not exist.")
        sys.exit(1)

    with open(ymmp_path, 'r', encoding='utf-8-sig') as f:
        data = json.load(f)

    timelines = data.get('Timelines') or [data.get('Timeline')]
    tl = timelines[0]
    items = tl['Items']

    print("=======================================================")
    print(f"  VERIFYING YMMP INTEGRITY: {ymmp_path.name}")
    print("=======================================================")
    print(f"Total Timeline Items: {len(items)}")
    print(f"Total Duration (frames): {tl['Length']} ({tl['Length']/60:.2f}s)")
    print(f"MaxLayer: {tl['MaxLayer']}")

    layer_counts = {}
    for it in items:
        l = it.get('Layer', -1)
        layer_counts[l] = layer_counts.get(l, 0) + 1
    for l in sorted(layer_counts.keys()):
        print(f"  Layer {l}: {layer_counts[l]} items")

    # 1. Speech Voice & Native Lip-Sync Driver (Layer 9 VoiceItem)
    voices = [it for it in items if it.get('Layer') == 9 and 'VoiceItem' in it.get('$type', '')]
    print(f"\n[1] Speech Voice & Lip-Sync Driver (Layer 9): {len(voices)} items")
    assert len(voices) > 0, "No VoiceItems found on Layer 9!"
    for i, v in enumerate(voices):
        char = v.get('CharacterName')
        # A. FilePath and Hatsuon
        hatsuon = v.get('Hatsuon', '')
        assert hatsuon, f"VoiceItem[{i}] ({char}) has empty Hatsuon!"
        fp = v.get('FilePath', '')
        assert fp, f"VoiceItem[{i}] ({char}) has empty FilePath!"
        f_path = Path(fp)
        assert f_path.exists(), f"VoiceItem[{i}] ({char}) audio file missing: {f_path}"
        assert f_path.stat().st_size > 0, f"VoiceItem[{i}] ({char}) audio file is 0 bytes: {f_path}"
        
        # B. Brotli-compressed VoiceCache
        vc = v.get('VoiceCache', '')
        assert vc, f"VoiceItem[{i}] ({char}) VoiceCache is empty! YMM4 requires VoiceCache for waveform calculation & lip-sync."
        decompressed = brotli.decompress(base64.b64decode(vc))
        assert len(decompressed) >= 44, f"VoiceItem[{i}] ({char}) decompressed audio too small: {len(decompressed)}"
        assert decompressed[:4] == b"RIFF" and decompressed[8:12] == b"WAVE", f"VoiceItem[{i}] ({char}) VoiceCache is not valid RIFF/WAVE!"
        
        # C. Timing and waveform flags
        v_len = v.get('VoiceLength', '00:00:00')
        assert v_len != '00:00:00', f"VoiceItem[{i}] ({char}) VoiceLength is 0: {v_len}"
        assert v.get('IsWaveformEnabled') is True, f"VoiceItem[{i}] ({char}) IsWaveformEnabled is False!"
        
        # D. Volume
        vol = v.get('Volume', {}).get('Values', [{}])[0].get('Value', 0.0)
        assert vol > 0, f"VoiceItem[{i}] ({char}) volume is 0: {vol}"
    print(f"  -> All {len(voices)} VoiceItems have verified Brotli VoiceCache, CustomVoice Hatsuon, and valid waveform durations!")

    # 2. BGM Audio
    bgm_audio = [it for it in items if it.get('Layer') == 3 and 'AudioItem' in it.get('$type', '')]
    print(f"\n[2] BGM Audio (Layer 3): {len(bgm_audio)} items")
    assert len(bgm_audio) > 0, "No BGM AudioItem found on Layer 3!"
    for b in bgm_audio:
        bfp = Path(b.get('FilePath', ''))
        assert bfp.exists(), f"BGM file missing: {bfp}"
    print(f"  -> BGM exists on Layer 3!")

    # 3. Tachie Characters
    tachie_items = [it for it in items if 'TachieItem' in it.get('$type', '')]
    print(f"\n[3] Tachie Characters (Layers 4 & 6): {len(tachie_items)} items")
    assert len(tachie_items) > 0, "No TachieItems found in timeline!"
    for i, t in enumerate(tachie_items):
        char = t.get('CharacterName')
        layer = t.get('Layer')
        assert layer in (4, 6), f"Tachie item on wrong layer: {layer}"
        tip = t.get('TachieItemParameter', {})
        el = tip.get('EnableLayers', [])
        assert len(el) > 0, f"Tachie item {char} at frame {t.get('Frame')} has empty EnableLayers!"
        for lid in el:
            assert lid.startswith('n'), f"Invalid layer ID {lid}"
        x = t.get('X', {}).get('Values', [{}])[0].get('Value', 0.0)
        y = t.get('Y', {}).get('Values', [{}])[0].get('Value', 0.0)
        z = t.get('Zoom', {}).get('Values', [{}])[0].get('Value', 0.0)
        assert abs(x) <= 1200, f"Tachie off screen: X={x}"
        print(f"  Tachie {char:6s} L{layer} Frame {t.get('Frame'):5d}-{t.get('Frame')+t.get('Length'):5d} | Pos: X={x:6.1f}, Y={y:5.1f}, Zoom={z:4.1f}% | EnableLayers: {len(el)} IDs")

    # 4. TachieFaceItems
    face_items = [it for it in items if 'TachieFaceItem' in it.get('$type', '')]
    print(f"\n[4] TachieFaceItems (facial expressions & 2-state lip-sync): {len(face_items)} items")
    forbidden_zunda_mouths = {'n104', 'n110', 'n111', 'n112', 'n113'}
    forbidden_metan_mouths = {'n39', 'n41', 'n42', 'n43', 'n46'}
    for f_it in face_items:
        char = f_it.get('CharacterName')
        fl = f_it.get('Layer')
        assert fl in (5, 7, 10, 11), f"TachieFaceItem on wrong layer: {fl}"
        tfp = f_it.get('TachieFaceParameter', {})
        el = tfp.get('EnableLayers', [])
        assert len(el) > 0, "Face item has empty EnableLayers!"
        assert tfp.get('MouthAnimation') in ("VolumeLipSyncPriority", "VowelLipSyncPriority", "AlwaysOpen", "AlwaysClose"), f"Invalid MouthAnimation: {tfp.get('MouthAnimation')}"
        # Strict 2-state lip-sync check: only 1 open mouth + 1 closed mouth allowed (rival standard)
        allowed_mouths = {'n108', 'n109'} if 'ずんだ' in char else {'n47', 'n48'}
        forbidden_mouths = forbidden_zunda_mouths if 'ずんだ' in char else forbidden_metan_mouths
        assert set(el) & allowed_mouths, f"TachieFaceItem ({char}) at frame {f_it.get('Frame')} missing 2-state mouth layer {allowed_mouths}! Found: {el}"
        assert not (set(el) & forbidden_mouths), f"TachieFaceItem ({char}) at frame {f_it.get('Frame')} contains unnatural extra mouth layer {set(el) & forbidden_mouths}!"

    # 5. Subtitle Plates
    plates = [it for it in items if it.get('Layer') == 8 and 'ImageItem' in it.get('$type', '')]
    print(f"\n[5] Subtitle Plates (Layer 8): {len(plates)} items")
    assert len(plates) == len(voices), f"Plate count {len(plates)} != voice count {len(voices)}"
    for p in plates:
        pfp = Path(p.get('FilePath', ''))
        assert pfp.exists(), f"Plate image missing: {pfp}"
    print(f"  -> All {len(plates)} custom-fitted speech bubble plates exist!")

    # 6. Characters Section
    print("\n[6] Characters Root Definition:")
    for c in data.get('Characters', []):
        name = c.get('Name')
        tcp = c.get('TachieCharacterParameter', {})
        tdfp = c.get('TachieDefaultFaceParameter', {})
        psd_path = Path(tcp.get('FilePath', ''))
        assert psd_path.exists(), f"PSD does not exist: {psd_path}"
        ttype = c.get('TachieType', '')
        assert 'PsdTachiePlugin' in ttype, f"Character {name} TachieType is '{ttype}', must contain PsdTachiePlugin!"
        sens = tcp.get('MouthSensitivity', 0.0)
        assert sens >= 150.0, f"MouthSensitivity is {sens}, must be >= 150.0 for reliable speech lip-sync"
        el = tdfp.get('EnableLayers', [])
        assert len(el) > 0, f"Character {name} has empty default EnableLayers"
        expected_mouth = 'n109' if 'ずんだ' in name else 'n47'
        assert expected_mouth in el, f"Character {name} default EnableLayers missing mouth layer {expected_mouth}!"
        print(f"  Character \"{name}\": PSD exists ({psd_path.name}), TachieType=OK, MouthSens={sens}, EnableLayers={len(el)} IDs (includes {expected_mouth})")

    print("\n=======================================================")
    print("  ALL 6 YMMP QA VERIFICATION SUITES PASSED 100%!")
    print("=======================================================")

if __name__ == '__main__':
    path = sys.argv[1] if len(sys.argv) > 1 else 'projects/02_market_analysis_2026/ymmp/final_video.ymmp'
    verify_project(path)
