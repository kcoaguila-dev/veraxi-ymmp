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



# Subpackages
from . import core
from . import epistemic
from . import editorial
from . import graphics
from . import audio
from . import exporters
from . import app

# Key Public API Exports
from .app.compiler import YMMPCompiler, CompilerError
from .graphics.psd_registry import CharacterPSDRegistry
from .app.ir_builder import TimelineIRBuilder
from .exporters.ymmp_renderer import YMMPRenderer, CompilationResult
from .audio.voicevox import VoicevoxClient, VoicevoxError
from .audio.hatsuon import Hatsuon, HatsuonError
from .core.template import load_template, extract_character_templates, CharacterTemplates

try:
    from .exporters.premiere_exporter import PremiereExporter, export_to_premiere, generate_fcp_xml
except ImportError:
    pass

from .core.ports import ExportResult, TimelineExporter

try:
    from .exporters.srt_generator import generate_srt, SRTExporter
except ImportError:
    pass

from .app.pipeline import PipelineResult, ProjectPipeline
from .audio.audio_normalizer import normalize_video_audio

from .graphics import broll
from .graphics.official_assets import (
    OfficialSourceCitation,
    OfficialAssetRegistry,
    render_official_image_slide,
    render_official_data_slide,
)
from .graphics.thumbnail import (
    ThumbnailConfig,
    generate_thumbnail,
    auto_extract_thumbnail_config,
    generate_project_thumbnail,
)

__all__ = [
    "core",
    "epistemic",
    "editorial",
    "graphics",
    "audio",
    "exporters",
    "app",
    "YMMPCompiler",
    "CompilerError",
    "CompilationResult",
    "CharacterPSDRegistry",
    "TimelineIRBuilder",
    "YMMPRenderer",
    "VoicevoxClient",
    "VoicevoxError",
    "Hatsuon",
    "HatsuonError",
    "load_template",
    "extract_character_templates",
    "CharacterTemplates",
    "PremiereExporter",
    "export_to_premiere",
    "generate_fcp_xml",
    "generate_srt",
    "SRTExporter",
    "TimelineExporter",
    "ExportResult",
    "ProjectPipeline",
    "PipelineResult",
    "normalize_video_audio",
    "broll",
    "ThumbnailConfig",
    "generate_thumbnail",
    "auto_extract_thumbnail_config",
    "generate_project_thumbnail",
    "OfficialSourceCitation",
    "OfficialAssetRegistry",
    "render_official_image_slide",
    "render_official_data_slide",
]

__version__ = "0.1.0"
