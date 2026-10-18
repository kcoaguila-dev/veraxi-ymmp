"""
Async compilation for parallel TTS synthesis.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import List, Union

from .compiler import CompilationResult, ScriptEntry, YMMPCompiler


class AsyncYMMPCompiler(YMMPCompiler):
    """
    Compiler capable of parallel TTS synthesis.
    """

    async def compile_async(
        self,
        script: List[ScriptEntry],
        output_path: Union[str, Path],
        use_bom: bool = False,
    ) -> CompilationResult:
        """
        Asynchronously synthesizes speech audio in parallel before delegating
        to build_ir and render_ymmp.
        """
        output_path = Path(output_path)
        self.warnings.clear()
        self.errors.clear()

        audio_dir = output_path.parent / "audio"
        if not audio_dir.exists() and (output_path.parent.parent / "audio").exists():
            audio_dir = output_path.parent.parent / "audio"

        # Phase 1: Async TTS synthesis in parallel
        tts_tasks = []
        for idx, line in enumerate(script):
            char_name = line.get("character")
            text = line.get("text")
            if not char_name or not text:
                continue
            if self.config.use_tts and self.tts_backend:
                speaker_id = self.config.speaker_map.get(char_name, self.config.default_speaker_id)
                if hasattr(self.tts_backend, "synthesize_async"):
                    task = asyncio.create_task(self.tts_backend.synthesize_async(text, speaker_id))
                    tts_tasks.append((idx, char_name, text, task))

        if tts_tasks:
            results = await asyncio.gather(*(t for _, _, _, t in tts_tasks), return_exceptions=True)
            for (idx, char_name, text, _), result in zip(tts_tasks, results):
                if isinstance(result, BaseException):
                    self.errors.append(f"Async synthesis failed for {char_name}: {result}")
                else:
                    wav_bytes, duration = result
                    speaker_id = self.config.speaker_map.get(char_name, self.config.default_speaker_id)
                    self.cache.set(text, speaker_id, wav_bytes, duration)

        # Phase 2: Build IR
        timeline_ir, audio_files = self.build_ir(script, audio_dir)

        # Phase 3: Render to YMMP
        return self.render_ymmp(
            timeline_ir,
            output_path,
            use_bom=use_bom,
            script_len=len(script),
            audio_files=audio_files,
        )
