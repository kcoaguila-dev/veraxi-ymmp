"""
Async compilation for parallel TTS synthesis.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import List, Optional, Union

from .compiler import CompilationResult, CompilerError, ScriptEntry, YMMPCompiler
from .validation import sanitize_filename


class AsyncYMMPCompiler(YMMPCompiler):
    """
    Compiler capable of parallel TTS synthesis.
    """

    async def synthesize_all_async(
        self,
        script: List[ScriptEntry],
        audio_dir: Optional[Path] = None,
    ) -> None:
        """Synthesize all script entries asynchronously in parallel."""
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
                    if len(result) == 3:
                        wav_bytes, duration, audio_query = result
                    else:
                        wav_bytes, duration = result
                        audio_query = None
                    speaker_id = self.config.speaker_map.get(char_name, self.config.default_speaker_id)
                    self.cache.set(text, speaker_id, wav_bytes, duration)
                    if isinstance(audio_query, dict) and audio_query and audio_dir is not None:
                        audio_dir.mkdir(parents=True, exist_ok=True)
                        safe_char_name = sanitize_filename(str(char_name))
                        out_path = audio_dir / f"{idx:03d}_{safe_char_name}.wav"
                        out_path.with_suffix(".query.json").write_text(
                            json.dumps(audio_query, ensure_ascii=False),
                            encoding="utf-8",
                        )

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
        await self.synthesize_all_async(script, audio_dir)
        if self.errors and getattr(self.config, "strict_tts", False):
            raise CompilerError("Compilation failed due to TTS errors:\n" + "\n".join(self.errors))

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
