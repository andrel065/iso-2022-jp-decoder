import unittest

from iso_2022_jp_decoder import Decoder, decode, decode_chunks


class DecodeTests(unittest.TestCase):
    def test_ascii_passthrough(self):
        self.assertEqual(decode(b"hello"), "hello")

    def test_escape_to_jis208_and_back(self):
        # "\x1b$B" switches to JIS X 0208; "\x1b(B" switches back to ASCII.
        # The bytes 0x24 0x22 are the JIS X 0208 code for U+3042 (hiragana A).
        data = b"\x1b$B$" + b"\x1b(B"
        # The second byte of the JIS pair is 0x22, which is the quote char.
        data = b"\x1b$B" + b"\x24\x22" + b"\x1b(B"
        self.assertEqual(decode(data), "\u3042")

    def test_roman_yen_and_overline(self):
        # JIS X 0201 Roman maps 0x5C to yen and 0x7E to overline.
        data = b"\x1b(J" + b"\\~" + b"\x1b(B"
        self.assertEqual(decode(data), "\u00a5\u203e")

    def test_escape_split_across_chunks(self):
        chunks = [b"\x1b", b"$", b"B", b"\x24\x22", b"\x1b", b"(", b"B"]
        self.assertEqual(decode_chunks(chunks), "\u3042")

    def test_jis_pair_split_across_chunks(self):
        decoder = Decoder()
        first = decoder.feed(b"\x1b$B\x24")
        second = decoder.feed(b"\x22")
        self.assertEqual(first + second, "\u3042")

    def test_truncated_escape_at_flush(self):
        decoder = Decoder()
        self.assertEqual(decoder.feed(b"abc\x1b"), "abc")
        self.assertEqual(decoder.flush(), "\x1b")

    def test_truncated_jis_lead_at_flush(self):
        decoder = Decoder()
        self.assertEqual(decoder.feed(b"\x1b$B\x24"), "")
        self.assertEqual(decoder.flush(), "\ufffd")

    def test_invalid_jis_pair_produces_replacement(self):
        # 0x22 is a valid lead byte but 0x20 is below the valid trail range.
        data = b"\x1b$B\x22\x20"
        self.assertEqual(decode(data), "\ufffd")

    def test_feed_after_flush_raises(self):
        decoder = Decoder()
        decoder.flush()
        with self.assertRaises(RuntimeError):
            decoder.feed(b"x")

    def test_feed_rejects_non_bytes(self):
        decoder = Decoder()
        with self.assertRaises(TypeError):
            decoder.feed("not bytes")  # type: ignore[arg-type]

    def test_flush_is_idempotent(self):
        decoder = Decoder()
        decoder.feed(b"abc")
        self.assertEqual(decoder.flush(), "")
        self.assertEqual(decoder.flush(), "")

    def test_state_persists_across_feeds(self):
        decoder = Decoder()
        decoder.feed(b"\x1b$B")
        # Feed a complete JIS pair in the next call.
        self.assertEqual(decoder.feed(b"\x24\x22"), "\u3042")
        # Still in JIS X 0208 until we switch back.
        self.assertEqual(decoder.feed(b"\x24\x22"), "\u3042")


if __name__ == "__main__":
    unittest.main()
