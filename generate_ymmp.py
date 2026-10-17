from veraxi_ymmp.compiler import YMMPCompiler
from veraxi_ymmp.voicevox import VoicevoxClient
import json
from pathlib import Path

script = json.load(open('artifacts/script.json', encoding='utf-8-sig'))
vv = VoicevoxClient()
vv.ensure_started()
speaker_map = {'ずんだもん': 3, '四国めたん': 2, '春日部つむぎ': 8}
compiler = YMMPCompiler('examples/full_template.ymmp', voicevox_client=vv, speaker_map=speaker_map)
timeline_ir, audio_files = compiler.build_ir(script, Path('artifacts/audio'))
compiler.render_ymmp(timeline_ir, Path('artifacts/final_video.ymmp'), False, len(timeline_ir.voice_clips), audio_files)
print("YMMP generated successfully!")
