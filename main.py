"""ai-excited-01 — Frame-Break Koi.

Copies the pre-rendered entry image (entry.png, sitting next to this
script) into the make.fun output directory and verifies the copy.

Deterministic: the output is a byte-for-byte copy of the source image,
so repeated runs always produce identical bytes. No network access,
no randomness, standard library only.
"""

import hashlib
import os
import struct
import sys
import zlib

SOURCE_NAME = "entry.png"
EXPECTED_WIDTH = 1024
EXPECTED_HEIGHT = 1024
MAX_BYTES = 1 * 1024 * 1024  # 1 MiB


def fail(message):
    print(f"ERROR: {message}", file=sys.stderr)
    sys.exit(1)


def read_png_dimensions(data):
    """Return (width, height) from a PNG byte string, or None."""
    if len(data) < 33 or data[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    if data[12:16] != b"IHDR":
        return None
    width, height = struct.unpack(">II", data[16:24])
    return width, height


def check_png_crc(data):
    """Verify the CRC of every PNG chunk; return the bad chunk type or None."""
    pos = 8
    while pos + 8 <= len(data):
        length = struct.unpack(">I", data[pos:pos + 4])[0]
        chunk_type = data[pos + 4:pos + 8]
        chunk_end = pos + 8 + length
        if chunk_end + 4 > len(data):
            return chunk_type
        stored_crc = struct.unpack(">I", data[chunk_end:chunk_end + 4])[0]
        actual_crc = zlib.crc32(chunk_type + data[pos + 8:chunk_end]) & 0xFFFFFFFF
        if stored_crc != actual_crc:
            return chunk_type
        pos = chunk_end + 4
        if chunk_type == b"IEND":
            break
    return None


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    source = os.path.join(here, SOURCE_NAME)

    out_dir = os.environ.get("MAKEFUN_OUTPUT_DIR", "/output")
    dest = os.path.join(out_dir, SOURCE_NAME)

    if not os.path.isfile(source):
        fail(f"source image not found: {source}")

    with open(source, "rb") as fh:
        data = fh.read()

    if len(data) == 0:
        fail("source image is empty")
    if len(data) > MAX_BYTES:
        fail(f"source image is {len(data)} bytes, over the 1 MiB limit")

    dims = read_png_dimensions(data)
    if dims is None:
        fail("source image is not a valid PNG")
    if dims != (EXPECTED_WIDTH, EXPECTED_HEIGHT):
        fail(f"source image is {dims[0]}x{dims[1]}, expected "
             f"{EXPECTED_WIDTH}x{EXPECTED_HEIGHT}")

    bad_chunk = check_png_crc(data)
    if bad_chunk is not None:
        fail(f"PNG CRC check failed on chunk {bad_chunk!r}")

    source_sha = hashlib.sha256(data).hexdigest()

    os.makedirs(out_dir, exist_ok=True)
    with open(dest, "wb") as fh:
        fh.write(data)

    with open(dest, "rb") as fh:
        copied = fh.read()

    if len(copied) != len(data):
        fail(f"output size {len(copied)} != source size {len(data)}")
    if hashlib.sha256(copied).hexdigest() != source_sha:
        fail("output sha256 does not match source sha256")
    # Re-verify the bytes actually on disk, not just the in-memory copy:
    # dimensions and per-chunk CRCs must still hold after the write.
    if read_png_dimensions(copied) != (EXPECTED_WIDTH, EXPECTED_HEIGHT):
        fail("output PNG dimensions changed after copy")
    bad_chunk = check_png_crc(copied)
    if bad_chunk is not None:
        fail(f"output PNG CRC check failed on chunk {bad_chunk!r}")
    if b"IEND" not in copied[-12:]:
        fail("output PNG is truncated (no IEND trailer)")

    print(f"Wrote {dest}")
    print(f"bytes: {len(copied)}")
    print(f"sha256: {source_sha}")
    print(f"dimensions: {dims[0]}x{dims[1]}")


if __name__ == "__main__":
    main()
