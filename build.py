#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Assemble the Fe library with its native adapter, then invoke pinned Fe."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import time

ROOT = Path(__file__).resolve().parent
PIN = "3732fbe8a6e9d2ea3925d02d0e3a1478bc1e01d742c2be75d3ea7300c46c45f0"
DEFAULT = os.environ.get("FE") or shutil.which("fe")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=["build", "test", "check"], nargs="?", default="build")
    ap.add_argument("--compiler", default=DEFAULT)
    args = ap.parse_args()
    if not args.compiler:
        ap.error("Supply --compiler /path/to/fe_linux_amd64, set FE, or put pinned fe on PATH")
    compiler = Path(args.compiler).resolve()
    digest = hashlib.sha256(compiler.read_bytes()).hexdigest()
    if digest != PIN:
        raise SystemExit("Compiler SHA256 differs from pinned Fe26.5.0 x86_64 Linux asset")
    build = ROOT / "build"
    build.mkdir(exist_ok=True)
    source = ROOT / "src/lib.fe"
    if args.action == "check":
        generated = source
        command = [str(compiler), "check", str(ROOT)]
    else:
        tail = ROOT / ("cli/main.fe" if args.action == "build" else "tests/native.fe")
        generated = build / ("ferecords.fe" if args.action == "build" else "native-tests.fe")
        generated.write_bytes(source.read_bytes() + b"\n" + tail.read_bytes())
    if args.action == "build":
        command = [str(compiler), "build", str(generated), "--standalone", "--backend", "native", "--out-dir", str(build / "bin")]
    elif args.action == "test":
        command = [str(compiler), "test", str(generated), "--backend", "native", "--jobs", "1", "--native-timeout-secs", "20", "--native-output-limit-kib", "64"]
    start = time.monotonic()
    run_id = str(time.time_ns())
    result = subprocess.run(command, cwd=ROOT, timeout=120, capture_output=True)
    log = result.stdout + result.stderr
    (build / (args.action + ".log")).write_bytes(log)
    print(log.decode("utf-8", errors="replace"), end="")
    receipt = {"action": args.action, "compiler_sha256": digest, "argv": command,
               "source_sha256": hashlib.sha256(generated.read_bytes()).hexdigest(),
               "returncode": result.returncode, "wall_seconds": time.monotonic() - start,
               "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    (build / (args.action + "-receipt.json")).write_text(json.dumps(receipt, indent=2) + "\n")
    archive = build / "runs" / run_id
    archive.mkdir(parents=True)
    (archive / "source.fe").write_bytes(generated.read_bytes())
    (archive / "output.log").write_bytes(log)
    (archive / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    raise SystemExit(result.returncode)

if __name__ == "__main__":
    main()
