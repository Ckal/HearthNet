from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Chunk:
    text: str
    metadata: dict  # {doc_cid, doc_title, page, chunk_index, language}


def chunk_text(
    text: str,
    *,
    chunk_size: int = 512,
    overlap: int = 64,
    metadata: dict | None = None,
) -> list[Chunk]:
    """Split text using sliding window measured in approximate tokens (chars/4).

    Respects paragraph boundaries (double newline) where possible, else word
    boundaries.
    """
    meta = metadata or {}

    approx_tokens = len(text) // 4
    if approx_tokens <= chunk_size:
        return [Chunk(text=text, metadata=meta)]

    # Split on paragraph boundaries first
    paragraphs = text.split("\n\n")

    chunks: list[Chunk] = []
    current_parts: list[str] = []
    current_tokens = 0

    def flush(parts: list[str]) -> str:
        return "\n\n".join(parts).strip()

    for para in paragraphs:
        para_tokens = len(para) // 4
        if current_tokens + para_tokens > chunk_size and current_parts:
            chunk_text_val = flush(current_parts)
            if chunk_text_val:
                chunks.append(Chunk(text=chunk_text_val, metadata=meta))
            # Carry overlap: keep tail words from current
            overlap_chars = overlap * 4
            tail = (
                chunk_text_val[-overlap_chars:]
                if overlap_chars < len(chunk_text_val)
                else chunk_text_val
            )
            # Find word boundary at start of tail
            space_idx = tail.find(" ")
            if space_idx != -1:
                tail = tail[space_idx + 1 :]
            current_parts = [tail] if tail else []
            current_tokens = len(tail) // 4

        if para_tokens > chunk_size:
            # Para itself too large — split at word boundaries
            words = para.split(" ")
            word_buf: list[str] = []
            word_tokens = 0
            for word in words:
                wt = (len(word) + 1) // 4 or 1
                if word_tokens + wt > chunk_size and word_buf:
                    chunk_text_val = " ".join(word_buf).strip()
                    if chunk_text_val:
                        chunks.append(Chunk(text=chunk_text_val, metadata=meta))
                    # overlap
                    overlap_chars = overlap * 4
                    tail_words = " ".join(word_buf)
                    tail = (
                        tail_words[-overlap_chars:]
                        if overlap_chars < len(tail_words)
                        else tail_words
                    )
                    space_idx = tail.find(" ")
                    if space_idx != -1:
                        tail = tail[space_idx + 1 :]
                    word_buf = tail.split(" ") if tail else []
                    word_tokens = len(tail) // 4
                word_buf.append(word)
                word_tokens += wt
            remaining = " ".join(word_buf).strip()
            if remaining:
                current_parts.append(remaining)
                current_tokens += len(remaining) // 4
        else:
            current_parts.append(para)
            current_tokens += para_tokens

    # Flush remainder
    if current_parts:
        chunk_text_val = flush(current_parts)
        if chunk_text_val:
            chunks.append(Chunk(text=chunk_text_val, metadata=meta))

    return chunks if chunks else [Chunk(text=text, metadata=meta)]


def chunk_pdf(pdf_bytes: bytes, *, doc_metadata: dict) -> list[Chunk]:
    """Extract text per page using pypdf, then chunk_text per page.

    Falls back to treating as plain text if pypdf not installed.
    """
    try:
        import io

        import pypdf  # type: ignore[import-untyped]

        reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
        all_chunks: list[Chunk] = []
        for page_num, page in enumerate(reader.pages):
            page_text = page.extract_text() or ""
            if not page_text.strip():
                continue
            meta = {**doc_metadata, "page": page_num, "language": "unknown"}
            page_chunks = chunk_text(page_text, metadata=meta)
            all_chunks.extend(page_chunks)
        return all_chunks
    except ImportError:
        # Fallback: treat bytes as UTF-8 text
        text = pdf_bytes.decode("utf-8", errors="replace")
        return chunk_text(text, metadata=doc_metadata)
