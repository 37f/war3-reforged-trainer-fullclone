# CascLib supplied with R23

Upstream: https://github.com/ladislav-zezula/CascLib

Exact source commit: `38a34665624b8775bb875274b36191b21c38d97b`.

`src`, `sources-c.c`, `sources-cpp.cpp` and `LICENSE` are unchanged upstream files. The existing LLVM MinGW 20261020 UCRT x86_64 toolchain produced the DLL in `source/tools/CascLib.dll` (SHA-256 `5641c4f30cb4367127a97dc6b00dda6bc906064323f3e3df5829872b2a829947`). The compilation used the following arguments, from this directory:

```powershell
& '<LLVM-MinGW>\bin\clang.exe' -O2 -D__CASCLIB_SELF__ -DCASCLIB_NO_AUTO_LINK_LIBRARY -DCASCLIB_NODEBUG -DUNICODE -D_UNICODE -c sources-c.c -o r23-c.o
& '<LLVM-MinGW>\bin\clang++.exe' -O2 -shared -static -D__CASCLIB_SELF__ -DCASCLIB_NO_AUTO_LINK_LIBRARY -DCASCLIB_NODEBUG -DUNICODE -D_UNICODE sources-cpp.cpp src/DllMain.c src/DllMain.def r23-c.o -lwininet -lws2_32 -ladvapi32 -o CascLib-r23.dll
```

The output was copied byte-for-byte to `tools/CascLib.dll`. A future rebuild may require updating the paired hash after inspecting its compiler and artifact; the reader refuses an unrecognized library. The normal trainer build uses the supplied, verified DLL and needs no CascLib download or global installation.

The reader uses local CascOpenStorage only, without online/download feature flags. Private official map extracts and runtime investigation records are not included in this dependency folder or a release archive.
