"""Zero-Dependency PDF Stream Ingestion & Text Extractor.

Track B - Native arXiv & Academic PDF Parsing.
Pure Python Standard Library (3.10+) - Zero External Dependencies.

Implements a pure standard-library PDF text stream parser using `zlib` and `re`
to decompress `/FlateDecode` object streams, interpret PostScript/PDF text
positioning operators (`BT`...`ET`, `Tj`, `TJ`, `Td`, `TD`, `T*`, `'`, `"`),
decode octal/escaped literal strings and UTF-16BE/Latin-1 hex strings, and
extract document metadata (`/Title`, `/Author`, `/CreationDate`) without
any third-party PDF libraries.
"""

from __future__ import annotations

import html
import logging
import re
import zlib
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class ExtractedPDFDocument:
    """Structured result of pure-stdlib PDF stream extraction."""

    text: str
    paragraphs: List[str] = field(default_factory=list)
    headings: List[str] = field(default_factory=list)
    title: Optional[str] = None
    author: Optional[str] = None
    published_date: Optional[str] = None
    page_count: int = 0
    stream_count: int = 0
    decompressed_streams: int = 0


class ZeroDepPDFExtractor:
    """Pure Python standard-library PDF stream parser and text extractor."""

    # Matches PDF stream blocks: << ...dict... >> stream\r?\n ...bytes... \r?\nendstream
    _STREAM_BLOCK_RE = re.compile(
        rb"(<<.*?>>)\s*stream(?:\r\n|\n|\r)(.*?)(?:\r\n|\n|\r)?endstream",
        re.DOTALL,
    )

    # Matches BT ... ET text object blocks inside a content stream
    _BT_ET_RE = re.compile(r"\bBT\b(.*?)\bET\b", re.DOTALL)

    # Matches /Page objects (excluding /Pages catalog nodes)
    _PAGE_OBJ_RE = re.compile(rb"/Type\s*/Page\b(?![sS])")

    # Matches PDF Info dictionary fields like /Title (Some Title) or /Title <FEFF...>
    _INFO_LITERAL_RE = {
        "title": re.compile(rb"/Title\s*\((?:\\.|[^\\)])*\)", re.DOTALL),
        "author": re.compile(rb"/Author\s*\((?:\\.|[^\\)])*\)", re.DOTALL),
        "date": re.compile(rb"/CreationDate\s*\((?:\\.|[^\\)])*\)", re.DOTALL),
    }

    _INFO_HEX_RE = {
        "title": re.compile(rb"/Title\s*<([0-9A-Fa-f\s]+)>"),
        "author": re.compile(rb"/Author\s*<([0-9A-Fa-f\s]+)>"),
        "date": re.compile(rb"/CreationDate\s*<([0-9A-Fa-f\s]+)>"),
    }

    # Octal escape sequence in PDF literal strings: \ddd (1 to 3 octal digits)
    _OCTAL_RE = re.compile(r"\\([0-7]{1,3})")

    @classmethod
    def is_pdf_bytes(cls, data: bytes) -> bool:
        """Check whether raw byte payload begins with a PDF header signature."""
        if not data:
            return False
        return b"%PDF-" in data[:1024]

    @classmethod
    def is_pdf_content(cls, content_type: str = "", url: str = "", raw_text: str = "") -> bool:
        """Determine whether a response represents a PDF stream."""
        ct_lower = (content_type or "").lower()
        url_lower = (url or "").lower().split("?")[0]
        if "application/pdf" in ct_lower or "application/x-pdf" in ct_lower:
            return True
        if url_lower.endswith(".pdf") or "/pdf/" in url_lower:
            if raw_text.startswith("%PDF-") or not raw_text.lstrip().startswith("<"):
                return True
        if raw_text and raw_text[:1024].lstrip().startswith("%PDF-"):
            return True
        return False

    @classmethod
    def decode_pdf_literal_string(cls, raw_str: str) -> str:
        """Decode a PDF literal string (inside parentheses) handling escapes and octals."""
        if not raw_str:
            return ""

        # 1. Remove line continuation backslashes (\ followed by newline)
        s = re.sub(r"\\(?:\r\n|\r|\n)", "", raw_str)

        # 2. Decode octal escapes \ddd
        def _replace_octal(match: re.Match) -> str:
            oct_val = int(match.group(1), 8)
            if 32 <= oct_val <= 126 or oct_val >= 160:
                return chr(oct_val)
            if oct_val in (9, 10, 13):
                return " "
            return ""

        s = cls._OCTAL_RE.sub(_replace_octal, s)

        # 3. Decode standard PDF escape sequences
        out: List[str] = []
        i = 0
        n = len(s)
        while i < n:
            ch = s[i]
            if ch == "\\" and i + 1 < n:
                nxt = s[i + 1]
                if nxt == "n":
                    out.append("\n")
                elif nxt == "r":
                    out.append("\r")
                elif nxt == "t":
                    out.append("\t")
                elif nxt == "b":
                    out.append("")
                elif nxt == "f":
                    out.append("\n")
                elif nxt in ("(", ")", "\\"):
                    out.append(nxt)
                else:
                    out.append(nxt)
                i += 2
            else:
                out.append(ch)
                i += 1

        return "".join(out)

    @classmethod
    def decode_pdf_hex_string(cls, hex_str: str) -> str:
        """Decode a PDF hexadecimal string <...> supporting UTF-16BE BOM and Latin-1."""
        cleaned = re.sub(r"\s+", "", hex_str)
        if not cleaned:
            return ""
        # Pad odd-length hex strings with trailing 0 per PDF spec
        if len(cleaned) % 2 == 1:
            cleaned += "0"
        try:
            raw_bytes = bytes.fromhex(cleaned)
        except ValueError:
            return ""

        if raw_bytes.startswith(b"\xfe\xff"):
            try:
                return raw_bytes[2:].decode("utf-16-be", errors="ignore")
            except Exception:
                pass
        if raw_bytes.startswith(b"\xff\xfe"):
            try:
                return raw_bytes[2:].decode("utf-16-le", errors="ignore")
            except Exception:
                pass

        # If every other byte is 0x00, likely UTF-16BE without BOM
        if len(raw_bytes) >= 4 and raw_bytes[0] == 0 and raw_bytes[2] == 0:
            try:
                return raw_bytes.decode("utf-16-be", errors="ignore")
            except Exception:
                pass

        try:
            return raw_bytes.decode("utf-8")
        except UnicodeDecodeError:
            return raw_bytes.decode("latin-1", errors="ignore")

    @classmethod
    def _extract_balanced_parens(cls, text: str, start_idx: int) -> Tuple[str, int]:
        """Extract balanced parenthesized literal string starting at `start_idx` (where text[start_idx] == '(')."""
        depth = 0
        i = start_idx
        n = len(text)
        buf: List[str] = []

        while i < n:
            ch = text[i]
            if ch == "\\" and i + 1 < n:
                if depth >= 1:
                    buf.append(ch)
                    buf.append(text[i + 1])
                i += 2
                continue
            if ch == "(":
                if depth >= 1:
                    buf.append(ch)
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    return "".join(buf), i + 1
                buf.append(ch)
            else:
                if depth >= 1:
                    buf.append(ch)
            i += 1

        return "".join(buf), n

    @classmethod
    def _parse_text_block(cls, block: str) -> List[str]:
        """Parse a single BT ... ET content block into lines/segments of text."""
        lines: List[str] = []
        current_line: List[str] = []

        i = 0
        n = len(block)

        while i < n:
            ch = block[i]

            # 1. Parenthesized literal string: (...) followed by Tj, ', or "
            if ch == "(":
                literal_content, next_i = cls._extract_balanced_parens(block, i)
                decoded = cls.decode_pdf_literal_string(literal_content)
                # Look ahead for operator
                rest = block[next_i : next_i + 20].lstrip()
                if rest.startswith("'") or rest.startswith('"'):
                    if current_line:
                        lines.append("".join(current_line).strip())
                        current_line = []
                if decoded:
                    current_line.append(decoded)
                i = next_i
                continue

            # 2. TJ array: [ (text) -200 (more) <hex> ] TJ
            if ch == "[":
                end_bracket = block.find("]", i + 1)
                if end_bracket != -1:
                    array_body = block[i + 1 : end_bracket]
                    arr_text = cls._parse_tj_array(array_body)
                    if arr_text:
                        current_line.append(arr_text)
                    i = end_bracket + 1
                    continue

            # 3. Hex string outside array: <...> Tj
            if ch == "<" and (i + 1 < n and block[i + 1] != "<"):
                end_angle = block.find(">", i + 1)
                if end_angle != -1:
                    hex_body = block[i + 1 : end_angle]
                    decoded_hex = cls.decode_pdf_hex_string(hex_body)
                    if decoded_hex:
                        current_line.append(decoded_hex)
                    i = end_angle + 1
                    continue

            # 4. Detect line-breaking text positioning operators: T*, Td, TD, TL
            if ch == "T" and i + 1 < n:
                op2 = block[i + 1]
                # T* moves to start of next line
                if op2 == "*":
                    if current_line:
                        lines.append("".join(current_line).strip())
                        current_line = []
                    i += 2
                    continue
                # Td or TD with non-zero vertical offset moves to a new line
                if op2 in ("d", "D") and (i == 0 or not block[i - 1].isalpha()):
                    if i + 2 >= n or not block[i + 2].isalpha():
                        # Check preceding numeric dy argument
                        preceding = block[max(0, i - 40) : i].strip().split()
                        if len(preceding) >= 2:
                            try:
                                dy = float(preceding[-1])
                                dx = float(preceding[-2])
                                if abs(dy) > 0.1:
                                    if current_line:
                                        lines.append("".join(current_line).strip())
                                        current_line = []
                                elif dx > 1.0 and current_line and not current_line[-1].endswith(" "):
                                    current_line.append(" ")
                            except ValueError:
                                pass
                        i += 2
                        continue

            i += 1

        if current_line:
            lines.append("".join(current_line).strip())

        return [ln for ln in lines if ln]

    @classmethod
    def _parse_tj_array(cls, array_body: str) -> str:
        """Parse the inside of a `[...] TJ` operator array, converting kerning offsets into spaces."""
        parts: List[str] = []
        i = 0
        n = len(array_body)

        while i < n:
            ch = array_body[i]
            if ch == "(":
                lit, next_i = cls._extract_balanced_parens(array_body, i)
                decoded = cls.decode_pdf_literal_string(lit)
                if decoded:
                    parts.append(decoded)
                i = next_i
            elif ch == "<":
                end_angle = array_body.find(">", i + 1)
                if end_angle != -1:
                    decoded = cls.decode_pdf_hex_string(array_body[i + 1 : end_angle])
                    if decoded:
                        parts.append(decoded)
                    i = end_angle + 1
                else:
                    i += 1
            elif ch in "-+0123456789.":
                # Parse numeric kerning adjustment; large negative values (< -100) indicate inter-word space
                m = re.match(r"[-+]?\d+(?:\.\d+)?", array_body[i:])
                if m:
                    try:
                        kern = float(m.group(0))
                        if kern <= -100.0 and parts and not parts[-1].endswith(" "):
                            parts.append(" ")
                    except ValueError:
                        pass
                    i += len(m.group(0))
                else:
                    i += 1
            else:
                i += 1

        return "".join(parts)

    @classmethod
    def _decompress_stream(cls, dict_bytes: bytes, raw_stream: bytes) -> Optional[str]:
        """Decompress a PDF stream if `/FlateDecode` is specified, or decode uncompressed text stream."""
        is_flate = bool(re.search(rb"/FlateDecode\b|/Fl\b", dict_bytes))
        # Skip binary image/font/metadata streams that are not content streams
        if re.search(rb"/Subtype\s*/Image\b|/FontFile[23]?\b|/Type\s*/XRef\b", dict_bytes):
            return None

        payload = raw_stream
        if is_flate:
            decompressed: Optional[bytes] = None
            for wbits in (zlib.MAX_WBITS, -zlib.MAX_WBITS):
                try:
                    decompressed = zlib.decompress(raw_stream, wbits)
                    break
                except zlib.error:
                    try:
                        decompressed = zlib.decompress(raw_stream.strip(b"\r\n"), wbits)
                        break
                    except zlib.error:
                        continue
            if decompressed is None:
                return None
            payload = decompressed

        # Check if decompressed payload looks like a content stream containing text operators
        if b"BT" not in payload and b"Tj" not in payload and b"TJ" not in payload:
            return None

        return payload.decode("latin-1", errors="ignore")

    @classmethod
    def _extract_metadata(cls, pdf_bytes: bytes) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """Extract Title, Author, and CreationDate from PDF `/Info` dictionary."""
        title: Optional[str] = None
        author: Optional[str] = None
        pub_date: Optional[str] = None

        # 1. Literal string metadata
        m_title = cls._INFO_LITERAL_RE["title"].search(pdf_bytes)
        if m_title:
            raw = m_title.group(0).decode("latin-1", errors="ignore")
            p_start = raw.find("(")
            if p_start != -1:
                lit, _ = cls._extract_balanced_parens(raw, p_start)
                title = cls.decode_pdf_literal_string(lit).strip() or None

        m_author = cls._INFO_LITERAL_RE["author"].search(pdf_bytes)
        if m_author:
            raw = m_author.group(0).decode("latin-1", errors="ignore")
            p_start = raw.find("(")
            if p_start != -1:
                lit, _ = cls._extract_balanced_parens(raw, p_start)
                author = cls.decode_pdf_literal_string(lit).strip() or None

        m_date = cls._INFO_LITERAL_RE["date"].search(pdf_bytes)
        if m_date:
            raw = m_date.group(0).decode("latin-1", errors="ignore")
            p_start = raw.find("(")
            if p_start != -1:
                lit, _ = cls._extract_balanced_parens(raw, p_start)
                date_str = cls.decode_pdf_literal_string(lit).strip()
                # Format D:YYYYMMDDHHmmSS -> YYYY-MM-DD
                m_iso = re.search(r"D:(\d{4})(\d{2})?(\d{2})?", date_str)
                if m_iso:
                    y = m_iso.group(1)
                    mo = m_iso.group(2) or "01"
                    d = m_iso.group(3) or "01"
                    pub_date = f"{y}-{mo}-{d}"
                elif date_str:
                    pub_date = date_str

        # 2. Hex string fallback
        if not title:
            mh = cls._INFO_HEX_RE["title"].search(pdf_bytes)
            if mh:
                title = cls.decode_pdf_hex_string(mh.group(1).decode("ascii", errors="ignore")).strip() or None
        if not author:
            mh = cls._INFO_HEX_RE["author"].search(pdf_bytes)
            if mh:
                author = cls.decode_pdf_hex_string(mh.group(1).decode("ascii", errors="ignore")).strip() or None

        return title, author, pub_date

    @classmethod
    def _assemble_paragraphs_and_headings(cls, raw_lines: List[str]) -> Tuple[List[str], List[str]]:
        """Reflow extracted PDF text lines into clean paragraphs and section headings."""
        paragraphs: List[str] = []
        headings: List[str] = []
        current_para: List[str] = []

        heading_pattern = re.compile(
            r"^(?:(?:\d+(?:\.\d+)*\.?\s+)|(?:[I|V|X]+\.\s+))?[A-Z][A-Za-z0-9\s,\-:]{2,70}$"
        )
        academic_sections = {
            "abstract", "introduction", "background", "related work", "methodology",
            "methods", "experimental setup", "experiments", "results", "discussion",
            "conclusion", "conclusions", "references", "acknowledgments",
        }

        for line in raw_lines:
            # Normalize whitespace and strip control chars
            clean_line = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", line)
            clean_line = " ".join(clean_line.split()).strip()
            if not clean_line:
                if current_para:
                    joined = " ".join(current_para).strip()
                    if len(joined) >= 25:
                        paragraphs.append(joined)
                    current_para = []
                continue

            # Ignore standalone page numbers
            if re.match(r"^\d{1,4}$", clean_line):
                continue

            # De-hyphenate line wraps if previous line ended with word-hyphen
            if current_para and current_para[-1].endswith("-") and clean_line[0].islower():
                current_para[-1] = current_para[-1][:-1] + clean_line
                continue

            # Check if line is a section heading
            lower_stripped = re.sub(r"^[\d\.IVX]+\s*", "", clean_line.lower()).strip()
            is_heading = (
                lower_stripped in academic_sections
                or (
                    len(clean_line) <= 75
                    and not clean_line.endswith(".")
                    and heading_pattern.match(clean_line) is not None
                    and len(clean_line.split()) <= 10
                )
            )

            if is_heading and len(clean_line) >= 3:
                if current_para:
                    joined = " ".join(current_para).strip()
                    if len(joined) >= 25:
                        paragraphs.append(joined)
                    current_para = []
                if clean_line not in headings:
                    headings.append(clean_line)
                continue

            current_para.append(clean_line)

            # Flush paragraph if sentence ends and buffer is reasonably sized
            joined_len = sum(len(x) for x in current_para)
            if clean_line.endswith((".", "!", "?")) and joined_len >= 180:
                joined = " ".join(current_para).strip()
                if len(joined) >= 25:
                    paragraphs.append(joined)
                current_para = []

        if current_para:
            joined = " ".join(current_para).strip()
            if len(joined) >= 25:
                paragraphs.append(joined)
            elif joined and not paragraphs:
                paragraphs.append(joined)

        return paragraphs, headings

    @classmethod
    def extract_from_bytes(cls, pdf_bytes: bytes) -> ExtractedPDFDocument:
        """Extract text, paragraphs, headings, and metadata from raw PDF bytes."""
        if not pdf_bytes:
            return ExtractedPDFDocument(text="")

        title, author, pub_date = cls._extract_metadata(pdf_bytes)
        page_count = len(cls._PAGE_OBJ_RE.findall(pdf_bytes))

        all_lines: List[str] = []
        stream_count = 0
        decompressed_count = 0

        for match in cls._STREAM_BLOCK_RE.finditer(pdf_bytes):
            stream_count += 1
            dict_bytes = match.group(1)
            raw_stream = match.group(2)

            content_str = cls._decompress_stream(dict_bytes, raw_stream)
            if not content_str:
                continue

            decompressed_count += 1
            bt_blocks = cls._BT_ET_RE.findall(content_str)
            if bt_blocks:
                for blk in bt_blocks:
                    all_lines.extend(cls._parse_text_block(blk))
            else:
                all_lines.extend(cls._parse_text_block(content_str))

        paragraphs, headings = cls._assemble_paragraphs_and_headings(all_lines)
        if not title and headings:
            title = headings[0]

        full_text = "\n\n".join(paragraphs) if paragraphs else " ".join(all_lines).strip()

        return ExtractedPDFDocument(
            text=full_text,
            paragraphs=paragraphs,
            headings=headings,
            title=title,
            author=author,
            published_date=pub_date,
            page_count=max(1, page_count) if (paragraphs or all_lines) else 0,
            stream_count=stream_count,
            decompressed_streams=decompressed_count,
        )

    @classmethod
    def pdf_bytes_to_html(
        cls,
        pdf_bytes: bytes,
        url: str = "",
        fallback_title: str = "Academic PDF Preprint",
        fallback_author: str = "",
        fallback_date: str = "",
        abstract_summary: str = "",
    ) -> str:
        """Convert raw PDF bytes into a structured HTML document for seamless pipeline ingestion."""
        extracted = cls.extract_from_bytes(pdf_bytes)
        title = extracted.title or fallback_title
        author = extracted.author or fallback_author or "Academic Author"
        pub_date = extracted.published_date or fallback_date

        body_parts: List[str] = []
        if abstract_summary:
            body_parts.append(f'<div class="abstract"><h2>Abstract</h2><p>{html.escape(abstract_summary)}</p></div>')

        if extracted.headings or extracted.paragraphs:
            body_parts.append('<div class="pdf-fulltext">')
            for h in extracted.headings[:10]:
                body_parts.append(f"<h2>{html.escape(h)}</h2>")
            for p in extracted.paragraphs:
                body_parts.append(f"<p>{html.escape(p)}</p>")
            body_parts.append("</div>")
        elif extracted.text:
            body_parts.append(f'<div class="pdf-fulltext"><p>{html.escape(extracted.text)}</p></div>')

        body_html = "\n".join(body_parts)
        return (
            f"<!DOCTYPE html>\n"
            f'<html lang="en"><head>\n'
            f"<title>{html.escape(title)}</title>\n"
            f'<meta name="author" content="{html.escape(author)}">\n'
            f'<meta property="article:published_time" content="{html.escape(pub_date)}">\n'
            f'<meta name="pdf:pages" content="{extracted.page_count}">\n'
            f'<link rel="canonical" href="{html.escape(url)}">\n'
            f"</head><body><main>\n"
            f"<h1>{html.escape(title)}</h1>\n"
            f'<div class="byline">By {html.escape(author)} on {html.escape(pub_date)}</div>\n'
            f"{body_html}\n"
            f"</main></body></html>"
        )
