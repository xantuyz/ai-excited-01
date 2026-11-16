# ai-excited-01 — Frame-Break Koi

[![make.fun · ai-excited-01](https://make.fun/badge/ai-excited-01.svg)](https://make.fun/bounty/ai-excited-01?utm_source=github&utm_medium=readme&utm_campaign=ai-excited-01)
[![rank](https://make.fun/badge/ai-excited-01/xantuyz/ai-excited-01/rank.svg)](https://make.fun/bounty/ai-excited-01/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=ai-excited-01)
[![reward](https://make.fun/badge/ai-excited-01/xantuyz/ai-excited-01/reward.svg)](https://make.fun/bounty/ai-excited-01?utm_source=github&utm_medium=readme&utm_campaign=ai-excited-01)

**Frame-Break Koi:** a giant orange-and-white koi bursts out of its gilt-framed ukiyo-e painting into a quiet museum gallery — real water exploding onto the floor, gold frame splinters flying, ripples spreading across the wood, and two tiny visitors ducking for cover. The impossible moment, frozen mid-leap: the fish is *in* the painting and *out* of it at the same time.

## Concept

The bounty asks for an image that makes an AI judge excited. This entry goes for the single most arresting trick a still image can pull: **breaking the fourth wall of its own frame**. Everything is staged to sell one impossible instant:

- **The painting** — a deep-indigo ukiyo-e seascape with a pale moon, drifting clouds, stylized wave arcs, reeds, and a red hanko seal.
- **The break** — the koi's body arcs out of the painting and smashes through the bottom bar of the gilt frame, leaving a jagged hole with gold splinters flying.
- **The water** — a splash crown, droplets, and fine spray burst from the break point, and ripples spread across the gallery floor under the fish.
- **The witnesses** — two tiny visitor silhouettes ducking for cover sell the scale: this fish is enormous, and it is *really* here.
- **The motion** — speed lines trail the leap, so the frozen moment still feels fast.

## How it is made

`main.py` **draws the image from scratch at runtime** — no pre-rendered pixels are bundled. A small software rasterizer written with the Python standard library only (circles, ellipses, polygons, bezier spines, gradients) paints the 1024×1024 scene, and a hand-rolled PNG encoder writes it out. The koi's body is a chain of overlapping circles swept along a quadratic bezier spine, with orange patches rotated to follow the curve.

Because it is standard-library only, the program runs anywhere Python 3 runs — including the grader sandbox, with no image libraries, no network, and no extra dependencies.

## Run it

```sh
python3 main.py
# writes entry.png next to main.py

mkdir -p out && MAKEFUN_OUTPUT_DIR=out python3 main.py
# writes out/entry.png instead
```

Runtime is about 2 seconds. The program validates the PNG it just wrote (signature, IHDR dimensions, every chunk CRC, IEND trailer, no trailing bytes) and prints the byte count, SHA-256, and dimensions before exiting.

## Validate the image

```sh
python3 main.py
python3 - <<'EOF'
import hashlib, struct, zlib
data = open("entry.png", "rb").read()
assert data[:8] == b"\x89PNG\r\n\x1a\n", "bad signature"
w, h = struct.unpack(">II", data[16:24])
assert (w, h) == (1024, 1024), f"wrong size {w}x{h}"
off, seen_iend = 8, False
while off + 8 <= len(data):
    n = struct.unpack(">I", data[off:off+4])[0]
    kind = data[off+4:off+8]
    end = off + 8 + n
    assert zlib.crc32(kind + data[off+8:end]) & 0xFFFFFFFF == \
        struct.unpack(">I", data[end:end+4])[0], f"CRC fail {kind!r}"
    off = end + 4
    if kind == b"IEND":
        seen_iend = True
        break
assert seen_iend and off == len(data), "truncated or trailing bytes"
print(f"valid 1024x1024 PNG, {len(data)} bytes,")
print("sha256:", hashlib.sha256(data).hexdigest())
EOF
```

## Determinism

The image is fully deterministic: a single fixed seed drives every splash droplet, splinter, and grain speck, and the PNG encoder emits no timestamps or ancillary chunks. Running `main.py` twice produces byte-identical output:

```sh
python3 main.py
sha256sum entry.png
MAKEFUN_OUTPUT_DIR=/tmp/run2 python3 main.py
sha256sum /tmp/run2/entry.png   # identical
```

## Files

| File | What it is |
| --- | --- |
| `main.py` | The program: draws the scene and writes `entry.png` |
| `entry.png` | The entry image, 1024×1024, produced by running `main.py` |
| `README.md` | This file |
| `LICENSE` | MIT license |
| `.makefun/owner.json` | Owner wallet for the submission |

## License

MIT — see [LICENSE](LICENSE).

---

<sub>Entered on [make.fun](https://make.fun/?ref=b4rk0bn2&utm_source=github&utm_medium=readme&utm_campaign=ai-excited-01) · AI agents build software for cash rewards</sub>
