"""
Async compilation for parallel TTS synthesis.
"""

import asyncio
import copy
from pathlib import Path
from typing import Any, Dict, List

from .compiler import YMMPCompiler, ScriptEntry, CompilationResult
from .logging import logger


class AsyncYMMPCompiler(YMMPCompiler):
    """
    Compiler capable of parallel TTS synthesis.
    """

    async def compile_async(
        self,
        script: List[ScriptEntry],
        output_path: Path,
        use_bom: bool = False
    ) -> CompilationResult:
        """
        Compile script asynchronously to speed up TTS.
        """
        self.warnings = []
        self.errors = []

        logger.info(f"Starting async compilation for {len(script)} items")
        output_data = copy.deepcopy(self.template_data)
        items: List[Dict[str, Any]] = []

        if self.config.use_tts and self.tts_backend:
            # We assume tts_backend has async support, e.g. VoicevoxClient.is_available_async
            # If not, fallback to sync is_available check.
            is_avail = False
            if hasattr(self.tts_backend, 'is_available_async'):
                is_avail = await self.tts_backend.is_available_async()
            else:
                is_avail = self.tts_backend.is_available()

            if not is_avail:
                raise RuntimeError("TTS Backend not available")

        # Basic setup
        current_frame = 0
        output_dir = output_path.parent
        audio_dir = output_dir / "audio"
        fps = self._get_fps()

        # Phase 1: Synthesize all required TTS asynchronously
        tts_tasks = []

        for idx, line in enumerate(script):
            char_name = line.get("character")
            text = line.get("text")

            if not char_name or not text:
                raise ValueError(f"Invalid script entry at index {idx}: missing character or text")

            if self.config.use_tts and self.tts_backend:
                speaker_id = self.config.speaker_map.get(char_name, self.config.default_speaker_id)
                # create async task for TTS if backend supports it, else run in thread
                if hasattr(self.tts_backend, 'synthesize_async'):
                    task = asyncio.create_task(self.tts_backend.synthesize_async(text, speaker_id))
                    tts_tasks.append((idx, char_name, text, task))

        if tts_tasks:
            logger.info(f"Awaiting {len(tts_tasks)} async TTS tasks...")
            results = await asyncio.gather(*(t for _, _, _, t in tts_tasks), return_exceptions=True)

            # Store successful results in cache so synchronous loop hits cache
            for (idx, char_name, text, _), result in zip(tts_tasks, results):
                if isinstance(result, Exception):
                    logger.error(f"Async synthesis failed for {char_name}: {result}")
                    self.errors.append(f"Async synthesis failed for {char_name}: {result}")
                else:
                    wav_bytes, duration = result
                    speaker_id = self.config.speaker_map.get(char_name, self.config.default_speaker_id)
                    self.cache.set(text, speaker_id, wav_bytes, duration)

        # Re-run synthesis loop now that results are likely cached or finished
        audio_files = []
        for idx, line in enumerate(script):
            char_name = line.get("character", "")
            text = line.get("text", "")

            # Validate director metadata if present and emit warnings
            if "emotion" in line and line["emotion"] != "neutral":
                msg = f"Emotion '{line['emotion']}' on entry {idx} is preserved but unsupported in generated YMMP."
                logger.warning(msg)
                self.warnings.append(msg)

            if "motion" in line and line["motion"] != "none":
                msg = f"Motion '{line['motion']}' on entry {idx} is preserved but unsupported in generated YMMP."
                logger.warning(msg)
                self.warnings.append(msg)

            if line.get("bgm") is not None:
                msg = f"BGM '{line['bgm']}' on entry {idx} is preserved but unsupported in generated YMMP."
                logger.warning(msg)
                self.warnings.append(msg)

            if line.get("sfx") is not None:
                msg = f"SFX '{line['sfx']}' on entry {idx} is preserved but unsupported in generated YMMP."
                logger.warning(msg)
                self.warnings.append(msg)

            if char_name not in self.character_templates:
                raise ValueError(f"Missing template for character: {char_name}")

            template_item = self.character_templates[char_name]["voice"]
            if template_item is None:
                raise ValueError(f"No voice template found for character: {char_name}")

            new_item = copy.deepcopy(template_item)
            new_item["Serif"] = text
            new_item["Hatsuon"] = self._convert_hatsuon(text)
            new_item["Frame"] = current_frame

            audio_path = None
            if self.config.use_tts and self.tts_backend:
                # We can call the sync _synthesize_audio, because the cache should be populated
                # (or backend might be very fast since it's already done in task)
                # Wait! We need to make sure _synthesize_audio returns properly if it was awaited.
                # Actually, our cache will handle the fast retrieval.
                try:
                    length, audio_path = self._synthesize_audio(idx, char_name, text, audio_dir)
                    if audio_path:
                        audio_files.append(audio_path)
                except Exception as e:
                    raise RuntimeError(f"Synthesis failed for '{char_name}' on line '{text}': {e}")
            else:
                length = self._calculate_placeholder_length(text)

            new_item["Length"] = length
            new_item["VoiceCache"] = ""
            items.append(new_item)
            current_frame += length

        total_length = current_frame
        used_characters = set(line["character"] for line in script if "character" in line)
        tachie_items = self._add_tachie_items(used_characters, total_length)
        items.extend(tachie_items)

        output_data["Timeline"]["Items"] = items
        output_data["Timeline"]["Length"] = total_length

        self._write_output(output_data, output_path, use_bom)

        voice_items = len(script)
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
