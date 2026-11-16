#!/usr/bin/env python3
"""ai-excited-01 — Frame-Break Koi.

Copies the pre-rendered entry image (entry.png, sitting next to this
script) into the output directory required by make.fun and verifies the
copy byte-for-byte before exiting.

Usage:
    mkdir -p out && MAKEFUN_OUTPUT_DIR=out python3 main.py

The entry image itself is a fixed asset: this script performs no image
generation, no network access, and no randomness, so repeated runs
produce byte-identical output.
"""

import hashlib
import os
import shutil
import struct
import sys
import zlib

SOURCE_NAME = "entry.png"
EXPECTED_WIDTH = 1024
EXPECTED_HEIGHT = 1024
MAX_BYTES = 1 * 1024 * 1024  # 1 MiB


def sha256_of(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def png_dimensions(path):
    """Return (width, height) of a PNG file, verifying its signature."""
    with open(path, "rb") as handle:
        header = handle.read(33)
    if len(header) < 33 or header[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("not a PNG file (bad signature)")
    length, chunk_type = struct.unpack(">I4s", header[8:16])
    if chunk_type != b"IHDR" or length != 13:
        raise ValueError("not a PNG file (missing IHDR chunk)")
    width, height = struct.unpack(">II", header[16:24])
    return width, height


def png_chunks_valid(path):
    """Walk the PNG chunk list and check every CRC."""
    with open(path, "rb") as handle:
        data = handle.read()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("not a PNG file (bad signature)")
    pos = 8
    saw_iend = False
    while pos + 8 <= len(data):
        length, chunk_type = struct.unpack(">I4s", data[pos:pos + 8])
        end = pos + 8 + length + 4
        if end > len(data):
            raise ValueError("truncated PNG chunk: %r" % chunk_type)
        stored_crc, = struct.unpack(">I", data[pos + 8 + length:end])
        actual_crc = zlib.crc32(chunk_type + data[pos + 8:pos + 8 + length])
        if stored_crc != (actual_crc & 0xFFFFFFFF):
            raise ValueError("bad CRC in PNG chunk: %r" % chunk_type)
        if chunk_type == b"IEND":
            saw_iend = True
            break
        pos = end
    if not saw_iend:
        raise ValueError("PNG missing IEND chunk")
    return True


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    source = os.path.join(here, SOURCE_NAME)
    out_dir = os.environ.get("MAKEFUN_OUTPUT_DIR", "/output")
    os.makedirs(out_dir, exist_ok=True)
    destination = os.path.join(out_dir, SOURCE_NAME)

    if not os.path.isfile(source):
        print("error: source image not found: %s" % source, file=sys.stderr)
        return 1

    source_size = os.path.getsize(source)
    if source_size > MAX_BYTES:
        print("error: source image %d bytes exceeds 1 MiB" % source_size,
              file=sys.stderr)
        return 1
    try:
        src_w, src_h = png_dimensions(source)
        png_chunks_valid(source)
    except ValueError as exc:
        print("error: source image invalid: %s" % exc, file=sys.stderr)
        return 1
    if (src_w, src_h) != (EXPECTED_WIDTH, EXPECTED_HEIGHT):
        print("error: source is %dx%d, expected 1024x1024" % (src_w, src_h),
              file=sys.stderr)
        return 1

    shutil.copyfile(source, destination)

    # --- verify the copy ---
    if not os.path.isfile(destination):
        print("error: output image missing: %s" % destination, file=sys.stderr)
        return 1
    if os.path.getsize(destination) != source_size:
        print("error: output size differs from source", file=sys.stderr)
        return 1
    if sha256_of(destination) != sha256_of(source):
        print("error: output sha256 differs from source", file=sys.stderr)
        return 1
    width, height = png_dimensions(destination)
    if (width, height) != (EXPECTED_WIDTH, EXPECTED_HEIGHT):
        print("error: expected 1024x1024, got %dx%d" % (width, height),
              file=sys.stderr)
        return 1
    png_chunks_valid(destination)

    print("wrote %s (%d bytes, %dx%d, sha256 %s)"
          % (destination, source_size, width, height,
             sha256_of(destination)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
