#!/usr/bin/env python3
"""Fix UTF-8 curly quotes in node.py that cause SyntaxError."""
import pathlib

p = pathlib.Path("hearthnet/node.py")
data = p.read_bytes()

replacements = [
    (b"\xe2\x80\x9c", b'"'),   # U+201C left double quotation mark
    (b"\xe2\x80\x9d", b'"'),   # U+201D right double quotation mark
    (b"\xe2\x80\x98", b"'"),   # U+2018 left single quotation mark
    (b"\xe2\x80\x99", b"'"),   # U+2019 right single quotation mark
    (b"\xe2\x80\x93", b"-"),   # U+2013 en dash
    (b"\xe2\x80\x94", b"--"),  # U+2014 em dash
]

total = 0
for bad, good in replacements:
    count = data.count(bad)
    if count:
        print(f"Replacing {count}x {bad!r} -> {good!r}")
        total += count
        data = data.replace(bad, good)

p.write_bytes(data)
print(f"Done. Fixed {total} occurrences.")
