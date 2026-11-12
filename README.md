# iso-2022-jp-decoder

Decode ISO-2022-JP text from a stream of byte chunks, tracking escape-sequence
charset switches across chunk boundaries.

```python
from iso_2022_jp_decoder import Decoder, decode, decode_chunks

# One-shot decoding of a complete byte string.
text = decode(b"\x1b$B$\"\x1b(B")
assert text == "\u3042"

# Streaming: feed chunks as they arrive from a socket or file.
decoder = Decoder()
parts = [decoder.feed(b"\x1b"), decoder.feed(b"$B"), decoder.feed(b"$\"")]
parts.append(decoder.flush())
assert "".join(parts) == "\u3042"

# Or wrap an iterable of chunks.
assert decode_chunks([b"\x1b$B", b"$\"", b"\x1b(B"]) == "\u3042"
```

## Why this exists

ISO-2022-JP is a stateful 7-bit encoding: the active character set is changed
by escape sequences such as `ESC ( B` for ASCII, `ESC ( J` for JIS X 0201
Roman, and `ESC $ B` for JIS X 0208. A decoder that processes a stream chunk by
chunk must remember the active set between chunks and must buffer escape
sequences that are split across a chunk boundary. Python's built-in codec
decodes a complete byte string but does not expose the incremental state, so
feeding it partial input fails.

This library implements a small explicit state machine. The trade-off is
scope: only the three character sets that actually occur in ISO-2022-JP are
supported. The full ISO-2022 family is deliberately out of scope, which keeps
the state machine small enough to reason about and test.

## The awkward edge

A truncated stream is ambiguous. If the input ends with a partial escape
sequence, `flush()` emits the raw ESC bytes so the caller can see that the
stream was cut off. If it ends with a dangling JIS X 0208 lead byte, `flush()`
emits U+FFFD. Neither case raises; the caller decides how to react.

## API

- `Decoder()` — incremental decoder with `feed(data) -> str` and `flush() -> str`.
- `decode(data: bytes) -> str` — decode a complete byte string.
- `decode_chunks(chunks: Iterable[bytes]) -> str` — decode an iterable of chunks.
