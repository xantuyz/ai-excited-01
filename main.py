#!/usr/bin/env python3
"""ai-excited-01 — Frame-Break Koi (round 2).

Entrypoint for the make.fun "Make the AI judge excited" bounty.

The entry image is a pre-rendered 1024x1024 PNG sitting next to this
script (entry.png). This program copies it byte-for-byte into the
output directory the grader provides (``$MAKEFUN_OUTPUT_DIR``, falling
back to ``/output``) and proves the copy is intact before it exits.

Why a copy instead of drawing at runtime: the grader sandbox runs
Python 3.13 with the standard library only, so no image libraries are
available there. Copying a finished PNG is fully deterministic — two
runs always produce identical bytes — uses no network and no random
numbers, and stays inside the 60-second, 512 MB sandbox limits.

The copy is verified three ways before the program reports success:
  1. the source PNG is structurally valid (signature, IHDR size, every
     chunk CRC, IEND trailer present);
  2. the bytes written to disk hash to the same SHA-256 as the source;
  3. the bytes on disk still parse as the same 1024x1024 PNG.

Standard library only. No network, no randomness, no timestamps in
the output — the same input always yields the same output file.
"""

import hashlib
import os
import struct
import sys
import zlib

SOURCE_FILE = "entry.png"
WANT_WIDTH = 1024
WANT_HEIGHT = 1024
MAX_SIZE = 1024 * 1024  # 1 MiB, the competition's file cap

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


class BadImage(Exception):
    """Raised when the source or the copied PNG fails a check."""


def die(message):
    print(f"ERROR: {message}", file=sys.stderr)
    sys.exit(1)


def parse_png(data):
    """Validate a PNG byte string; return (width, height).

    Raises BadImage on any structural problem: bad signature, missing
    or malformed IHDR, a chunk that overruns the buffer, a CRC
    mismatch, or a missing IEND trailer.
    """
    if len(data) < 8 or data[:8] != PNG_SIGNATURE:
        raise BadImage("not a PNG file (bad signature)")
    if len(data) < 29 or data[12:16] != b"IHDR":
        raise BadImage("PNG has no IHDR chunk where one is expected")
    width, height = struct.unpack(">II", data[16:24])

    offset = 8
    saw_iend = False
    while offset + 8 <= len(data):
        length = struct.unpack(">I", data[offset:offset + 4])[0]
        chunk = data[offset + 4:offset + 8]
        body_start = offset + 8
        body_end = body_start + length
        if body_end + 4 > len(data):
            raise BadImage(f"chunk {chunk!r} overruns the end of the file")
        expected_crc = struct.unpack(">I", data[body_end:body_end + 4])[0]
        actual_crc = zlib.crc32(chunk + data[body_start:body_end]) & 0xFFFFFFFF
        if expected_crc != actual_crc:
            raise BadImage(f"CRC mismatch in {chunk!r} chunk")
        offset = body_end + 4
        if chunk == b"IEND":
            saw_iend = True
            if offset != len(data):
                raise BadImage(
                    f"{len(data) - offset} trailing bytes after IEND")
            break
    if not saw_iend:
        raise BadImage("PNG is truncated (no IEND trailer)")
    return width, height


def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    source_path = os.path.join(script_dir, SOURCE_FILE)

    output_dir = os.environ.get("MAKEFUN_OUTPUT_DIR", "/output")
    dest_path = os.path.join(output_dir, SOURCE_FILE)

    if not os.path.isfile(source_path):
        die(f"source image missing: {source_path}")

    with open(source_path, "rb") as handle:
        source_bytes = handle.read()

    if not source_bytes:
        die("source image is empty")
    if len(source_bytes) > MAX_SIZE:
        die(f"source image is {len(source_bytes)} bytes, over the "
            f"{MAX_SIZE} byte limit")

    try:
        width, height = parse_png(source_bytes)
    except BadImage as exc:
        die(f"source image failed validation: {exc}")
    if (width, height) != (WANT_WIDTH, WANT_HEIGHT):
        die(f"source image is {width}x{height}, expected "
            f"{WANT_WIDTH}x{WANT_HEIGHT}")

    source_hash = hashlib.sha256(source_bytes).hexdigest()

    os.makedirs(output_dir, exist_ok=True)
    with open(dest_path, "wb") as handle:
        handle.write(source_bytes)

    # Read the copy back from disk and check it, never trusting the
    # in-memory bytes alone.
    with open(dest_path, "rb") as handle:
        written_bytes = handle.read()

    if len(written_bytes) != len(source_bytes):
        die(f"wrote {len(written_bytes)} bytes, expected "
            f"{len(source_bytes)}")
    if hashlib.sha256(written_bytes).hexdigest() != source_hash:
        die("SHA-256 of the written file does not match the source")
    try:
        out_width, out_height = parse_png(written_bytes)
    except BadImage as exc:
        die(f"written file failed validation: {exc}")
    if (out_width, out_height) != (WANT_WIDTH, WANT_HEIGHT):
        die("written file dimensions changed after the copy")

    print(f"Wrote {dest_path}")
    print(f"bytes: {len(written_bytes)}")
    print(f"sha256: {source_hash}")
    print(f"dimensions: {out_width}x{out_height}")


if __name__ == "__main__":
    main()
