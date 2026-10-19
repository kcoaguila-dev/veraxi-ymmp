"""
YMM4 project compiler for generating dialogue timelines.

Provides the high-level YMMPCompiler facade coordinating:
- Character PSD resolution (CharacterPSDRegistry)
- Intermediate representation construction (TimelineIRBuilder)
- YMM4 project rendering and output generation (YMMPRenderer)
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple, Union

from .cache import TTSCache
from .config import CompilerConfig
from .hatsuon import Hatsuon
from .ir import (
    CharacterClip as CharacterClip,
    DynamicAudioClip as DynamicAudioClip,
    DynamicImageClip as DynamicImageClip,
    GlobalClip as GlobalClip,
    TimelineIR,
    VoiceClip as VoiceClip,
)
from .ir_builder import TimelineIRBuilder
from .psd_registry import CharacterPSDRegistry
from .script import DirectorScriptEntry, WriterScriptEntry
from .template import (
    extract_character_templates,
    extract_face_templates,
    extract_text_template,
    load_template,
)
from .utils import ensure_path
from .voicevox import VoicevoxClient
from .ymmp_renderer import CompilationResult, YMMPRenderer

try:
    from .ports import TTSBackend
except ImportError:
    from .voicevox import TTSBackend

if TYPE_CHECKING:
    pass

# Type alias for script entries
ScriptEntry = Union[WriterScriptEntry, DirectorScriptEntry, Dict[str, Any]]


class CompilerError(Exception):
    """Exception raised when compilation fails."""
    pass


class YMMPCompiler:
    """
    Compiler facade for generating YMM4 .ymmp dialogue timelines.

    Delegates IR generation to TimelineIRBuilder and file emission to YMMPRenderer,
    while preserving backward compatibility for all legacy APIs and protected methods.
    """

    def __init__(
        self,
        template_path: Union[str, Path],
        voicevox_client: Optional[VoicevoxClient] = None,
        speaker_map: Optional[Dict[str, int]] = None,
        default_speaker_id: int = 3,
        hatsuon_converter: Optional[Hatsuon] = None,
        tts_backend: Optional[TTSBackend] = None,
        config: Optional[CompilerConfig] = None,
        psd_registry: Optional[CharacterPSDRegistry] = None,
    ) -> None:
        self.template_path = ensure_path(template_path)
        self.template_data = load_template(str(self.template_path))
        self.character_templates = dict(extract_character_templates(self.template_data))
        self.text_template = extract_text_template(self.template_data)
        self.face_templates = extract_face_templates(self.template_data)
        self.hatsuon = hatsuon_converter or Hatsuon()
        self.tts_backend = tts_backend or voicevox_client
        self.voicevox_client = voicevox_client  # for backward compatibility checks

        # Merge backwards-compatible config
        if config is None:
            self.config = CompilerConfig(
                default_speaker_id=default_speaker_id,
                speaker_map=speaker_map or {},
                use_tts=self.tts_backend is not None,
            )
        else:
            self.config = config

        self.cache = TTSCache(enabled=self.config.use_cache, cache_dir=self.config.cache_dir)
        self.warnings: List[str] = []
        self.errors: List[str] = []
        self.psd_registry = psd_registry or CharacterPSDRegistry.get_default()

        # Layout configuration for legacy tachie positioning
        self.layout_cfg: Dict[str, Any] = {
            "tachie": {"X": -650.0, "Y": 250.0, "Zoom": 65.0},
            "broll": {"X": 350.0, "Y": -50.0, "Zoom": 80.0},
        }

        # Subsystems
        self._ir_builder = TimelineIRBuilder(
            template_data=self.template_data,
            character_templates=self.character_templates,
            face_templates=self.face_templates,
            config=self.config,
            tts_backend=self.tts_backend,
            cache=self.cache,
            hatsuon_converter=self.hatsuon,
            warnings=self.warnings,
            errors=self.errors,
        )
        self._renderer = YMMPRenderer(
            template_data=self.template_data,
            character_templates=self.character_templates,
            text_template=self.text_template,
            face_templates=self.face_templates,
            psd_registry=self.psd_registry,
            layout_cfg=self.layout_cfg,
            warnings=self.warnings,
            errors=self.errors,
        )

    def compile(
        self,
        script: List[ScriptEntry],
        output_path: Union[str, Path],
        use_bom: bool = False,
    ) -> CompilationResult:
        """
        Compiles script into a .ymmp project file at output_path.
        Preserves original template_data without mutation.
        """
        output_path = Path(output_path)
        self.warnings.clear()
        self.errors.clear()
        audio_dir = output_path.parent / "audio"
        if not audio_dir.exists() and (output_path.parent.parent / "audio").exists():
            audio_dir = output_path.parent.parent / "audio"

        timeline_ir, audio_files = self.build_ir(script, audio_dir)
        return self.render_ymmp(
            timeline_ir,
            output_path,
            use_bom=use_bom,
            script_len=len(script),
            audio_files=audio_files,
        )

    def build_ir(
        self,
        script: List[ScriptEntry],
        audio_dir: Path,
    ) -> Tuple[TimelineIR, List[Path]]:
        """Public method to construct TimelineIR and synthesize audio."""
        timeline_ir, audio_files = self._ir_builder.build_ir(script, audio_dir)
        self.character_templates.update(self._ir_builder.character_templates)
        self._renderer.character_templates.update(self._ir_builder.character_templates)
        return timeline_ir, audio_files

    def render_ymmp(
        self,
        timeline_ir: TimelineIR,
        output_path: Path,
        use_bom: bool = False,
        script_len: Optional[int] = None,
        audio_files: Optional[List[Path]] = None,
    ) -> CompilationResult:
        """Public method to render TimelineIR into a .ymmp project file."""
        return self._renderer.render(
            timeline_ir=timeline_ir,
            output_path=output_path,
            use_bom=use_bom,
            script_len=script_len,
            audio_files=audio_files,
        )

    # -------------------------------------------------------------------------
    # Backward-compatible protected delegates
    # -------------------------------------------------------------------------

    def _build_ir(
        self,
        script: List[ScriptEntry],
        audio_dir: Path,
    ) -> Tuple[TimelineIR, List[Path]]:
        return self.build_ir(script, audio_dir)

    def _render_ymmp(
        self,
        timeline_ir: TimelineIR,
        output_path: Path,
        use_bom: bool = False,
        script_len: Optional[int] = None,
        audio_files: Optional[List[Path]] = None,
    ) -> CompilationResult:
        return self.render_ymmp(
            timeline_ir=timeline_ir,
            output_path=output_path,
            use_bom=use_bom,
            script_len=script_len,
            audio_files=audio_files,
        )

    def _render_psd_ymmp(
        self,
        timeline_ir: TimelineIR,
        output_path: Path,
        use_bom: bool,
        script_len: int,
        audio_files: List[Path],
        output_data: Dict[str, Any],
    ) -> CompilationResult:
        return self._renderer.render_psd(
            timeline_ir=timeline_ir,
            output_path=output_path,
            use_bom=use_bom,
            script_len=script_len,
            audio_files=audio_files,
            output_data=output_data,
        )

    def _get_fps(self) -> int:
        return self._ir_builder.get_fps()

    def _convert_hatsuon(self, text: str) -> str:
        return self._ir_builder.convert_hatsuon(text)

    def _synthesize_audio(
        self,
        idx: int,
        char_name: str,
        text: str,
        audio_dir: Path,
    ) -> Tuple[int, Optional[Path], Optional[Dict[str, Any]]]:
        return self._ir_builder.synthesize_audio(idx, char_name, text, audio_dir)

    def _calculate_placeholder_length(self, text: str) -> int:
        return self._ir_builder.calculate_placeholder_length(text)

    def _mute_voice_item(self, voice_item: Dict[str, Any]) -> None:
        self._renderer._mute_voice_item(voice_item)

    def _make_audio_item(
        self,
        voice_item: Dict[str, Any],
        audio_path: Path,
    ) -> Dict[str, Any]:
        return self._renderer._make_audio_item(voice_item, audio_path)

    def _make_text_item(
        self,
        text: str,
        frame: int,
        length: int,
        line: ScriptEntry,
    ) -> Optional[Dict[str, Any]]:
        return self._renderer._make_text_item(text, frame, length, line)

    def _make_face_item(
        self,
        line: ScriptEntry,
        frame: int,
        length: int,
    ) -> Optional[Dict[str, Any]]:
        return self._renderer._make_face_item(line, frame, length)

    @staticmethod
    def _set_animated_value(item: Dict[str, Any], key: str, value: float) -> None:
        YMMPRenderer._set_animated_value(item, key, value)

    def _get_subtitle_layer(self) -> int:
        return self._renderer._get_subtitle_layer()

    def _add_tachie_items(
        self,
        used_characters: set[str],
        total_length: int,
        character_positions: Dict[str, str],
    ) -> List[Dict[str, Any]]:
        # Synchronize layout_cfg before delegation
        self._renderer.layout_cfg = self.layout_cfg
        return self._renderer._add_tachie_items(
            used_characters, total_length, character_positions
        )

    @staticmethod
    def _write_output(output_data: Dict[str, Any], output_path: Path, use_bom: bool) -> None:
        YMMPRenderer._write_output(output_data, output_path, use_bom)
