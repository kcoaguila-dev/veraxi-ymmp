import json
from pathlib import Path
from veraxi_ymmp.compiler import YMMPCompiler
from veraxi_ymmp.voicevox import VoicevoxClient
from veraxi_ymmp.moviepy_renderer import MoviePyRenderer

print("Loading script...", flush=True)
script = json.load(open('artifacts/script.json', encoding='utf-8-sig'))
print("Initializing compiler...", flush=True)
vv = VoicevoxClient()
if not vv.ensure_started():
    print("Warning: VOICEVOX could not be started. Audio will not be generated.")
    vv = None
speaker_map = {
    "ずんだもん": 3,
    "四国めたん": 2,
    "春日部つむぎ": 8,
}
compiler = YMMPCompiler('examples/full_template.ymmp', voicevox_client=vv, speaker_map=speaker_map)
print("Building Timeline IR...", flush=True)
timeline_ir, _ = compiler._build_ir(script, Path('artifacts/audio'))
print("Initializing MoviePyRenderer...", flush=True)
renderer = MoviePyRenderer(timeline_ir)
# Smart QA Duration: Render just enough to see every character speak at least once
seen_chars = set()
smart_duration = 2.0
for vc in script:
    if "character" in vc and vc["character"] not in seen_chars:
        seen_chars.add(vc["character"])
        # Give them 2 seconds to finish their line
        smart_duration = max(smart_duration, timeline_ir.total_frames / timeline_ir.fps) # Approximation since we don't map time easily here, let's just use 10s default
        
renderer.fast_qa_duration = 25.0 # Render 10 seconds to ensure we see Metan speak
print("Rendering MP4...", flush=True)
renderer.render('artifacts/qa_test.mp4')
print('MoviePy MP4 Rendered.', flush=True)
