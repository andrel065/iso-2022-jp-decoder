"""Core implementation of the ISO-2022-JP streaming decoder.

The decoder is a small state machine. ISO-2022-JP is a 7-bit encoding in which
the active character set is selected by escape sequences. Because escape
sequences may straddle chunk boundaries, the decoder must buffer partial
escape sequences until enough bytes arrive.

We deliberately do not implement the full ISO-2022 family: only the three
character sets that appear in ISO-2022-JP (ASCII, JIS X 0201 Roman, and
JIS X 0208-1983). This keeps the state machine small and testable.
"""

from __future__ import annotations

from typing import Iterable, Iterator, List

__all__ = ["Decoder", "decode", "decode_chunks"]

# Character set identifiers used internally.
_ASCII = "ascii"
_ROMAN = "roman"
_JIS208 = "jis208"

# Escape sequence prefixes (without the final designator byte).
_ESC_ASCII = b"\x1b(B"
_ESC_ROMAN = b"\x1b(J"
_ESC_JIS208 = b"\x1b$B"

# The longest escape prefix we recognise, used to bound buffering.
_MAX_ESCAPE_LEN = 3


def _decode_jis208(lead: int, trail: int) -> str:
    """Decode a JIS X 0208 two-byte sequence to a Unicode character.

    The standard formula maps the 94x94 JIS grid to the Unicode BMP. We use
    Python's built-in codec instead of embedding a table: it is exact and
    keeps the library dependency-free. The codec raises on invalid input, so
    callers must validate byte ranges first.
    """
    # JIS X 0208 bytes are 0x21..0x7E. Python's iso2022_jp codec expects
    # the charset to be selected by an escape sequence, so we prepend the
    # escape to the pair before decoding.
    raw = b"\x1b$B" + bytes((lead, trail))
    return raw.decode("iso2022_jp")


def _decode_roman(byte: int) -> str:
    """Decode a single JIS X 0201 Roman byte.

    JIS X 0201 Roman is nearly ASCII, but 0x5C is the yen sign and 0x7E is
    the overline. Python's iso2022_jp codec treats the Roman set as ASCII,
    which would lose that distinction, so we map those two bytes ourselves.
    """
    if byte == 0x5C:
        return "\u00a5"
    if byte == 0x7E:
        return "\u203e"
    return chr(byte)


class Decoder:
    """Incremental ISO-2022-JP decoder.

    Feed bytes with :meth:`feed`; the method returns the text that can be
    decoded so far. Call :meth:`flush` at the end of the stream to emit any
    pending character and to surface truncated escape sequences.

    The decoder is stateful: the active character set persists between calls.
    """

    def __init__(self) -> None:
        self._charset = _ASCII
        self._pending_escape = bytearray()
        self._pending_jis = bytearray()
        self._finished = False

    def feed(self, data: bytes) -> str:
        """Decode *data* and return the text produced so far.

        Partial escape sequences and partial JIS X 0208 characters are kept
        internally for the next call.
        """
        if self._finished:
            raise RuntimeError("decoder already flushed")
        if not isinstance(data, (bytes, bytearray, memoryview)):
            raise TypeError("data must be bytes-like")

        out: List[str] = []
        buf = bytes(data)
        i = 0
        n = len(buf)

        while i < n:
            b = buf[i]

            # If we are in the middle of an escape sequence, keep consuming.
            if self._pending_escape:
                self._pending_escape.append(b)
                i += 1
                if self._try_finish_escape(out):
                    continue
                # If the buffer is already longer than any valid escape and
                # still not matched, the stream is malformed. Emit the escape
                # byte literally and reset, so we do not silently drop data.
                if len(self._pending_escape) > _MAX_ESCAPE_LEN:
                    out.append(self._pending_escape[:1].decode("latin-1"))
                    self._pending_escape = bytearray()
                continue

            # Start of an escape sequence.
            if b == 0x1B:
                self._pending_escape.append(b)
                i += 1
                continue

            if self._charset == _JIS208:
                # Two-byte characters; buffer the lead byte if needed.
                if not self._pending_jis:
                    if 0x21 <= b <= 0x7E:
                        self._pending_jis.append(b)
                    else:
                        # Invalid in JIS X 0208; emit the replacement char so
                        # the caller can see that something went wrong.
                        out.append("\ufffd")
                    i += 1
                    continue
                # We have a lead byte; this byte is the trail.
                lead = self._pending_jis[0]
                self._pending_jis.clear()
                if 0x21 <= b <= 0x7E:
                    try:
                        out.append(_decode_jis208(lead, b))
                    except UnicodeDecodeError:
                        out.append("\ufffd")
                else:
                    out.append("\ufffd")
                i += 1
                continue

            # Single-byte character sets.
            if self._charset == _ROMAN:
                out.append(_decode_roman(b))
            else:
                out.append(chr(b))
            i += 1

        return "".join(out)

    def flush(self) -> str:
        """Finalise the stream and return any remaining text.

        A dangling escape sequence is emitted as the literal ESC byte so that
        the caller can detect the truncation. A dangling JIS X 0208 lead byte
        is replaced with U+FFFD.
        """
        if self._finished:
            return ""
        self._finished = True

        out: List[str] = []
        if self._pending_escape:
            # Emit the escape bytes literally; they are not valid text but
            # dropping them would hide a truncated stream.
            out.append(self._pending_escape.decode("latin-1"))
            self._pending_escape.clear()
        if self._pending_jis:
            out.append("\ufffd")
            self._pending_jis.clear()
        return "".join(out)

    def _try_finish_escape(self, out: List[str]) -> bool:
        """Check whether the pending escape buffer is a complete sequence.

        Returns True if a sequence was recognised and the buffer cleared.
        """
        esc = bytes(self._pending_escape)
        if esc == _ESC_ASCII:
            self._charset = _ASCII
            self._pending_escape = bytearray()
            return True
        if esc == _ESC_ROMAN:
            self._charset = _ROMAN
            self._pending_escape = bytearray()
            return True
        if esc == _ESC_JIS208:
            self._charset = _JIS208
            self._pending_escape = bytearray()
            return True
        return False


def decode(data: bytes) -> str:
    """Decode a complete ISO-2022-JP byte string in one call."""
    decoder = Decoder()
    text = decoder.feed(data)
    return text + decoder.flush()


def decode_chunks(chunks: Iterable[bytes]) -> str:
    """Decode an iterable of byte chunks, preserving state between chunks."""
    decoder = Decoder()
    parts: List[str] = []
    for chunk in chunks:
        parts.append(decoder.feed(chunk))
    parts.append(decoder.flush())
    return "".join(parts)
