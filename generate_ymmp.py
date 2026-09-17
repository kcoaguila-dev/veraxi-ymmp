from veraxi_ymmp.compiler import YMMPCompiler
from veraxi_ymmp.voicevox import VoicevoxClient
import json
from pathlib import Path

script = json.load(open('artifacts/script.json', encoding='utf-8-sig'))
vv = VoicevoxClient()
compiler = YMMPCompiler('examples/full_template.ymmp', voicevox_client=vv)
timeline_ir, _ = compiler._build_ir(script, Path('artifacts/audio'))
compiler._render_ymmp(timeline_ir, Path('artifacts/final_video.ymmp'), False, len(script), [])
print("YMMP generated successfully!")
