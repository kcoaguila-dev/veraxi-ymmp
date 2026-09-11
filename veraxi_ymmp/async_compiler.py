"""
Async compilation for parallel TTS synthesis.
"""

import asyncio
import copy
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, TypedDict
from .ir import TimelineIR, VoiceClip, CharacterClip, GlobalClip

from .compiler import YMMPCompiler, ScriptEntry, CompilationResult
from .logging import logger
from .template import get_timeline


class AsyncYMMPCompiler(YMMPCompiler):
    """
    Compiler capable of parallel TTS synthesis.
    """

    async def compile_async(
        self,
        script: List[ScriptEntry],
        output_path: "Path",
        use_bom: bool = False
    ) -> CompilationResult:
        import copy
        import asyncio
        from .template import get_timeline

        self.warnings.clear()
        self.errors.clear()
        output_data = copy.deepcopy(self.template_data)
        items = []

        from pathlib import Path
        output_path = Path(output_path)
        audio_dir = output_path.parent / "audio"
        
        # Phase 1: Async TTS synthesis
        tts_tasks = []
        for idx, line in enumerate(script):
            char_name = line.get("character")
            text = line.get("text")
            if not char_name or not text:
                continue
            if self.config.use_tts and self.tts_backend:
                speaker_id = self.config.speaker_map.get(char_name, self.config.default_speaker_id)
                if hasattr(self.tts_backend, 'synthesize_async'):
                    task = asyncio.create_task(self.tts_backend.synthesize_async(text, speaker_id))
                    tts_tasks.append((idx, char_name, text, task))

        if tts_tasks:
            results = await asyncio.gather(*(t for _, _, _, t in tts_tasks), return_exceptions=True)
            for (idx, char_name, text, _), result in zip(tts_tasks, results):
                if isinstance(result, Exception):
                    self.errors.append(f"Async synthesis failed for {char_name}: {result}")
                else:
                    wav_bytes, duration = result
                    speaker_id = self.config.speaker_map.get(char_name, self.config.default_speaker_id)
                    self.cache.set(text, speaker_id, wav_bytes, duration)
                    
        # Phase 2: Build IR
        timeline_ir, audio_files = self._build_ir(script, audio_dir)
        
        # Phase 3: Render to YMMP
        return self._render_ymmp(timeline_ir, output_path, use_bom, len(script), audio_files)

        tachie_count = len(tachie_items)
        total_duration = total_length / fps if fps else 0.0

        return CompilationResult(
            output_path=output_path,
            item_count=len(items),
            voice_item_count=voice_items,
            tachie_item_count=tachie_count,
            total_frames=total_length,
            total_duration_seconds=total_duration,
            audio_files=audio_files,
            warnings=self.warnings,
            errors=self.errors
        )
