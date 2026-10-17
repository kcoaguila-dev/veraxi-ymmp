"""
veraxi-ymmp: A Python tool for generating YMM4 .ymmp dialogue timelines.

This package provides tools for creating YMM4 (Yukkuri Movie Maker 4) dialogue
timelines by cloning real template items. It supports both placeholder timing
and real VOICEVOX-backed TTS for accurate frame calculation.

Main Components:
    - YMMPCompiler: Compiles scripts into .ymmp files
    - VoicevoxClient: Interface to VOICEVOX Engine for TTS
    - Hatsuon: Phonetic converter for Japanese text
    - template: Template loading and processing utilities

Example usage:
    >>> from veraxi_ymmp import YMMPCompiler
    >>> compiler = YMMPCompiler("template.ymmp")
    >>> compiler.compile([{"character": "ゆっくり霊夢", "text": "こんにちは"}], "output.ymmp")
"""

from __future__ import annotations

from .compiler import YMMPCompiler, CompilerError
from .psd_registry import CharacterPSDRegistry
from .ir_builder import TimelineIRBuilder
from .ymmp_renderer import YMMPRenderer, CompilationResult
from .voicevox import VoicevoxClient, VoicevoxError
from .hatsuon import Hatsuon, HatsuonError
from .template import load_template, extract_character_templates, CharacterTemplates

try:
    from .premiere_exporter import PremiereExporter, export_to_premiere, generate_fcp_xml
except ImportError:
    pass

try:
    from .srt_generator import generate_srt
except ImportError:
    pass

from . import broll
from .thumbnail import (
    ThumbnailConfig,
    generate_thumbnail,
    auto_extract_thumbnail_config,
    generate_project_thumbnail,
)

__all__ = [
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
    "broll",
    "ThumbnailConfig",
    "generate_thumbnail",
    "auto_extract_thumbnail_config",
    "generate_project_thumbnail",
]

__version__ = "0.1.0"

