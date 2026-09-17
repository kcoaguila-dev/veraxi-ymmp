import json
from pathlib import Path
from veraxi_ymmp.compiler import YMMPCompiler
from veraxi_ymmp.premiere_exporter import export_to_premiere

print("Starting export pipeline...")

# Load the script
script_path = Path("artifacts/script.json")
script = json.loads(script_path.read_text(encoding="utf-8-sig"))

# Initialize Voicevox
from veraxi_ymmp.voicevox import VoicevoxClient
vv = VoicevoxClient()
if not vv.ensure_started():
    print("Warning: VOICEVOX could not be started. Audio will not be generated.")
    vv = None

# We don't have a template path here, let's just use the full template from examples
speaker_map = {
    "ずんだもん": 3,
    "四国めたん": 2,
    "春日部つむぎ": 8,
}
compiler = YMMPCompiler("examples/full_template.ymmp", voicevox_client=vv, speaker_map=speaker_map)

print("Building timeline from script...")
# Build timeline IR
import time
audio_dir = Path(f"artifacts/audio_{int(time.time())}")
audio_dir.mkdir(parents=True, exist_ok=True)
timeline_ir, _ = compiler._build_ir(script, audio_dir)

print("Generating Premiere Pro XML + PNG Speech Bubbles...")
# Output directories
xml_dir = Path("artifacts/premiere_output")
proj_dir = Path("artifacts/premiere_project")
xml_dir.mkdir(parents=True, exist_ok=True)
proj_dir.mkdir(parents=True, exist_ok=True)

# Run the exporter in PNG mode (no MOGRT)
result = export_to_premiere(timeline_ir, xml_dir, proj_dir)

print(f"Success! Mode used: {result['mode']}")
print(f"Your Premiere XML is at: {result['xml_path']}")
print("You can now open Premiere Pro and import the XML!")
