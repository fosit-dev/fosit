"""Pack core/fosit into public/fosit-core.zip for the browser, reproducibly.

Fixed timestamps and sorted entries mean the same source always gives the same
bytes, so the SHA-256 written to public/fosit-core.json (and into every locked
plan as tool.core_sha256) identifies exactly which statistical code ran.
"""

import hashlib
import json
import os
import shutil
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.normpath(os.path.join(HERE, "..", "..", "core"))
OUT = os.path.normpath(os.path.join(HERE, "..", "public"))
FIXED_TIME = (1980, 1, 1, 0, 0, 0)


def files():
    for root, dirs, names in os.walk(os.path.join(CORE, "fosit")):
        dirs[:] = sorted(d for d in dirs if d != "__pycache__")
        for name in sorted(names):
            if name.endswith((".py", ".csv", ".json", ".md")):
                path = os.path.join(root, name)
                yield path, os.path.relpath(path, CORE).replace(os.sep, "/")


def main():
    os.makedirs(OUT, exist_ok=True)
    zip_path = os.path.join(OUT, "fosit-core.zip")
    listed = []
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for path, arc in sorted(files(), key=lambda pa: pa[1]):
            info = zipfile.ZipInfo(arc, FIXED_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            with open(path, "rb") as f:
                z.writestr(info, f.read())
            listed.append(arc)
    with open(zip_path, "rb") as f:
        digest = hashlib.sha256(f.read()).hexdigest()
    namespace = {}
    with open(os.path.join(CORE, "fosit", "__init__.py")) as f:
        exec(f.read(), namespace)
    with open(os.path.join(CORE, "fosit", "geo_data", "SOURCES.json")) as f:
        geo = json.load(f)["outputs"]
    manifest = {"version": namespace["__version__"], "sha256": digest, "files": listed,
                "geo_mapping_sha256": geo["zcta_to_geo.csv"]["sha256"]}
    with open(os.path.join(OUT, "fosit-core.json"), "w") as f:
        json.dump(manifest, f, indent=2)
    print(f"fosit-core.zip {digest} ({len(listed)} files)")

    # The Read module's "Try it with the example" loads these from the app's own origin.
    src = os.path.normpath(os.path.join(HERE, "..", "..", "examples", "two_vendor"))
    dst = os.path.join(OUT, "examples", "two_vendor")
    os.makedirs(dst, exist_ok=True)
    for name in ("plan.fosit-plan.json", "kpi_history.csv", "spend_delivery.csv"):
        shutil.copyfile(os.path.join(src, name), os.path.join(dst, name))
    print("copied examples/two_vendor into public/examples")


if __name__ == "__main__":
    main()
