"""Document parsing and chunking.

Everything here is pure and side-effect free (aside from reading the source file
in ``parse_document``) so the chunking logic can be unit-tested without a
database, a worker, or an embedding model.

Parsing produces a list of :class:`ParsedBlock` — a span of text tagged with the
location metadata we want to preserve for citations (page number for PDFs,
section heading for Markdown/HTML). Chunking then packs those blocks into
overlapping windows, carrying the metadata through onto each chunk.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ParsedBlock:
    text: str
    page_num: int | None = None
    section: str | None = None


@dataclass(frozen=True)
class ChunkData:
    chunk_index: int
    text: str
    page_num: int | None = None
    section: str | None = None


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------
def parse_pdf(path: str | Path) -> list[ParsedBlock]:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    blocks: list[ParsedBlock] = []
    for i, page in enumerate(reader.pages, start=1):
        text = (page.extract_text() or "").strip()
        if text:
            blocks.append(ParsedBlock(text=text, page_num=i))
    return blocks


_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")


def parse_markdown(text: str) -> list[ParsedBlock]:
    """Split Markdown into paragraph blocks, tagging each with its section.

    The section is the nearest preceding ATX heading (``#`` .. ``######``).
    """
    blocks: list[ParsedBlock] = []
    section: str | None = None
    buffer: list[str] = []

    def flush() -> None:
        nonlocal buffer
        para = "\n".join(buffer).strip()
        if para:
            blocks.append(ParsedBlock(text=para, section=section))
        buffer = []

    for line in text.splitlines():
        heading = _HEADING_RE.match(line.strip())
        if heading:
            flush()
            section = heading.group(2).strip()
        elif line.strip() == "":
            flush()
        else:
            buffer.append(line)
    flush()
    return blocks


def parse_html(html: str) -> list[ParsedBlock]:
    """Extract visible text from HTML, tagging blocks with their section.

    Section tracking follows the most recent ``<h1>``..``<h6>`` heading.
    """
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    body = soup.body or soup
    blocks: list[ParsedBlock] = []
    section: str | None = None

    block_tags = ["h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "pre", "blockquote"]
    elements = body.find_all(block_tags)
    if not elements:
        text = soup.get_text(separator="\n").strip()
        return [ParsedBlock(text=text)] if text else []

    for el in elements:
        text = el.get_text(separator=" ", strip=True)
        if not text:
            continue
        if el.name in ("h1", "h2", "h3", "h4", "h5", "h6"):
            section = text
        else:
            blocks.append(ParsedBlock(text=text, section=section))
    return blocks


def parse_document(path: str | Path, content_type: str) -> list[ParsedBlock]:
    """Dispatch to the right parser based on content type / file extension."""
    path = Path(path)
    ct = (content_type or "").lower()
    suffix = path.suffix.lower()

    if "pdf" in ct or suffix == ".pdf":
        return parse_pdf(path)

    raw = path.read_text(encoding="utf-8", errors="replace")
    if "html" in ct or suffix in (".html", ".htm"):
        return parse_html(raw)
    if "markdown" in ct or ct == "text/md" or suffix in (".md", ".markdown"):
        return parse_markdown(raw)
    # Fallback: treat as Markdown/plain text.
    return parse_markdown(raw)


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------
_WORD_RE = re.compile(r"\S+")


def _split_with_overlap(text: str, max_chars: int, overlap: int) -> list[str]:
    """Pack whitespace-delimited tokens into windows of at most ``max_chars``.

    Consecutive windows share roughly ``overlap`` characters of trailing context
    so a fact spanning a chunk boundary is still retrievable from both sides.
    """
    words = _WORD_RE.findall(text)
    if not words:
        return []

    chunks: list[str] = []
    current: list[str] = []
    length = 0  # characters in ``current`` including single-space separators

    for word in words:
        add = len(word) + (1 if current else 0)
        if current and length + add > max_chars:
            chunks.append(" ".join(current))
            # Seed the next window with trailing words up to ``overlap`` chars.
            carry: list[str] = []
            carry_len = 0
            for w in reversed(current):
                extra = len(w) + (1 if carry else 0)
                if carry_len + extra > overlap:
                    break
                carry.insert(0, w)
                carry_len += extra
            current = carry
            length = carry_len
            add = len(word) + (1 if current else 0)
        current.append(word)
        length += add

    if current:
        chunks.append(" ".join(current))
    return chunks


def chunk_blocks(
    blocks: list[ParsedBlock],
    *,
    max_chars: int = 1000,
    overlap: int = 150,
) -> list[ChunkData]:
    """Turn parsed blocks into ordered, overlapping chunks.

    Each block is chunked independently so page/section metadata is never mixed
    across boundaries. ``chunk_index`` is a stable global ordering.
    """
    if overlap >= max_chars:
        raise ValueError("overlap must be smaller than max_chars")

    out: list[ChunkData] = []
    index = 0
    for block in blocks:
        for piece in _split_with_overlap(block.text, max_chars, overlap):
            out.append(
                ChunkData(
                    chunk_index=index,
                    text=piece,
                    page_num=block.page_num,
                    section=block.section,
                )
            )
            index += 1
    return out
