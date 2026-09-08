import json
import copy
import os
from typing import List, Dict, Any, Optional
from .template import load_template, extract_character_templates
from .hatsuon import Hatsuon
from .voicevox import VoicevoxClient, VoicevoxError

class YMMPCompiler:
    def __init__(self,
                 template_path: str,
                 voicevox_client: Optional[VoicevoxClient] = None,
                 speaker_map: Optional[Dict[str, int]] = None,
                 default_speaker_id: int = 3):
        self.template_data = load_template(template_path)
        self.character_templates = extract_character_templates(self.template_data)
        self.hatsuon = Hatsuon()
        self.voicevox_client = voicevox_client
        self.speaker_map = speaker_map or {}
        self.default_speaker_id = default_speaker_id

    def compile(self, script: List[Dict[str, str]], output_path: str, use_bom: bool = False):
        output_data = copy.deepcopy(self.template_data)
        items = []

        if self.voicevox_client and not self.voicevox_client.is_available():
            raise RuntimeError(f"VOICEVOX server not reachable at {self.voicevox_client.base_url} — is it running?")

        current_frame = 0
        output_dir = os.path.dirname(os.path.abspath(output_path))
        audio_dir = os.path.join(output_dir, "audio")

        fps = self.template_data.get("Timeline", {}).get("VideoInfo", {}).get("FPS", 60)

        for idx, line in enumerate(script):
            char_name = line["character"]
            text = line["text"]

            if char_name not in self.character_templates or self.character_templates[char_name]["voice"] is None:
                raise ValueError(f"Missing template for character: {char_name}")

            template_item = self.character_templates[char_name]["voice"]
            new_item = copy.deepcopy(template_item)

            new_item["Serif"] = text
            new_item["Hatsuon"] = self.hatsuon.convert(text)
            new_item["Frame"] = current_frame

            if self.voicevox_client:
                speaker_id = self.speaker_map.get(char_name, self.default_speaker_id)
                try:
                    wav_bytes, duration = self.voicevox_client.synthesize(text, speaker_id)
                except VoicevoxError as e:
                    raise RuntimeError(f"Synthesis failed for '{char_name}' on line '{text}': {e}")

                os.makedirs(audio_dir, exist_ok=True)
                audio_filename = f"{idx:03d}_{char_name}.wav"
                audio_path = os.path.join(audio_dir, audio_filename)

                with open(audio_path, "wb") as f:
                    f.write(wav_bytes)

                length = round(duration * fps)
            else:
                # Placeholder timing heuristic
                frames_per_char = 5
                min_length = 30
                length = max(min_length, len(text) * frames_per_char)

            new_item["Length"] = length
            new_item["VoiceCache"] = ""

            items.append(new_item)
            current_frame += length

        total_length = current_frame

        # Build set of character names actually used in the script
        used_characters = set(line["character"] for line in script)

        # Add TachieItems
        for char_name, templates in self.character_templates.items():
            if char_name in used_characters and templates["tachie"] is not None:
                # Add tachie item covering the whole timeline
                tachie_item = copy.deepcopy(templates["tachie"])
                tachie_item["Frame"] = 0
                tachie_item["Length"] = total_length
                items.append(tachie_item)

        output_data["Timeline"]["Items"] = items
        output_data["Timeline"]["Length"] = total_length

        mode = 'w'
        encoding = 'utf-8-sig' if use_bom else 'utf-8'
        with open(output_path, mode, encoding=encoding) as f:
            json.dump(output_data, f, ensure_ascii=False, indent=4)
