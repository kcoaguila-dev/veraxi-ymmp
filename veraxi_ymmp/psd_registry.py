"""
PSD Registry for YMM4 characters.

Encapsulates character PSD path resolution, layer definitions, facial expressions,
mouth animation layers, spatial layouts, and YMM4 character definitions.
Supports dynamic character registration adhering to the Open-Closed Principle.
"""

from __future__ import annotations

import copy
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from .constants import DEFAULT_TEMPLATE_PATH


@dataclass
class CharacterPSDConfig:
    """Configuration for a PSD-based YMM4 character."""
    name: str
    psd_path: Path
    base_layers: List[str]
    base_paths: List[str]
    mouth_open_layer: str
    mouth_open_path: str
    mouth_closed_layer: str
    mouth_closed_path: str
    face_layer: int = 10
    tachie_layer: int = 4
    font_color: str = "#FF18181B"
    style_color: str = "#FF000000"
    style_id: int = 2
    layout_with_broll: Dict[str, float] = field(
        default_factory=lambda: {"x": 650.0, "y": 300.0, "zoom": 48.0}
    )
    layout_without_broll: Dict[str, float] = field(
        default_factory=lambda: {"x": -550.0, "y": 300.0, "zoom": 62.0}
    )
    emotion_rules: Dict[str, Tuple[List[str], List[str]]] = field(
        default_factory=dict
    )


class CharacterPSDRegistry:
    """
    Registry for managing PSD tachie assets, layer sets, emotions, and spatial layouts.
    """

    DEFAULT_ZUNDA_REL = Path("ずんだもん立ち絵素材V3.2") / "坂本アヒル_ずんだもん立ち絵V3.2_全部入り版.psd.psd"
    DEFAULT_METAN_REL = Path("四国めたん立ち絵素材2.1") / "四国めたん立ち絵素材2.1.psd"

    # Base layers & paths for Zundamon
    ZUNDA_BASE_LAYERS = [
        "n153", "n89", "n88", "n83", "n97", "n95", "n148", "n140", "n115",
        "n21", "n15", "n12", "n4", "n1", "n0", "n147", "n139", "n109"
    ]
    ZUNDA_BASE_PATHS = [
        "\x1c*頭_正面向き\x1d0",
        "\x1c*頭_正面向き\x1d0\x1c!枝豆\x1d0",
        "\x1c*頭_正面向き\x1d0\x1c!枝豆\x1d0\x1c*枝豆通常\x1d0",
        "\x1c*頭_正面向き\x1d0\x1c!頭\x1d0",
        "\x1c*頭_正面向き\x1d0\x1c!顔色\x1d0",
        "\x1c*頭_正面向き\x1d0\x1c!顔色\x1d0\x1c*ほっぺ基本\x1d0",
        "\x1c*頭_正面向き\x1d0\x1c!眉\x1d0",
        "\x1c*頭_正面向き\x1d0\x1c!目\x1d0",
        "\x1c*頭_正面向き\x1d0\x1c!口\x1d0",
        "\x1c!左腕\x1d0",
        "\x1c!左腕\x1d0\x1c*腰\x1d0",
        "\x1c!右腕\x1d0",
        "\x1c!右腕\x1d0\x1c*腰\x1d0",
        "\x1c!体\x1d0",
        "\x1c尻尾のような何か\x1d0",
        "\x1c*頭_正面向き\x1d0\x1c!眉\x1d0\x1c*基本眉\x1d0",
        "\x1c*頭_正面向き\x1d0\x1c!目\x1d0\x1c*基本目\x1d0",
        "\x1c*頭_正面向き\x1d0\x1c!口\x1d0\x1c*ほほえみ\x1d0",
    ]

    # Base layers & paths for Metan
    METAN_BASE_LAYERS = [
        "n1", "n2", "n26", "n11", "n17", "n16", "n25", "n24", "n34", "n33",
        "n79", "n70", "n49", "n86", "n85", "n82", "n84", "n78", "n69", "n60",
        "n68", "n67", "n47"
    ]
    METAN_BASE_PATHS = [
        "\x1cツインドリル右\x1d0",
        "\x1cツインドリル左\x1d0",
        "\x1c*白ロリ服\x1d0",
        "\x1c*白ロリ服\x1d0\x1c!体\x1d0",
        "\x1c*白ロリ服\x1d0\x1c!右腕\x1d0",
        "\x1c*白ロリ服\x1d0\x1c!右腕\x1d0\x1c*普通\x1d0",
        "\x1c*白ロリ服\x1d0\x1c!左腕\x1d0",
        "\x1c*白ロリ服\x1d0\x1c!左腕\x1d0\x1c*普通\x1d0",
        "\x1c!顔色\x1d0",
        "\x1c!顔色\x1d0\x1c*普通\x1d0",
        "\x1c!眉\x1d0",
        "\x1c!目\x1d0",
        "\x1c!口\x1d0",
        "\x1c!前髪もみあげ\x1d0",
        "\x1c頭部アクセサリ\x1d0",
        "\x1c頭部アクセサリ\x1d0\x1c髪留めハート\x1d0",
        "\x1c頭部アクセサリ\x1d0\x1cヘッドドレス\x1d0",
        "\x1c!眉\x1d0\x1c*ごきげん\x1d0",
        "\x1c!目\x1d0\x1c*目セット\x1d0",
        "\x1c!目\x1d0\x1c*目セット\x1d0\x1c*普通白目\x1d0",
        "\x1c!目\x1d0\x1c*目セット\x1d0\x1c!黒目\x1d0",
        "\x1c!目\x1d0\x1c*目セット\x1d0\x1c!黒目\x1d0\x1c*普通目\x1d0",
        "\x1c!口\x1d0\x1c*ほほえみ\x1d0",
    ]

    _instance: Optional[CharacterPSDRegistry] = None

    def __init__(self) -> None:
        self._custom_characters: Dict[str, CharacterPSDConfig] = {}

    @classmethod
    def get_default(cls) -> CharacterPSDRegistry:
        """Returns singleton default registry instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def resolve_psd_path(cls, character: str) -> Path:
        """
        Encapsulate character PSD path resolution using environment variable overrides
        (VERAXI_ZUNDA_PSD, VERAXI_METAN_PSD, VERAXI_PSD_DIR) and Path.home() / 'Pictures'.
        """
        char_lower = character.lower()
        is_zunda = "ずんだ" in char_lower or "zunda" in char_lower
        is_metan = "めたん" in char_lower or "metan" in char_lower

        # 1. Direct character-specific environment variable overrides
        if is_zunda:
            env_override = os.environ.get("VERAXI_ZUNDA_PSD") or os.environ.get("ZUNDAMON_PSD_PATH")
            if env_override:
                return Path(env_override).resolve()
            rel_subpath = cls.DEFAULT_ZUNDA_REL
        elif is_metan:
            env_override = os.environ.get("VERAXI_METAN_PSD")
            if env_override:
                return Path(env_override).resolve()
            rel_subpath = cls.DEFAULT_METAN_REL
        else:
            rel_subpath = Path(character)

        # 2. Base PSD directory override (VERAXI_PSD_DIR)
        psd_dir = os.environ.get("VERAXI_PSD_DIR")
        if psd_dir:
            cand = Path(psd_dir) / rel_subpath
            if cand.exists():
                return cand.resolve()
            # Try just the filename inside psd_dir
            cand_file = Path(psd_dir) / rel_subpath.name
            if cand_file.exists():
                return cand_file.resolve()

        # 3. User Pictures directory
        user_pic = Path.home() / "Pictures" / rel_subpath
        if user_pic.exists():
            return user_pic.resolve()

        # Default fallback to user_pic even if file doesn't currently exist (clean path)
        return user_pic

    def register_character(self, config: CharacterPSDConfig) -> None:
        """Registers a custom character configuration dynamically."""
        self._custom_characters[config.name] = config

    def get_psd_path(self, character: str) -> Path:
        """Gets resolved PSD path for character name."""
        if character in self._custom_characters:
            return self._custom_characters[character].psd_path
        return self.resolve_psd_path(character)

    def get_base_layers(self, character: str) -> List[str]:
        """Gets base PSD layers for character."""
        if character in self._custom_characters:
            return list(self._custom_characters[character].base_layers)
        char_lower = character.lower()
        if "ずんだ" in char_lower or "zunda" in char_lower:
            return list(self.ZUNDA_BASE_LAYERS)
        return list(self.METAN_BASE_LAYERS)

    def get_base_paths(self, character: str) -> List[str]:
        """Gets base PSD layer paths for character."""
        if character in self._custom_characters:
            return list(self._custom_characters[character].base_paths)
        char_lower = character.lower()
        if "ずんだ" in char_lower or "zunda" in char_lower:
            return list(self.ZUNDA_BASE_PATHS)
        return list(self.METAN_BASE_PATHS)

    @classmethod
    def get_mouth_layers(cls, character_or_path: str) -> Set[str]:
        """
        Gets registered mouth animation layer IDs ('n...') for a given character or PSD path.
        Can be called statically or on an instance.
        """
        if not character_or_path:
            return set()
        s = character_or_path.lower()
        if "ずんだ" in s or "zunda" in s:
            return {"n108", "n109"}
        elif "めたん" in s or "metan" in s:
            return {"n47", "n48"}
        return set()

    def get_face_layers_and_paths(
        self,
        character: str,
        emotion: str,
        vowel: str = "silent",
        is_open: Optional[bool] = None,
    ) -> Tuple[List[str], List[str]]:
        """
        Computes the complete layer IDs and paths for a facial expression and mouth state.
        """
        if is_open is not None:
            vowel = "a" if is_open else "silent"
        vowel = (vowel or "silent").lower()
        is_mouth_open = is_open if is_open is not None else (vowel != "silent")

        if character in self._custom_characters:
            cfg = self._custom_characters[character]
            layers = list(cfg.base_layers)
            paths = list(cfg.base_paths)
            if emotion in cfg.emotion_rules:
                emo_layers, emo_paths = cfg.emotion_rules[emotion]
                layers.extend(emo_layers)
                paths.extend(emo_paths)
            if is_mouth_open:
                layers.append(cfg.mouth_open_layer)
                paths.append(cfg.mouth_open_path)
            else:
                layers.append(cfg.mouth_closed_layer)
                paths.append(cfg.mouth_closed_path)
            return layers, paths

        char_lower = character.lower()
        if "ずんだ" in char_lower or "zunda" in char_lower:
            layers = [
                "n153", "n89", "n88", "n83", "n97", "n95", "n148", "n140", "n115",
                "n21", "n15", "n12", "n4", "n1", "n0"
            ]
            paths = [
                "\x1c*頭_正面向き\x1d0",
                "\x1c*頭_正面向き\x1d0\x1c!枝豆\x1d0",
                "\x1c*頭_正面向き\x1d0\x1c!枝豆\x1d0\x1c*枝豆通常\x1d0",
                "\x1c*頭_正面向き\x1d0\x1c!頭\x1d0",
                "\x1c*頭_正面向き\x1d0\x1c!顔色\x1d0",
                "\x1c*頭_正面向き\x1d0\x1c!顔色\x1d0\x1c*ほっぺ基本\x1d0",
                "\x1c*頭_正面向き\x1d0\x1c!眉\x1d0",
                "\x1c*頭_正面向き\x1d0\x1c!目\x1d0",
                "\x1c*頭_正面向き\x1d0\x1c!口\x1d0",
                "\x1c!左腕\x1d0",
                "\x1c!左腕\x1d0\x1c*腰\x1d0",
                "\x1c!右腕\x1d0",
                "\x1c!右腕\x1d0\x1c*腰\x1d0",
                "\x1c!体\x1d0",
                "\x1c尻尾のような何か\x1d0",
            ]
            if emotion == "surprised":
                layers.extend(["n145", "n132"])
                paths.extend([
                    "\x1c*頭_正面向き\x1d0\x1c!眉\x1d0\x1c*上がり眉\x1d0",
                    "\x1c*頭_正面向き\x1d0\x1c!目\x1d0\x1c*基本目2\x1d0",
                ])
            elif emotion == "angry":
                layers.extend(["n144", "n139"])
                paths.extend([
                    "\x1c*頭_正面向き\x1d0\x1c!眉\x1d0\x1c*怒り眉\x1d0",
                    "\x1c*頭_正面向き\x1d0\x1c!目\x1d0\x1c*基本目\x1d0",
                ])
            elif emotion == "sad":
                layers.extend(["n142", "n139"])
                paths.extend([
                    "\x1c*頭_正面向き\x1d0\x1c!眉\x1d0\x1c*困り眉\x1d0",
                    "\x1c*頭_正面向き\x1d0\x1c!目\x1d0\x1c*基本目\x1d0",
                ])
            elif emotion == "happy":
                layers.extend(["n147", "n121"])
                paths.extend([
                    "\x1c*頭_正面向き\x1d0\x1c!眉\x1d0\x1c*基本眉\x1d0",
                    "\x1c*頭_正面向き\x1d0\x1c!目\x1d0\x1c*にっこり\x1d0",
                ])
            else:  # normal
                layers.extend(["n147", "n139"])
                paths.extend([
                    "\x1c*頭_正面向き\x1d0\x1c!眉\x1d0\x1c*基本眉\x1d0",
                    "\x1c*頭_正面向き\x1d0\x1c!目\x1d0\x1c*基本目\x1d0",
                ])

            if is_mouth_open:
                layers.append("n108")
                paths.append("\x1c*頭_正面向き\x1d0\x1c!口\x1d0\x1c*あは\x1d0")
            else:
                layers.append("n109")
                paths.append("\x1c*頭_正面向き\x1d0\x1c!口\x1d0\x1c*ほほえみ\x1d0")
            return layers, paths
        else:
            # 四国めたん
            layers = [
                "n1", "n2", "n26", "n11", "n17", "n16", "n25", "n24", "n34", "n33",
                "n79", "n70", "n49", "n86", "n85", "n82", "n84"
            ]
            paths = [
                "\x1cツインドリル右\x1d0",
                "\x1cツインドリル左\x1d0",
                "\x1c*白ロリ服\x1d0",
                "\x1c*白ロリ服\x1d0\x1c!体\x1d0",
                "\x1c*白ロリ服\x1d0\x1c!右腕\x1d0",
                "\x1c*白ロリ服\x1d0\x1c!右腕\x1d0\x1c*普通\x1d0",
                "\x1c*白ロリ服\x1d0\x1c!左腕\x1d0",
                "\x1c*白ロリ服\x1d0\x1c!左腕\x1d0\x1c*普通\x1d0",
                "\x1c!顔色\x1d0",
                "\x1c!顔色\x1d0\x1c*普通\x1d0",
                "\x1c!眉\x1d0",
                "\x1c!目\x1d0",
                "\x1c!口\x1d0",
                "\x1c!前髪もみあげ\x1d0",
                "\x1c頭部アクセサリ\x1d0",
                "\x1c頭部アクセサリ\x1d0\x1c髪留めハート\x1d0",
                "\x1c頭部アクセサリ\x1d0\x1cヘッドドレス\x1d0",
            ]
            if emotion == "surprised":
                layers.extend(["n78", "n69", "n59", "n68", "n67"])
                paths.extend([
                    "\x1c!眉\x1d0\x1c*ごきげん\x1d0",
                    "\x1c!目\x1d0\x1c*目セット\x1d0",
                    "\x1c!目\x1d0\x1c*目セット\x1d0\x1c*見開き白目\x1d0",
                    "\x1c!目\x1d0\x1c*目セット\x1d0\x1c!黒目\x1d0",
                    "\x1c!目\x1d0\x1c*目セット\x1d0\x1c!黒目\x1d0\x1c*普通目\x1d0",
                ])
            elif emotion == "angry":
                layers.extend(["n76", "n69", "n60", "n68", "n67"])
                paths.extend([
                    "\x1c!眉\x1d0\x1c*おこ\x1d0",
                    "\x1c!目\x1d0\x1c*目セット\x1d0",
                    "\x1c!目\x1d0\x1c*目セット\x1d0\x1c*普通白目\x1d0",
                    "\x1c!目\x1d0\x1c*目セット\x1d0\x1c!黒目\x1d0",
                    "\x1c!目\x1d0\x1c*目セット\x1d0\x1c!黒目\x1d0\x1c*普通目\x1d0",
                ])
            elif emotion == "sad":
                layers.extend(["n75", "n69", "n60", "n68", "n67"])
                paths.extend([
                    "\x1c!眉\x1d0\x1c*こまり\x1d0",
                    "\x1c!目\x1d0\x1c*目セット\x1d0",
                    "\x1c!目\x1d0\x1c*目セット\x1d0\x1c*普通白目\x1d0",
                    "\x1c!目\x1d0\x1c*目セット\x1d0\x1c!黒目\x1d0",
                    "\x1c!目\x1d0\x1c*目セット\x1d0\x1c!黒目\x1d0\x1c*普通目\x1d0",
                ])
            else:  # happy or normal
                layers.extend(["n78", "n69", "n60", "n68", "n67"])
                paths.extend([
                    "\x1c!眉\x1d0\x1c*ごきげん\x1d0",
                    "\x1c!目\x1d0\x1c*目セット\x1d0",
                    "\x1c!目\x1d0\x1c*目セット\x1d0\x1c*普通白目\x1d0",
                    "\x1c!目\x1d0\x1c*目セット\x1d0\x1c!黒目\x1d0",
                    "\x1c!目\x1d0\x1c*目セット\x1d0\x1c!黒目\x1d0\x1c*普通目\x1d0",
                ])

            if is_mouth_open:
                layers.append("n48")
                paths.append("\x1c!口\x1d0\x1c*わあー\x1d0")
            else:
                layers.append("n47")
                paths.append("\x1c!口\x1d0\x1c*ほほえみ\x1d0")
            return layers, paths

    def get_face_layer(self, character: str) -> int:
        """Returns the TachieFaceItem layer (11 for Zundamon, 10 for Metan/others)."""
        if character in self._custom_characters:
            return self._custom_characters[character].face_layer
        return 11 if "ずんだ" in character.lower() else 10

    def get_tachie_layer(self, character: str) -> int:
        """Returns the TachieItem layer (6 for Zundamon, 4 for Metan/others)."""
        if character in self._custom_characters:
            return self._custom_characters[character].tachie_layer
        return 6 if "ずんだ" in character.lower() else 4

    def get_style_id(self, character: str) -> int:
        """Returns default VOICEVOX style ID."""
        if character in self._custom_characters:
            return self._custom_characters[character].style_id
        return 3 if "ずんだ" in character.lower() else 2

    def get_style_color(self, character: str) -> str:
        """Returns subtitle outline style color."""
        if character in self._custom_characters:
            return self._custom_characters[character].style_color
        return "#FF006400" if "ずんだ" in character.lower() else "#FF8B008B"

    def get_font_color(self, character: str) -> str:
        """Returns subtitle font color."""
        if character in self._custom_characters:
            return self._custom_characters[character].font_color
        return "#FF18181B"

    def get_spatial_layout(self, character: str, has_broll: bool) -> Dict[str, Any]:
        """
        Returns spatial layout parameters (x, y, zoom, layer) for TachieItem,
        accounting for B-roll side-by-side positioning vs standard stage layout.
        """
        if character in self._custom_characters:
            cfg = self._custom_characters[character]
            preset = cfg.layout_with_broll if has_broll else cfg.layout_without_broll
            return {
                "x": preset["x"],
                "y": preset["y"],
                "zoom": preset["zoom"],
                "layer": cfg.tachie_layer,
            }

        is_zunda = "ずんだ" in character.lower()
        if has_broll:
            return {
                "x": 650.0,
                "y": 220.0 if is_zunda else 300.0,
                "zoom": 55.0 if is_zunda else 48.0,
                "layer": 6 if is_zunda else 4,
            }
        else:
            return {
                "x": 550.0 if is_zunda else -550.0,
                "y": 220.0 if is_zunda else 300.0,
                "zoom": 70.0 if is_zunda else 62.0,
                "layer": 6 if is_zunda else 4,
            }

    def create_character_definition(
        self,
        name: str,
        proto: Optional[Dict[str, Any]] = None,
        template_path: Optional[Path] = None,
    ) -> Dict[str, Any]:
        """
        Creates a complete YMM4 Character definition preserving all required plugin properties.
        """
        if proto is None:
            tmpl_p = template_path or Path(DEFAULT_TEMPLATE_PATH)
            if tmpl_p.exists():
                try:
                    with open(tmpl_p, "r", encoding="utf-8-sig") as tf:
                        t_data = json.load(tf)
                        if t_data.get("Characters"):
                            proto = t_data["Characters"][0]
                except Exception:
                    pass

        psd_path = self.get_psd_path(name)
        b_layers = self.get_base_layers(name)
        b_paths = self.get_base_paths(name)
        f_color = self.get_font_color(name)
        s_color = self.get_style_color(name)

        c = copy.deepcopy(proto) if proto else {}
        c["$type"] = "YukkuriMovieMaker.Project.Character, YukkuriMovieMaker"
        c["Name"] = name
        c["TachieType"] = "YukkuriMovieMaker.Plugin.Tachie.Psd.PsdTachiePlugin, YukkuriMovieMaker.Plugin.Tachie.Psd, Version=1.0.0.0, Culture=neutral, PublicKeyToken=null"
        c["TachieCharacterParameter"] = {
            "$type": "YukkuriMovieMaker.Plugin.Tachie.Psd.PsdTachieCharacterParameter, YukkuriMovieMaker.Plugin.Tachie.Psd",
            "FilePath": str(psd_path),
            "MouthSensitivity": 200.0,
            "EyeSensitivity": 100.0,
        }
        c["TachieDefaultItemParameter"] = {
            "$type": "YukkuriMovieMaker.Plugin.Tachie.Psd.PsdTachieItemParameter, YukkuriMovieMaker.Plugin.Tachie.Psd",
            "FilePath": None,
            "EnableLayers": [],
            "EnableLayerPaths": [],
            "IsHiddenWhenNoSpeech": False,
        }
        c["TachieDefaultFaceParameter"] = {
            "$type": "YukkuriMovieMaker.Plugin.Tachie.Psd.PsdTachieFaceParameter, YukkuriMovieMaker.Plugin.Tachie.Psd",
            "IsEnabled": True,
            "FilePath": str(psd_path),
            "EnableLayers": b_layers,
            "EnableLayerPaths": b_paths,
            "EyeAnimation": "Default",
            "MouthAnimation": "VolumeLipSyncPriority",
        }
        c["Font"] = "メイリオ"
        c["FontSize"] = {"Values": [{"Value": 44.0}], "Span": 0.0, "AnimationType": "なし"}
        c["FontColor"] = f_color
        c["StyleColor"] = s_color
        c["BasePoint"] = "CenterCenter"
        c["X"] = {"Values": [{"Value": 0.0}], "Span": 0.0, "AnimationType": "なし"}
        c["Y"] = {"Values": [{"Value": 418.0}], "Span": 0.0, "AnimationType": "なし"}
        c["Bold"] = True
        c["IsJimakuVisible"] = True
        c["WordWrap"] = "NoWrap"
        c["MaxWidth"] = {"Values": [{"Value": 1600.0}], "Span": 0.0, "AnimationType": "なし"}
        return c
