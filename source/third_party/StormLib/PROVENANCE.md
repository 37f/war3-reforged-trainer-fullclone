# StormLib read-only catalog dependency

- Upstream: https://github.com/ladislav-zezula/StormLib
- Version: v9.40, official `stormlib_dll.zip` release asset.
- Asset: https://github.com/ladislav-zezula/StormLib/releases/download/v9.40/stormlib_dll.zip
- Asset SHA-256 (verified against GitHub release API digest): `b2c9635e7b63edee1bd7c82e7dc180d739f3accb2b8994804c7774e464ce89ae`.
- Included file: `x64/StormLib.dll`, PE machine AMD64 (0x8664), 569856 bytes.
- Included DLL SHA-256: `93321f6f030be5d7d79eb4cbf433d6ef7e83ce20d47d8963717f207d54afbe16`.
- Release DLL project uses Unicode paths. The adapter binds archive filenames as wide strings, internal MPQ names as UTF-8 bytes, and C++ bool returns as ctypes.c_bool.
- License: upstream MIT notice in `LICENSE.txt`, fetched from the v9.40 tag.
- Production adapter exposes only open/read/size/close and opens with MPQ_OPEN_READ_ONLY (0x100). Test-only fixture tooling uses create/write APIs solely in pytest temporary directories.
- This DLL is loaded only into the trainer for offline file parsing. It is separate from the unchanged native helper and is not injected into Warcraft III.
