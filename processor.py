"""
Core bionic reading processor.
For each word in a PDF's text layer, overlays the first letter in bold.
"""

import fitz  # PyMuPDF
from pathlib import Path


# PyMuPDF base14 bold font aliases
_BOLD_SERIF = "tibo"   # Times Bold
_BOLD_SANS  = "hebo"   # Helvetica Bold
_BOLD_MONO  = "cobo"   # Courier Bold

_SERIF_HINTS = ("times", "roman", "georgia", "garamond", "palatino", "bookman",
                "charter", "cambria", "constantia", "didot", "minion", "caslon",
                "baskerville", "century", "schoolbook", "arnopro", "warnock")
_MONO_HINTS  = ("courier", "mono", "consol", "menlo", "monaco", "inconsolata",
                "jetbrains", "sourceCode", "firacode")


def _pick_bold_font(font_name: str) -> str:
    """Return the best-matching base14 bold font for a given font name."""
    # Strip PDF subset prefix, e.g. "ABCDEF+TimesNewRomanPSMT" → "timesnewromanpsmt"
    name = font_name.lower()
    if "+" in name:
        name = name.split("+", 1)[1]

    if any(h in name for h in _MONO_HINTS):
        return _BOLD_MONO
    if any(h in name for h in _SERIF_HINTS):
        return _BOLD_SERIF
    return _BOLD_SANS   # default: sans-serif


def _is_skippable_span(span: dict, page_height: float) -> bool:
    """
    Return True for spans we should NOT touch:
      - Very small text (footnotes, captions, page numbers)
      - Text in the top/bottom 6% of the page (headers / footers)
      - Spans whose font name suggests math / symbol glyphs
    """
    size = span.get("size", 12)
    if size < 7:
        return True

    bbox = span["bbox"]  # (x0, y0, x1, y1)
    top_margin = page_height * 0.06
    bot_margin = page_height * 0.94
    if bbox[1] < top_margin or bbox[3] > bot_margin:
        return True

    font_name = span.get("font", "").lower()
    skip_fonts = ("symbol", "zapf", "wingdings", "cmmi", "cmsy",
                  "cmex", "msam", "msbm", "stix")
    if any(f in font_name for f in skip_fonts):
        return True

    return False


def _bold_prefix_len(word_len: int) -> int:
    """Return how many leading characters of a word should be bolded."""
    return max(1, (word_len - 1) // 2)


def _overlay_bold_first_chars(page: fitz.Page, span: dict):
    """
    For each word in the span:
      1. Cover the original first character with a white rectangle.
      2. Draw the bold replacement on top.
    """
    size = span["size"]
    color = span.get("color", 0)
    bold_font = _pick_bold_font(span.get("font", ""))

    # Unpack color from packed int (0xRRGGBB) to (r, g, b) floats
    if isinstance(color, int):
        r = ((color >> 16) & 0xFF) / 255
        g = ((color >> 8) & 0xFF) / 255
        b = (color & 0xFF) / 255
    else:
        r, g, b = 0.0, 0.0, 0.0

    chars = span.get("chars", [])
    if not chars:
        return

    i = 0
    while i < len(chars):
        if chars[i]["c"].strip() == "":
            i += 1
            continue

        # Find the current word boundaries in this span.
        j = i
        while j < len(chars) and chars[j]["c"].strip() != "":
            j += 1

        prefix_len = _bold_prefix_len(j - i)
        for k in range(i, min(i + prefix_len, j)):
            ch = chars[k]
            ch_origin = ch["origin"]  # (x, y) baseline point

            # White-out the original character so it doesn't bleed through.
            char_rect = fitz.Rect(ch["bbox"])
            page.draw_rect(char_rect, color=None, fill=(1, 1, 1), overlay=True)

            # Draw bold replacement.
            page.insert_text(
                ch_origin,
                ch["c"],
                fontname=bold_font,
                fontsize=size,
                color=(r, g, b),
                overlay=True,
            )

        i = j


def process_pdf(
    input_path: str | Path,
    output_path: str | Path | None = None,
    progress_callback=None,   # callable(float 0.0–1.0) or None
) -> Path:
    """
    Read a PDF, overlay bold first letters on every word, write output.

    If output_path is None, saves as <stem>_bionic.pdf next to the input.
    Calls progress_callback(fraction) after each page if provided.
    Returns the output Path.
    """
    input_path = Path(input_path)
    if output_path is None:
        output_path = input_path.with_name(input_path.stem + "_bionic.pdf")
    output_path = Path(output_path)

    doc = fitz.open(str(input_path))
    total = len(doc)

    for i, page in enumerate(doc):
        page_height = page.rect.height
        data = page.get_text("rawdict", flags=fitz.TEXT_PRESERVE_WHITESPACE)

        for block in data.get("blocks", []):
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    if _is_skippable_span(span, page_height):
                        continue
                    _overlay_bold_first_chars(page, span)

        if progress_callback:
            progress_callback((i + 1) / total)

    doc.save(str(output_path), garbage=4, deflate=True)
    doc.close()
    return output_path


# Quick CLI test: python processor.py input.pdf
if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python processor.py <input.pdf>")
        sys.exit(1)
    out = process_pdf(sys.argv[1])
    print(f"Saved → {out}")
