# hivestack — backup/restore the platform (data + config) to a dated zip.
#   backup:  python scripts/backup.py --data ./runtime/data --config ./runtime/config --out ./backups
#   restore: python scripts/backup.py --restore ./backups/hivestack-backup-<ts>.zip --dest ./restore
#   verify:  python scripts/backup.py --verify ./backups/hivestack-backup-<ts>.zip

from __future__ import annotations

import argparse
import datetime as _dt
import json
import sys
import zipfile
from pathlib import Path

# Guard against cp1252 stdout on Windows so the "→" in restore logs never crashes.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def archive(data: Path, config: Path, out: Path) -> Path:
    data = data.expanduser().resolve()
    out.mkdir(parents=True, exist_ok=True)
    stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = out / f"hivestack-backup-{stamp}.zip"
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
        if data.is_dir():
            for f in sorted(data.rglob("*")):
                if f.is_file():
                    z.write(f, f"data/{f.relative_to(data)}")
        cfg = config / "config.yaml"
        if cfg.exists():
            z.write(cfg, "config.yaml")
        meta = {"created": stamp, "data_dir": str(data), "tool": "hivestack-backup"}
        z.writestr("META.json", json.dumps(meta, indent=2))
    return dest


def restore(archive: Path, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as z:
        for member in z.namelist():
            if member.startswith("data/"):
                target = dest / Path(member)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(z.read(member))
        if "config.yaml" in z.namelist():
            cfg = dest / "config.yaml"
            cfg.parent.mkdir(parents=True, exist_ok=True)
            cfg.write_bytes(z.read("config.yaml"))


def verify(archive: Path) -> dict:
    with zipfile.ZipFile(archive) as z:
        names = z.namelist()
        meta = json.loads(z.read("META.json")) if "META.json" in names else {}
    has_data = any(n.startswith("data/") for n in names)
    has_cfg = "config.yaml" in names
    return {"archive": str(archive), "entries": len(names), "has_config": has_cfg,
            "has_data": has_data, "meta": meta}


def main() -> int:
    ap = argparse.ArgumentParser(description="hivestack backup / restore / verify")
    ap.add_argument("--data", default=None, help="data dir (e.g. /data or ./runtime/data)")
    ap.add_argument("--config", default=None, help="config dir (e.g. /config or ./runtime/config)")
    ap.add_argument("--out", default="backups", help="backup output dir")
    ap.add_argument("--restore", default=None, help="archive to restore")
    ap.add_argument("--dest", default=None, help="destination dir for restore")
    ap.add_argument("--verify", default=None, help="archive to verify")
    args = ap.parse_args()

    if args.verify:
        print(json.dumps(verify(Path(args.verify)), indent=2))
        return 0
    if args.restore:
        if not args.dest:
            print("restore requires --dest")
            return 2
        restore(Path(args.restore), Path(args.dest))
        print(f"restored {args.restore} → {args.dest}")
        return 0
    if not args.data or not args.config:
        ap.print_help()
        return 2
    dest = archive(Path(args.data), Path(args.config), Path(args.out))
    print(f"backup written: {dest} ({dest.stat().st_size} bytes)")
    print(json.dumps(verify(dest), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())