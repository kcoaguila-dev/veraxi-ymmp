"""
Protocol for Director script generation.
"""

from typing import List, Protocol
from .script import WriterScriptEntry, DirectorScriptEntry

class DirectorProvider(Protocol):
    """
    Interface for providers that can convert a writer script into a director script.
    """

    def generate_director_script(self, writer_script: List[WriterScriptEntry]) -> List[DirectorScriptEntry]:
        """
        Generates a director script with added metadata (emotion, motion, bgm, sfx)
        while strictly preserving the character and text of the input writer script.
        """
        ...
