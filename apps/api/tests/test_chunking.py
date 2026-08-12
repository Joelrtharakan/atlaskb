"""Unit tests for parsing and chunking (pure, no DB)."""

from app.chunking import (
    ParsedBlock,
    _split_paragraphs,
    chunk_blocks,
    parse_html,
    parse_markdown,
)


def test_chunk_respects_max_chars():
    text = " ".join(f"word{i}" for i in range(500))
    chunks = chunk_blocks([ParsedBlock(text=text)], max_chars=200, overlap=40)
    assert len(chunks) > 1
    assert all(len(c.text) <= 200 for c in chunks)


def test_chunks_overlap():
    text = " ".join(f"w{i}" for i in range(200))
    chunks = chunk_blocks([ParsedBlock(text=text)], max_chars=100, overlap=30)
    # Consecutive chunks should share some trailing/leading tokens.
    first_tail = set(chunks[0].text.split()[-3:])
    second_head = set(chunks[1].text.split()[:5])
    assert first_tail & second_head


def test_chunk_index_is_sequential_and_metadata_preserved():
    blocks = [
        ParsedBlock(text="alpha " * 100, page_num=1, section="Intro"),
        ParsedBlock(text="beta " * 100, page_num=2, section="Body"),
    ]
    chunks = chunk_blocks(blocks, max_chars=120, overlap=20)
    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))
    # Page/section metadata carries through onto every chunk of the block.
    assert all(c.page_num == 1 and c.section == "Intro" for c in chunks if "alpha" in c.text)
    assert all(c.page_num == 2 and c.section == "Body" for c in chunks if "beta" in c.text)


def test_empty_text_yields_no_chunks():
    assert chunk_blocks([ParsedBlock(text="   ")]) == []


def test_overlap_must_be_smaller_than_max():
    import pytest

    with pytest.raises(ValueError):
        chunk_blocks([ParsedBlock(text="hi there")], max_chars=50, overlap=50)


def test_parse_markdown_tracks_sections():
    md = "# Title\n\nIntro paragraph.\n\n## Details\n\nMore text here.\n"
    blocks = parse_markdown(md)
    sections = {b.section for b in blocks}
    assert "Title" in sections
    assert "Details" in sections
    details = next(b for b in blocks if b.section == "Details")
    assert "More text" in details.text


def test_split_paragraphs_on_blank_lines():
    text = "First paragraph line one.\nLine two.\n\nSecond paragraph.\n\n\nThird paragraph."
    paras = _split_paragraphs(text)
    assert paras == [
        "First paragraph line one.\nLine two.",
        "Second paragraph.",
        "Third paragraph.",
    ]


def test_split_paragraphs_no_blank_lines_stays_one_block():
    text = "Line one.\nLine two.\nLine three."
    assert _split_paragraphs(text) == [text]


def test_split_paragraphs_empty_text_yields_nothing():
    assert _split_paragraphs("") == []
    assert _split_paragraphs("   \n  ") == []


def test_parse_html_tracks_sections_and_strips_scripts():
    html = (
        "<html><body>"
        "<h1>Header</h1><p>Visible paragraph.</p>"
        "<script>var x = 1;</script>"
        "<h2>Sub</h2><p>Second para.</p>"
        "</body></html>"
    )
    blocks = parse_html(html)
    texts = " ".join(b.text for b in blocks)
    assert "Visible paragraph." in texts
    assert "var x" not in texts
    assert any(b.section == "Header" for b in blocks)
    assert any(b.section == "Sub" for b in blocks)
