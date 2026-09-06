"""List the DLLs a Windows binary imports, by walking its PE import directory.

Used to check what the packaged add-on actually depends on at run time, which
is not obvious from the source: ONNX Runtime is statically linked, and the
prebuilt runtime brings imports of its own. `dumpbin` is not present on a
machine with only the Rust toolchain, hence this.

    python tools/pe_imports.py addon/synthDrivers/piper/bin/piper-helper.exe

Anything listed that is not an `api-ms-win-*` apiset, a core Windows DLL, or a
file the add-on ships is a dependency the user must already have.
"""

import struct
import sys


def imports(path):
    with open(path, "rb") as f:
        data = f.read()

    e_lfanew = struct.unpack_from("<I", data, 0x3C)[0]
    assert data[e_lfanew:e_lfanew + 4] == b"PE\0\0", "not a PE file"
    coff = e_lfanew + 4
    machine, num_sections = struct.unpack_from("<HH", data, coff)
    opt_size = struct.unpack_from("<H", data, coff + 16)[0]
    opt = coff + 20
    magic = struct.unpack_from("<H", data, opt)[0]
    pe32_plus = magic == 0x20B
    # Data directories start after the standard + windows-specific fields.
    dd = opt + (112 if pe32_plus else 96)
    import_rva, _import_size = struct.unpack_from("<II", data, dd + 8)

    sections = []
    sec = opt + opt_size
    for i in range(num_sections):
        off = sec + i * 40
        name = data[off:off + 8].rstrip(b"\0").decode("ascii", "replace")
        vsize, vaddr, rawsize, rawptr = struct.unpack_from("<IIII", data, off + 8)
        sections.append((name, vaddr, vsize, rawptr, rawsize))

    def to_offset(rva):
        for _name, vaddr, vsize, rawptr, rawsize in sections:
            if vaddr <= rva < vaddr + max(vsize, rawsize):
                return rawptr + (rva - vaddr)
        return None

    names = []
    if import_rva:
        entry = to_offset(import_rva)
        while entry is not None:
            fields = struct.unpack_from("<IIIII", data, entry)
            if not any(fields):
                break
            name_off = to_offset(fields[3])
            if name_off is None:
                break
            end = data.index(b"\0", name_off)
            names.append(data[name_off:end].decode("ascii", "replace"))
            entry += 20

    arch = {0x8664: "x64", 0x14C: "x86", 0xAA64: "arm64"}.get(machine, hex(machine))
    return arch, sorted(names, key=str.lower)


for path in sys.argv[1:]:
    arch, names = imports(path)
    print("%s  [%s]" % (path, arch))
    for name in names:
        print("   ", name)
    print()
