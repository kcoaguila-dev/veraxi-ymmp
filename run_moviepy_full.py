import json
from pathlib import Path
from veraxi_ymmp.compiler import YMMPCompiler
from veraxi_ymmp.voicevox import VoicevoxClient
from veraxi_ymmp.moviepy_renderer import MoviePyRenderer

print("Loading script...", flush=True)
script = json.load(open('artifacts/script.json', encoding='utf-8-sig'))
print("Initializing compiler...", flush=True)
compiler = YMMPCompiler('examples/full_template.ymmp', voicevox_client=VoicevoxClient())
print("Building Timeline IR...", flush=True)
timeline_ir, _ = compiler._build_ir(script, Path('artifacts/audio'))
print("Initializing MoviePyRenderer...", flush=True)
renderer = MoviePyRenderer(timeline_ir)
print("Rendering FULL MP4...", flush=True)
renderer.render('artifacts/final_video.mp4')
print('MoviePy MP4 Rendered.', flush=True)
