import json
import copy
from typing import List, Dict, Any
from .template import load_template, extract_character_templates
from .hatsuon import Hatsuon

class YMMPCompiler:
    def __init__(self, template_path: str):
        self.template_data = load_template(template_path)
        self.character_templates = extract_character_templates(self.template_data)
        self.hatsuon = Hatsuon()

    def compile(self, script: List[Dict[str, str]], output_path: str, use_bom: bool = False):
        output_data = copy.deepcopy(self.template_data)
        items = []

        current_frame = 0

        for line in script:
            char_name = line["character"]
            text = line["text"]

            if char_name not in self.character_templates or self.character_templates[char_name]["voice"] is None:
                raise ValueError(f"Missing template for character: {char_name}")

            template_item = self.character_templates[char_name]["voice"]
            new_item = copy.deepcopy(template_item)

            new_item["Serif"] = text
            new_item["Hatsuon"] = self.hatsuon.convert(text)
            new_item["Frame"] = current_frame

            # Placeholder timing heuristic
            frames_per_char = 5
            min_length = 30
            length = max(min_length, len(text) * frames_per_char)
            new_item["Length"] = length

            new_item["VoiceCache"] = ""

            items.append(new_item)
            current_frame += length

        total_length = current_frame

        # Add TachieItems
        for char_name, templates in self.character_templates.items():
            if templates["tachie"] is not None:
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
