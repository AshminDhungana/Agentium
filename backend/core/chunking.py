"""Dependency-free recursive text chunker for RAG knowledge storage.

Splits long text on natural boundaries (paragraph -> line -> sentence -> word ->
char) into overlapping chunks that stay under the embedding window. Short text
passes through unchanged so small documents incur no chunk overhead.
"""
from typing import List

_SEPARATORS = ["\n\n", "\n", ". ", " ", ""]


def chunk_text(text: str, chunk_size: int = 1500, overlap: int = 200) -> List[str]:
    """Split *text* into overlapping chunks no longer than *chunk_size* chars.

    - Returns ``[text]`` unchanged when the text already fits.
    - Returns ``[]`` for empty / whitespace-only input.
    - Recursively splits on paragraph/line/sentence/word boundaries; a token
      longer than ``chunk_size`` is hard-split on the character boundary.
    - Adjacent chunks share up to ``overlap`` trailing chars for context.
    """
    if chunk_size <= overlap:
        raise ValueError("chunk_size must be greater than overlap")
    if text is None or not text.strip():
        return []
    text = text.strip()
    if len(text) <= chunk_size:
        return [text]

    pieces = _recursive_split(text, chunk_size, _SEPARATORS)
    return _merge_with_overlap(pieces, chunk_size, overlap)


def _recursive_split(text: str, chunk_size: int, separators: List[str]) -> List[str]:
    if len(text) <= chunk_size:
        return [text] if text else []
    sep = separators[0]
    rest = separators[1:]
    if sep == "":
        # No separator left: hard-split on character boundary.
        return [text[i:i + chunk_size] for i in range(0, len(text), chunk_size)]
    parts = text.split(sep)
    out: List[str] = []
    for idx, part in enumerate(parts):
        # Re-attach the separator (except after the final part) so we don't lose it.
        piece = part + sep if (sep and idx < len(parts) - 1) else part
        if not piece:
            continue
        if len(piece) <= chunk_size:
            if piece.strip():
                out.append(piece)
        else:
            out.extend(_recursive_split(piece, chunk_size, rest))
    return out


def _merge_with_overlap(pieces: List[str], chunk_size: int, overlap: int) -> List[str]:
    chunks: List[str] = []
    current = ""
    for piece in pieces:
        if not current:
            current = piece
        elif len(current) + len(piece) <= chunk_size:
            current += piece
        else:
            chunks.append(current.strip())
            tail = current[-overlap:] if overlap and len(current) > overlap else ""
            current = tail + piece
            if len(current) > chunk_size:
                # overlap + piece still too big: flush in fixed slices.
                for i in range(0, len(current), chunk_size):
                    seg = current[i:i + chunk_size].strip()
                    if seg:
                        chunks.append(seg)
                current = ""
    if current.strip():
        chunks.append(current.strip())
    return [c for c in chunks if c]
