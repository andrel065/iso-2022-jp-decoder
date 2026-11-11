"""Decode ISO-2022-JP text across stream chunks."""

from .core import Decoder, decode, decode_chunks

__all__ = ["Decoder", "decode", "decode_chunks"]
