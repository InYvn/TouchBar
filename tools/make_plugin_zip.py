#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把插件代码打成 touchbar-plugin-<ver>.zip。

产物结构（解压后）：
    plugin.json
    touchbar_plugin/__init__.py
    touchbar_plugin/bar.py        <- src/touchbar.py
"""
import argparse
import hashlib
import json
import os
import shutil
import tempfile
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
PLUGIN = os.path.join(ROOT, "plugin")
OUT_DIR = os.path.join(ROOT, "dist-pyi")

FILES = {
    "__init__.py": os.path.join(PLUGIN, "__init__.py"),
    "bar.py": os.path.join(SRC, "touchbar.py"),
}


def build(version, min_host=None, out_dir=OUT_DIR):
    with open(os.path.join(PLUGIN, "plugin.json"), encoding="utf-8") as f:
        meta = json.load(f)
    meta["version"] = version
    if min_host:
        meta["min_host"] = min_host

    tmp = tempfile.mkdtemp(prefix="tb-plugin-")
    try:
        pkg = os.path.join(tmp, "touchbar_plugin")
        os.makedirs(pkg)
        for name, path in FILES.items():
            shutil.copy2(path, os.path.join(pkg, name))
        with open(os.path.join(tmp, "plugin.json"), "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)

        os.makedirs(out_dir, exist_ok=True)
        name = "touchbar-plugin-%s.zip" % version
        dest = os.path.join(out_dir, name)
        with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
            for rel in ["plugin.json"] + ["touchbar_plugin/" + n for n in FILES]:
                info = zipfile.ZipInfo(rel, date_time=(2026, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o644 << 16
                z.writestr(info, open(os.path.join(tmp, rel), "rb").read())
        data = open(dest, "rb").read()
        return dest, hashlib.sha256(data).hexdigest(), len(data)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", default="0.1.0")
    ap.add_argument("--min-host", default=None)
    args = ap.parse_args()
    dest, digest, size = build(args.version, args.min_host)
    print("SHA256  %s  %s" % (digest, os.path.basename(dest)))
    print("Bytes: %d" % size)


if __name__ == "__main__":
    main()
