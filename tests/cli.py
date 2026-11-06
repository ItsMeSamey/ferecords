#!/usr/bin/env python3
"""Hand-authored native CLI examples; no candidate CSV parser in this harness."""
# SPDX-License-Identifier: Apache-2.0
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile


def run(binary, args, data):
    return subprocess.run([str(binary), *args], input=data, capture_output=True,
                          timeout=10, check=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("binary", type=Path, nargs="?",
                        default=Path(__file__).resolve().parents[1] / "build/bin/ferecords")
    options = parser.parse_args()
    binary = options.binary.resolve()
    cases = [
        ("standalone help", ["--help"], b"", 0,
         b"FeRecords: strict CRLF CSV bytes (NUL rejected).\n"
         b"Usage:\n"
         b"  ferecords validate [WIDTH]\n"
         b"  ferecords select COLUMN...\n"
         b"  ferecords inspect [CHUNK [FIELD_LIMIT RAW_LIMIT FIELDS_LIMIT]]\n"
         b"Columns are zero-based; duplicates and order are preserved.\n"
         b"Reads stdin. validate is silent; select writes CSV; inspect writes diagnostics.\n"
         b"Defaults: field 16384 bytes, raw record 65536 bytes, 256 fields, chunk 4096 bytes.\n"
         b"Caps: raw record 1048576 bytes, fields 256, chunk 4096. Positive limits only.\n"
         b"Field limit cannot exceed raw limit. WIDTH is 1..256; select takes 1..256 columns.\n"
         b"Exit: 0 success; 64 arguments; 5 NUL; 6 bare CR; 7 bare LF; 8 misplaced quote;\n"
         b"9 after quote; 10 unclosed quote; 11 field limit; 12 raw limit; 13 field count;\n"
         b"14 counter overflow; 15 allocation; 16 output; 17 width; 18 missing column.\n"
         b"Library codes: 2 configuration; 3 range; 4 finished; 19 zero-field record.\n"
         b"Use inspect for error code and zero-based byte, row and field positions.\n"
         b"20 input failure. Read errors are distinct from EOF.\n"
         b"Earlier rows may be output before failure. Output is flushed and closed;\n"
         b"the first error is preserved. Broken pipes may terminate via SIGPIPE.\n"
         b"Successful output is not a filesystem durability guarantee.\n"),
        ("empty validation", ["validate"], b"", 0, b""),
        ("empty fixed-width stream", ["validate", "2"], b"", 0, b""),
        ("three fields", ["validate", "3"], b"a,b,c\r\n", 0, b""),
        ("empty fields", ["validate", "3"], b",,", 0, b""),
        ("multiline", ["validate", "2"], b'"a\r\nb",c\r\n', 0, b""),
        ("non-UTF8 bytes", ["validate"], b'\xff,\x80\r\n', 0, b""),
        ("width rejection", ["validate", "2"], b"a\r\n", 17, b""),
        ("bare LF rejection", ["validate"], b"a\n", 7, b""),
        ("bare CR rejection", ["validate"], b"a\r", 6, b""),
        ("NUL rejection", ["validate"], b"a\x00b", 5, b""),
        ("quote rejection", ["validate"], b'a"b', 8, b""),
        ("after-quote rejection", ["validate"], b'"a"b', 9, b""),
        ("unclosed quote rejection", ["validate"], b'"a', 10, b""),
        ("ordered duplicate columns", ["select", "1", "0", "1"],
         b'id,name\r\n1,"Ada, A"\r\n', 0,
         b'"name","id","name"\r\n"Ada, A","1","Ada, A"\r\n'),
        ("quote escaping", ["select", "0"], b'"a""b"', 0, b'"a""b"\r\n'),
        ("preserved CRLF field", ["select", "0"], b'"a\r\nb",x', 0,
         b'"a\r\nb"\r\n'),
        ("preserved non-UTF8", ["select", "1", "0"], b'\xff,\x80', 0,
         b'"\x80","\xff"\r\n'),
        ("empty selected field", ["select", "1"], b"a,", 0, b'""\r\n'),
        ("missing first row", ["select", "1"], b"a\r\n", 18, b""),
        ("missing later row keeps prior", ["select", "1", "1"], b"a,b\r\nc\r\n", 18,
         b'"b","b"\r\n'),
        ("syntax later row keeps prior", ["select", "0"], b"a\r\nb\n", 7, b'"a"\r\n'),
        ("u64 maximum missing column", ["select", "18446744073709551615"], b"a", 18, b""),
        ("empty projection stream", ["select", "99"], b"", 0, b""),
    ]
    invalid_args = [[], ["unknown"], ["validate", "0"], ["validate", "257"],
                    ["validate", "2", "3"], ["validate", ""], ["validate", "+1"],
                    ["validate", " 1"], ["select"], ["select", "-1"],
                    ["select", "18446744073709551616"], ["select", "1.0"],
                    ["inspect", "0"], ["inspect", "4097"], ["inspect", "1", "1"],
                    ["inspect", "1", "0", "2", "1"],
                    ["inspect", "1", "2", "1", "1"],
                    ["inspect", "1", "1", "1048577", "1"],
                    ["inspect", "1", "1", "2", "257"],
                    ["select", *(["0"] * 257)]]
    cases.extend((f"invalid args {i}", args, b"", 64, b"")
                 for i, args in enumerate(invalid_args))
    failures = []
    for name, args, data, code, output in cases:
        actual = run(binary, args, data)
        if (actual.returncode, actual.stdout, actual.stderr) != (code, output, b""):
            failures.append({"name": name, "args": args,
                             "expected": [code, output.hex(), ""],
                             "actual": [actual.returncode, actual.stdout.hex(), actual.stderr.hex()]})
    chunk_cases = [b"", b",,", b'a,b\r\n"c\r\nd","e""f"\r\n',
                   b'\xff,\x80\r\n', b'a\r\nx\n', b'"unterminated', b'a\r']
    comparisons = 0
    for data in chunk_cases:
        reference = run(binary, ["inspect", "4096"], data)
        for chunk in (1, 2, 3, 7, 31):
            actual = run(binary, ["inspect", str(chunk)], data)
            comparisons += 1
            # Only allocated input capacity varies with requested chunk size.
            actual_lines = actual.stdout.splitlines()
            reference_lines = reference.stdout.splitlines()
            expected_capacity = max(32, 1 << (chunk - 1).bit_length())
            stats_valid = bool(actual_lines and reference_lines)
            if stats_valid:
                actual_stats = actual_lines[-1].split()
                reference_stats = reference_lines[-1].split()
                stats_valid = (len(actual_stats) == len(reference_stats) == 6
                               and actual_stats[0] == reference_stats[0] == b"S"
                               and actual_stats[-1:] == [str(expected_capacity).encode()]
                               and reference_stats[-1:] == [b"4096"])
                actual_lines[-1] = b" ".join(actual_stats[:-1])
                reference_lines[-1] = b" ".join(reference_stats[:-1])
            if not stats_valid or (actual.returncode, actual_lines, actual.stderr) != (
                    reference.returncode, reference_lines, reference.stderr):
                failures.append({"name": "inspect chunk equality", "input_hex": data.hex(),
                                 "chunk": chunk, "actual": actual.stdout.hex(),
                                 "reference": reference.stdout.hex()})
    io_results = []

    def check_io(name, actual, code, output=None):
        passed = (actual.returncode == code and actual.stderr == b""
                  and (output is None or actual.stdout == output))
        io_results.append({"name": name, "expected_code": code,
                           "actual_code": actual.returncode, "passed": passed})
        if not passed:
            failures.append({"name": name, "expected_code": code,
                             "actual_code": actual.returncode,
                             "stdout_hex": (actual.stdout or b"").hex(),
                             "stderr_hex": actual.stderr.hex()})

    # A directory is readable as an fd, but fgetc reports a genuine source error.
    with tempfile.TemporaryDirectory(prefix="ferecords-io-") as directory:
        for args, expected in [(["validate"], b""), (["select", "0"], b""),
                               (["inspect"], b"E 20 0 0 0\nS 0 0 0 2048 4096\n")]:
            fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
            try:
                actual = subprocess.run([str(binary), *args], stdin=fd,
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                        timeout=10, check=False)
            finally:
                os.close(fd)
            check_io("directory stdin " + args[0], actual, 20, expected)

    # Small writes fit libc buffering, so /dev/full fails at flush, not fputc.
    full_cases = [
        ("delayed output failure", ["select", "0"], b"a\r\n", 16),
        ("help flush failure", ["--help"], b"", 16),
        ("inspect flush failure", ["inspect"], b"a\r\n", 16),
        ("earlier syntax error survives flush failure", ["select", "0"],
         b'a,b\r\n"unterminated', 10),
        ("earlier missing column survives flush failure", ["select", "1"],
         b"a,b\r\nc\r\n", 18),
        ("large output failure", ["select", "0"], b"x" * 9000 + b"\r\n", 16),
    ]
    for name, args, data, code in full_cases:
        with open("/dev/full", "wb", buffering=0) as output:
            actual = subprocess.run([str(binary), *args], input=data, stdout=output,
                                    stderr=subprocess.PIPE, timeout=10, check=False)
        check_io(name, actual, code)

    for args, expected in [(["validate"], 0), (["select", "0"], 16)]:
        fd = os.open("/dev/null", os.O_RDONLY)
        try:
            actual = subprocess.run([str(binary), *args], input=b"a\r\n", stdout=fd,
                                    stderr=subprocess.PIPE, timeout=10, check=False)
        finally:
            os.close(fd)
        check_io("read-only stdout " + args[0], actual, expected)
    fd = os.open("/dev/null", os.O_WRONLY)
    try:
        actual = subprocess.run([str(binary), "validate"], stdin=fd, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, timeout=10, check=False)
    finally:
        os.close(fd)
    check_io("write-only stdin", actual, 20, b"")

    # Each close runs only in this short-lived child after subprocess duplicates its fds.
    for args, expected in [(["validate"], 0), (["select", "0"], 16)]:
        actual = subprocess.run([str(binary), *args], input=b"a\r\n",
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                preexec_fn=lambda: os.close(1), timeout=10, check=False)
        check_io("closed stdout " + args[0], actual, expected, b"")
    actual = subprocess.run([str(binary), "validate"], input=b"a\r\n",
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            preexec_fn=lambda: os.close(0), timeout=10, check=False)
    check_io("closed stdin", actual, 20, b"")

    report = {"explicit_cases": len(cases), "chunk_comparisons": comparisons,
              "native_io_cases": len(io_results), "native_io_results": io_results,
              "passed": not failures, "failures": failures}
    print(json.dumps(report, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
