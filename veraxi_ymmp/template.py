import json

def load_template(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)

def extract_character_templates(template_data):
    """
    Extracts the first VoiceItem and TachieItem for each character.
    Returns a dict mapping character name to {"voice": item, "tachie": item}.
    """
    character_templates = {}

    if "Characters" in template_data:
        for char in template_data["Characters"]:
            name = char.get("Name")
            if name:
                character_templates[name] = {"voice": None, "tachie": None}

    items = template_data.get("Timeline", {}).get("Items", [])

    for item in items:
        item_type = item.get("$type", "")
        char_name = item.get("CharacterName")

        if not char_name:
            continue

        if char_name not in character_templates:
            character_templates[char_name] = {"voice": None, "tachie": None}

        if "VoiceItem" in item_type and character_templates[char_name]["voice"] is None:
            character_templates[char_name]["voice"] = item

        if "TachieItem" in item_type and character_templates[char_name]["tachie"] is None:
            character_templates[char_name]["tachie"] = item

    return character_templates
