"""
veraxi-ymmp: A Python tool for generating YMM4 .ymmp dialogue timelines.

3-Tier Compiler Architecture:
    - veraxi_ymmp.core: Pure AST, TimelineIR, Script, Staging, Ports & Primitives
    - veraxi_ymmp.epistemic: Fact-Checking, Pint Units, MeCab NLP, PDF/iXBRL/Web Source Grounding
    - veraxi_ymmp.editorial: Pre-Production, BudouX Ingestion, Pacing & 50/30/20 Retention Linting
    - veraxi_ymmp.graphics: Pro Dark Slate B-Roll, Infographics, 3-Split Thumbnails, PSD & Typography
    - veraxi_ymmp.audio: VoiceVox TTS, Hatsuon Pitch Accent, Phonetics, EBU R128 (-16 LUFS) & SFX
    - veraxi_ymmp.exporters: Hexagonal Targets: YMM4 (.ymmp), Premiere (.xml), MoviePy (.mp4), AE, SRT, YouTube
    - veraxi_ymmp.app: Orchestration Pipeline, Compiler, CLI, FastAPI Studio & MCP Server
"""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING, Any, Dict

__version__ = "0.1.0"

# Explicit mapping of top-level public API symbols to their canonical subpackage modules
_EXPORT_MAP: Dict[str, str] = {
    # Subpackages
    "core": "veraxi_ymmp.core",
    "epistemic": "veraxi_ymmp.epistemic",
    "editorial": "veraxi_ymmp.editorial",
    "graphics": "veraxi_ymmp.graphics",
    "audio": "veraxi_ymmp.audio",
    "exporters": "veraxi_ymmp.exporters",
    "app": "veraxi_ymmp.app",
    # App orchestration
    "YMMPCompiler": "veraxi_ymmp.app.compiler",
    "CompilerError": "veraxi_ymmp.app.compiler",
    "TimelineIRBuilder": "veraxi_ymmp.app.ir_builder",
    "ProjectPipeline": "veraxi_ymmp.app.pipeline",
    "PipelineResult": "veraxi_ymmp.app.pipeline",
    # Core domain & contracts
    "load_template": "veraxi_ymmp.core.template",
    "extract_character_templates": "veraxi_ymmp.core.template",
    "CharacterTemplates": "veraxi_ymmp.core.template",
    "TimelineExporter": "veraxi_ymmp.core.ports",
    "ExportResult": "veraxi_ymmp.core.ports",
    # Graphics
    "CharacterPSDRegistry": "veraxi_ymmp.graphics.psd_registry",
    "broll": "veraxi_ymmp.graphics.broll",
    "OfficialSourceCitation": "veraxi_ymmp.graphics.official_assets",
    "OfficialAssetRegistry": "veraxi_ymmp.graphics.official_assets",
    "render_official_image_slide": "veraxi_ymmp.graphics.official_assets",
    "render_official_data_slide": "veraxi_ymmp.graphics.official_assets",
    "ThumbnailConfig": "veraxi_ymmp.graphics.thumbnail",
    "generate_thumbnail": "veraxi_ymmp.graphics.thumbnail",
    "auto_extract_thumbnail_config": "veraxi_ymmp.graphics.thumbnail",
    "generate_project_thumbnail": "veraxi_ymmp.graphics.thumbnail",
    # Audio
    "VoicevoxClient": "veraxi_ymmp.audio.voicevox",
    "VoicevoxError": "veraxi_ymmp.audio.voicevox",
    "Hatsuon": "veraxi_ymmp.audio.hatsuon",
    "HatsuonError": "veraxi_ymmp.audio.hatsuon",
    "normalize_video_audio": "veraxi_ymmp.audio.audio_normalizer",
    # Exporters
    "YMMPRenderer": "veraxi_ymmp.exporters.ymmp_renderer",
    "CompilationResult": "veraxi_ymmp.exporters.ymmp_renderer",
    "PremiereExporter": "veraxi_ymmp.exporters.premiere_exporter",
    "export_to_premiere": "veraxi_ymmp.exporters.premiere_exporter",
    "generate_fcp_xml": "veraxi_ymmp.exporters.premiere_exporter",
    "generate_srt": "veraxi_ymmp.exporters.srt_generator",
    "SRTExporter": "veraxi_ymmp.exporters.srt_generator",
}

__all__ = list(_EXPORT_MAP.keys())


def __getattr__(name: str) -> Any:
    """PEP 562 lazy attribute loader: only loads subpackages when requested."""
    if name in _EXPORT_MAP:
        mod_name = _EXPORT_MAP[name]
        mod = importlib.import_module(mod_name)
        if name in ("core", "epistemic", "editorial", "graphics", "audio", "exporters", "app"):
            val = mod
        else:
            val = getattr(mod, name)
        globals()[name] = val
        return val
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return list(globals().keys()) + __all__


if TYPE_CHECKING:
    from . import app as app
    from . import audio as audio
    from . import core as core
    from . import editorial as editorial
    from . import epistemic as epistemic
    from . import exporters as exporters
    from . import graphics as graphics
    from .app.compiler import CompilerError as CompilerError, YMMPCompiler as YMMPCompiler
    from .app.ir_builder import TimelineIRBuilder as TimelineIRBuilder
    from .app.pipeline import PipelineResult as PipelineResult, ProjectPipeline as ProjectPipeline
    from .audio.audio_normalizer import normalize_video_audio as normalize_video_audio
    from .audio.hatsuon import Hatsuon as Hatsuon, HatsuonError as HatsuonError
    from .audio.voicevox import VoicevoxClient as VoicevoxClient, VoicevoxError as VoicevoxError
    from .core.ports import ExportResult as ExportResult, TimelineExporter as TimelineExporter
    from .core.template import (
        CharacterTemplates as CharacterTemplates,
        extract_character_templates as extract_character_templates,
        load_template as load_template,
    )
    from .exporters.premiere_exporter import (
        PremiereExporter as PremiereExporter,
        export_to_premiere as export_to_premiere,
        generate_fcp_xml as generate_fcp_xml,
    )
    from .exporters.srt_generator import SRTExporter as SRTExporter, generate_srt as generate_srt
    from .exporters.ymmp_renderer import (
        CompilationResult as CompilationResult,
        YMMPRenderer as YMMPRenderer,
    )
    from .graphics import broll as broll
    from .graphics.official_assets import (
        OfficialAssetRegistry as OfficialAssetRegistry,
        OfficialSourceCitation as OfficialSourceCitation,
        render_official_data_slide as render_official_data_slide,
        render_official_image_slide as render_official_image_slide,
    )
    from .graphics.psd_registry import CharacterPSDRegistry as CharacterPSDRegistry
    from .graphics.thumbnail import (
        ThumbnailConfig as ThumbnailConfig,
        auto_extract_thumbnail_config as auto_extract_thumbnail_config,
        generate_project_thumbnail as generate_project_thumbnail,
        generate_thumbnail as generate_thumbnail,
    )
