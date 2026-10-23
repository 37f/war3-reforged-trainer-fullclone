"""Read-only code evidence for the exact 2.0.4.23745 player-name ABI.

Never constructs a trainer, installs a hook, calls game functions, or writes
process memory. Disk code is encrypted; these bounded reads inspect live code.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

from capstone import CS_ARCH_X86, CS_MODE_64, Cs

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from war3_reforged_trainer import MEM_IMAGE, ProcessMemory, find_war3


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pid", type=int)
    parser.add_argument("--base", type=lambda value: int(value, 0))
    parser.add_argument("--rva", type=lambda value: int(value, 0), action="append")
    parser.add_argument("--bytes", type=lambda value: int(value, 0), default=0x100)
    args = parser.parse_args()
    if not 0x40 <= args.bytes <= 0x1000:
        parser.error("code window must be between 64 and 4096 bytes")
    _window, pid = find_war3(args.pid)
    decoder = Cs(CS_ARCH_X86, CS_MODE_64)
    with ProcessMemory(pid, write=False) as memory:
        base = None
        candidates = ([args.base] if args.base else
                      [region.base for region in memory.regions() if region.typ == MEM_IMAGE])
        for candidate_base in candidates:
            try:
                header = memory.read(candidate_base, 0x1000)
                if header[:2] != b"MZ":
                    continue
                offset = struct.unpack_from("<I", header, 0x3C)[0]
                if not 0x40 <= offset < len(header) - 0x80:
                    continue
                if (header[offset:offset + 4] != b"PE\0\0"
                        or struct.unpack_from("<I", header, offset + 8)[0] != 0x69E54471
                        or struct.unpack_from("<I", header, offset + 0x50)[0] != 0x0DD20000):
                    continue
                base = candidate_base
                break
            except (OSError, struct.error):
                continue
        if base is None:
            raise RuntimeError("exact 2.0.4.23745 module not found; no code read")
        windows = []
        for rva in args.rva or [0xC52F40, 0xC52EF0, 0xCA7200, 0xC5B510]:
            if not 0 < rva < 0x0DD20000 - args.bytes:
                raise ValueError("RVA outside verified module")
            data = memory.read(base + rva, args.bytes)
            fnv = 14695981039346656037
            for byte in data[:64]:
                fnv = ((fnv ^ byte) * 1099511628211) & 0xFFFFFFFFFFFFFFFF
            windows.append({
                "rva": hex(rva), "bytes_hex": data.hex(),
                "sha256": hashlib.sha256(data).hexdigest(),
                "fnv64_first_64": f"{fnv:016x}",
                "instructions": [f"{ins.address - base:#x}: {ins.mnemonic} {ins.op_str}"
                                 for ins in decoder.disasm(data, base + rva)],
            })
        print(json.dumps({"pid": pid, "read_only": True, "module_base": hex(base),
                          "timestamp": "0x69e54471", "image_size": "0xdd20000",
                          "windows": windows}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
