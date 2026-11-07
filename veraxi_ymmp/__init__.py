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

import sys
import importlib
import importlib.abc
from typing import Any, Sequence

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

_MODULE_MAP = {'constants': 'core', 'logging': 'core', 'utils': 'core', 'config': 'core', 'template': 'core', 'ir': 'core', 'script': 'core', 'staging': 'core', 'ports': 'core', 'director': 'core', 'schema': 'core', 'epistemic_units': 'epistemic', 'facts': 'epistemic', 'fact_audit': 'epistemic', 'fact_report': 'epistemic', 'citation_card': 'epistemic', 'asset_guard': 'epistemic', 'web_capture': 'epistemic', 'edgar_capture': 'epistemic', 'fred_capture': 'epistemic', 'claim_extractor': 'epistemic', 'veraxi_checker': 'epistemic', 'document_registry': 'epistemic', 'script_ingest': 'editorial', 'pacing': 'editorial', 'retention_qa': 'editorial', 'validation': 'editorial', 'official_assets': 'graphics', 'psd_registry': 'graphics', 'typography': 'graphics', 'subtitle_plate': 'graphics', 'stats_formatter': 'graphics', 'broll': 'graphics', 'infographic': 'graphics', 'thumbnail': 'graphics', 'thumbnail_composer': 'graphics', 'thumbnail_ab': 'graphics', 'phonetics': 'audio', 'hatsuon': 'audio', 'voicevox': 'audio', 'audio_normalizer': 'audio', 'sfx': 'audio', 'ymmp_renderer': 'exporters', 'ymmp_utils': 'exporters', 'premiere_exporter': 'exporters', 'moviepy_renderer': 'exporters', 'ae_renderer': 'exporters', 'srt_generator': 'exporters', 'youtube_auth': 'exporters', 'youtube_metadata': 'exporters', 'youtube_adapter': 'exporters', 'compiler': 'app', 'cache': 'app', 'async_compiler': 'app', 'ir_builder': 'app', 'pipeline': 'app', 'history': 'app', 'cli': 'app', 'cli_ideate': 'app', 'cli_capture': 'app', 'cli_youtube': 'app', 'api_server': 'app', 'mcp_server': 'app'}

class _SubpackageAliasLoader(importlib.abc.Loader):
    def __init__(self, target_module_name: str) -> None:
        self.target_module_name = target_module_name

    def create_module(self, spec: Any) -> Any:
        return importlib.import_module(self.target_module_name)

    def exec_module(self, module: Any) -> None:
        pass


class _SubpackageAliasFinder(importlib.abc.MetaPathFinder):
    """MetaPathFinder to alias legacy imports (e.g. from veraxi_ymmp.facts import ...) to subpackages."""
    def find_spec(self, fullname: str, path: Sequence[str] | None, target: Any = None) -> Any:
        if fullname.startswith("veraxi_ymmp."):
            parts = fullname.split(".")
            if len(parts) == 2 and parts[1] in _MODULE_MAP:
                sub = _MODULE_MAP[parts[1]]
                canonical = f"veraxi_ymmp.{sub}.{parts[1]}"
                return importlib.machinery.ModuleSpec(fullname, _SubpackageAliasLoader(canonical))
        return None

if not any(isinstance(f, _SubpackageAliasFinder) for f in sys.meta_path):
    sys.meta_path.insert(0, _SubpackageAliasFinder())

def __getattr__(name: str) -> Any:
    """Dynamically resolve legacy module imports from veraxi_ymmp.<module>."""
    if name in _MODULE_MAP:
        sub = _MODULE_MAP[name]
        mod = importlib.import_module(f"veraxi_ymmp.{sub}.{name}")
        sys.modules[f"veraxi_ymmp.{name}"] = mod
        globals()[name] = mod
        return mod
    raise AttributeError(f"module 'veraxi_ymmp' has no attribute '{name}'")
