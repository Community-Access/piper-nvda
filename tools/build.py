"""Build the Piper .nvda-addon package.

Steps: cargo build --release (unless --skip-cargo); stage the addon tree;
copy the helper exe, the Visual C++ runtime, and espeak-ng into
synthDrivers/piper/bin; render
the readme; zip into dist/piper-neural-<version>.nvda-addon. Voices are not
bundled; they download at runtime.

Usage: python tools/build.py [--skip-cargo]
"""

import configparser
import glob
import os
import shutil
import subprocess
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import i18n  # noqa: E402  (same directory)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ADDON = os.path.join(ROOT, "addon")
HELPER_DIR = os.path.join(ROOT, "helper")
RELEASE = os.path.join(HELPER_DIR, "target", "release")
ASSETS = os.path.join(ROOT, "assets")
BUILD = os.path.join(ROOT, "build", "addon")
DIST = os.path.join(ROOT, "dist")


def read_version():
    cp = configparser.ConfigParser()
    with open(os.path.join(ADDON, "manifest.ini"), encoding="utf-8") as f:
        cp.read_string("[m]\n" + f.read())
    return cp["m"]["version"].strip().strip('"')


def cargo_build():
    print("cargo build --release ...")
    subprocess.check_call(["cargo", "build", "--release"], cwd=HELPER_DIR)


def _copy(src, dst):
    if not os.path.isfile(src):
        raise SystemExit("missing build input: %s" % src)
    shutil.copy2(src, dst)


#: The Visual C++ runtime the helper and espeak-ng link against. These are not
#: part of Windows; without them the helper cannot start on a machine that has
#: never had the Visual C++ redistributable installed. Shipping them beside the
#: executable removes that prerequisite, which Microsoft's redistribution terms
#: allow. The executable's directory is searched first for both it and the
#: espeak DLL it loads, so one copy here covers both.
CRT_DLLS = ("msvcp140.dll", "msvcp140_1.dll",
            "vcruntime140.dll", "vcruntime140_1.dll")


def find_crt_dir():
    """The newest x64 VC redistributable directory holding every CRT DLL.

    `PIPER_CRT_DIR` overrides the search, for build machines that keep the
    redistributable somewhere else.
    """
    override = os.environ.get("PIPER_CRT_DIR")
    if override:
        return override if _has_crt(override) else None
    patterns = []
    for root in (os.environ.get("ProgramFiles(x86)"),
                 os.environ.get("ProgramFiles")):
        if root:
            patterns.append(os.path.join(
                root, "Microsoft Visual Studio", "*", "*", "VC", "Redist",
                "MSVC", "*", "x64", "Microsoft.VC*.CRT"))
    candidates = [d for pattern in patterns for d in glob.glob(pattern)
                  if _has_crt(d)]
    if not candidates:
        return None
    # Directory names carry the toolset version, so the last one sorts newest.
    return sorted(candidates)[-1]


def _has_crt(directory):
    return all(os.path.isfile(os.path.join(directory, name))
               for name in CRT_DLLS)


def copy_crt(bin_dir):
    source = find_crt_dir()
    if source is None:
        raise SystemExit(
            "Visual C++ runtime not found. Install the Visual Studio Build "
            "Tools with the C++ workload, or set PIPER_CRT_DIR to a directory "
            "containing: " + ", ".join(CRT_DLLS))
    for name in CRT_DLLS:
        _copy(os.path.join(source, name), os.path.join(bin_dir, name))
    print("bundled the Visual C++ runtime from %s" % source)


def stage():
    if os.path.exists(BUILD):
        shutil.rmtree(BUILD)
    # .po/.pot are translator sources; only the compiled .mo files ship.
    shutil.copytree(ADDON, BUILD,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc",
                                                  "_data", "*.po", "*.pot"))
    compiled = i18n.compile_locales(os.path.join(ADDON, "locale"),
                                    os.path.join(BUILD, "locale"))
    print("compiled %d translations" % len(compiled))
    bin_dir = os.path.join(BUILD, "synthDrivers", "piper", "bin")
    os.makedirs(bin_dir, exist_ok=True)
    _copy(os.path.join(RELEASE, "piper-helper.exe"),
          os.path.join(bin_dir, "piper-helper.exe"))
    copy_crt(bin_dir)
    for dll in ("onnxruntime.dll",):
        src = os.path.join(RELEASE, dll)
        if os.path.isfile(src):
            _copy(src, os.path.join(bin_dir, dll))
    espeak_src = os.path.join(ASSETS, "espeak-ng", "eSpeak NG")
    espeak_dst = os.path.join(bin_dir, "espeak-ng")
    os.makedirs(espeak_dst, exist_ok=True)
    _copy(os.path.join(espeak_src, "libespeak-ng.dll"),
          os.path.join(espeak_dst, "libespeak-ng.dll"))
    data_dst = os.path.join(espeak_dst, "espeak-ng-data")
    if os.path.exists(data_dst):
        shutil.rmtree(data_dst)
    shutil.copytree(os.path.join(espeak_src, "espeak-ng-data"), data_dst)


def make_readme():
    md_path = os.path.join(ADDON, "doc", "en", "readme.md")
    out_dir = os.path.join(BUILD, "doc", "en")
    os.makedirs(out_dir, exist_ok=True)
    body = _md(open(md_path, encoding="utf-8").read()) if os.path.isfile(md_path) else ""
    with open(os.path.join(out_dir, "readme.html"), "w", encoding="utf-8") as f:
        f.write("<!DOCTYPE html><html lang='en'><head><meta charset='utf-8'>"
                "<title>Piper Neural Voices</title></head><body>\n"
                + body + "\n</body></html>")


def _md(md):
    import html as _h
    out, para, in_list = [], [], False

    def flush():
        if para:
            out.append("<p>" + " ".join(para) + "</p>")
            para.clear()

    def close():
        nonlocal in_list
        if in_list:
            out.append("</ul>")
            in_list = False

    for raw in md.splitlines():
        line = raw.rstrip()
        if not line:
            flush(); close(); continue
        s = line.lstrip()
        if s.startswith("#"):
            flush(); close()
            lvl = len(s) - len(s.lstrip("#"))
            out.append("<h%d>%s</h%d>" % (min(lvl, 6),
                       _h.escape(s[lvl:].strip()), min(lvl, 6)))
        elif s[:2] in ("- ", "* "):
            flush()
            if not in_list:
                out.append("<ul>"); in_list = True
            out.append("<li>" + _h.escape(s[2:]) + "</li>")
        else:
            close(); para.append(_h.escape(s))
    flush(); close()
    return "\n".join(out)


def zip_addon(version):
    os.makedirs(DIST, exist_ok=True)
    out = os.path.join(DIST, "piper-neural-%s.nvda-addon" % version)
    if os.path.exists(out):
        os.remove(out)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for base, _d, files in os.walk(BUILD):
            for name in files:
                full = os.path.join(base, name)
                z.write(full, os.path.relpath(full, BUILD).replace(os.sep, "/"))
    print("wrote %s (%.1f MB)" % (out, os.path.getsize(out) / (1024 * 1024)))


def main():
    if "--skip-cargo" not in sys.argv:
        cargo_build()
    version = read_version()
    stage()
    make_readme()
    zip_addon(version)


if __name__ == "__main__":
    main()
