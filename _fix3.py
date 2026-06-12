"""Fix log.py B608 and remaining Ruff issues."""
from pathlib import Path

ROOT = Path(r"C:\Users\Chris4K\Projekte\HearthNet")

# events/log.py - B608: restructure so nosec is on the correct line
p = ROOT / "hearthnet/events/log.py"
text = p.read_text(encoding="utf-8")

old_block = (
    '            placeholders = ",".join("?" for _ in event_types)\n'
    '            sql = (\n'
    '                # nosec B608 \u2014 placeholders is computed from len(event_types), not user input\n'
    '                f"SELECT event_id,event_type,community_id,author,lamport,payload,issued_at,signature,schema_version,received_at "\n'
    '                f"FROM events WHERE community_id = ? AND lamport >= ? AND event_type IN ({placeholders}) "\n'
    '                f"ORDER BY lamport ASC, event_id ASC"\n'
    '            )'
)
# Check with the garbled encoding that's in the file
old_block2 = None
if old_block not in text:
    # Try finding by key parts
    idx = text.find('            placeholders = ",".join("?" for _ in event_types)')
    if idx >= 0:
        end = text.find('            )', idx) + len('            )')
        old_block2 = text[idx:end]
        print("Found block via idx:", repr(old_block2[:80]))

new_block = (
    '            # placeholders contains only "?" characters (len = len(event_types)) — not user input\n'
    '            placeholders = ",".join("?" for _ in event_types)\n'
    '            sql = (  # nosec B608\n'
    '                "SELECT event_id,event_type,community_id,author,lamport,payload,issued_at,signature,schema_version,received_at "\n'
    '                "FROM events WHERE community_id = ? AND lamport >= ? "\n'
    '                f"AND event_type IN ({placeholders}) "  # nosec B608\n'
    '                "ORDER BY lamport ASC, event_id ASC"\n'
    '            )'
)

if old_block in text:
    text = text.replace(old_block, new_block, 1)
    p.write_text(text, encoding="utf-8")
    print("log.py B608 patched (exact match)")
elif old_block2:
    text = text.replace(old_block2, new_block, 1)
    p.write_text(text, encoding="utf-8")
    print("log.py B608 patched (idx match)")
else:
    print("WARNING: log.py B608 block not found")
    # Show the area around the nosec comment
    idx = text.find("nosec B608")
    if idx >= 0:
        print("Current area:", repr(text[idx-200:idx+200]))

# services/speech/backends/whisper_local.py - PERF401 (extend)
p2 = ROOT / "hearthnet/services/speech/backends/whisper_local.py"
text2 = p2.read_text(encoding="utf-8")
# Replace for-loop with append inside it (lines 130-140 area)
old_segs1 = (
    "                for seg in segs:\n"
    "                    segments_out.append(\n"
    "                        SttSegment(\n"
    "                            start_seconds=seg.start,\n"
    "                            end_seconds=seg.end,\n"
    "                            text=seg.text.strip(),\n"
    "                            language=detected,\n"
    "                            confidence=None,\n"
    "                        )\n"
    "                    )"
)
new_segs1 = (
    "                segments_out.extend(\n"
    "                    SttSegment(\n"
    "                        start_seconds=seg.start,\n"
    "                        end_seconds=seg.end,\n"
    "                        text=seg.text.strip(),\n"
    "                        language=detected,\n"
    "                        confidence=None,\n"
    "                    )\n"
    "                    for seg in segs\n"
    "                )"
)
if old_segs1 in text2:
    text2 = text2.replace(old_segs1, new_segs1, 1)
    print("whisper_local.py PERF401 fix 1 applied")
else:
    print("WARNING: whisper_local.py PERF401 pattern 1 not found")

# Find openai-whisper segments loop (the second PERF401)
old_segs2 = (
    "                for seg in result.get(\"segments\", []):\n"
    "                    segments_out.append(\n"
    "                        SttSegment(\n"
    "                            start_seconds=float(seg[\"start\"]),\n"
    "                            end_seconds=float(seg[\"end\"]),\n"
    "                            text=str(seg[\"text\"]).strip(),\n"
    "                            language=detected,\n"
    "                            confidence=None,\n"
    "                        )\n"
    "                    )"
)
new_segs2 = (
    "                segments_out.extend(\n"
    "                    SttSegment(\n"
    "                        start_seconds=float(seg[\"start\"]),\n"
    "                        end_seconds=float(seg[\"end\"]),\n"
    "                        text=str(seg[\"text\"]).strip(),\n"
    "                        language=detected,\n"
    "                        confidence=None,\n"
    "                    )\n"
    "                    for seg in result.get(\"segments\", [])\n"
    "                )"
)
if old_segs2 in text2:
    text2 = text2.replace(old_segs2, new_segs2, 1)
    print("whisper_local.py PERF401 fix 2 applied")
else:
    print("WARNING: whisper_local.py PERF401 pattern 2 not found")

p2.write_text(text2, encoding="utf-8")

# ui/tabs/ask.py - PERF401 (line 171 - need to find it)
p3 = ROOT / "hearthnet/ui/tabs/ask.py"
text3 = p3.read_text(encoding="utf-8")
for i, line in enumerate(text3.splitlines(), 1):
    if i in range(168, 180):
        print(f"ask.py {i}: {repr(line)}")

# ui/tabs/settings.py - PERF401 (line 391 - need to find it)
p4 = ROOT / "hearthnet/ui/tabs/settings.py"
text4 = p4.read_text(encoding="utf-8")
for i, line in enumerate(text4.splitlines(), 1):
    if i in range(386, 400):
        print(f"settings.py {i}: {repr(line)}")

print("\nDone.")
