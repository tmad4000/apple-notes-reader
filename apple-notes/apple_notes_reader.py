#!/usr/bin/env python3
"""
Apple Notes Reader - Extract and search notes from the Apple Notes SQLite database.

Usage:
    python apple_notes_reader.py list [--limit N]
    python apple_notes_reader.py search "query"
    python apple_notes_reader.py read <note_id>
    python apple_notes_reader.py folders
    python apple_notes_reader.py export [--format json|csv|md] [--hours N] [--days N] [--output PATH]

Examples:
    python apple_notes_reader.py export --format md --hours 24    # Last 24 hours
    python apple_notes_reader.py export --format json --days 7    # Last week
    python apple_notes_reader.py export -o output/notes.json      # Write to file
"""

import argparse
import sqlite3
import gzip
import io
import re
import sys
import os
import json
import csv
from datetime import datetime
from pathlib import Path

# Apple Notes stores dates as seconds since 2001-01-01 (Core Data epoch)
CORE_DATA_EPOCH = 978307200  # Difference between Unix epoch and Core Data epoch

DB_PATH = os.path.expanduser(
    "~/Library/Group Containers/group.com.apple.notes/NoteStore.sqlite"
)


def extract_text_from_protobuf(data: bytes) -> str:
    """
    Extract readable text from Apple Notes protobuf format.
    The protobuf contains embedded strings that we can extract.
    """
    if not data:
        return ""

    try:
        # Decompress gzip data
        decompressed = gzip.decompress(data)
    except Exception:
        decompressed = data

    # Extract text strings from protobuf
    # Apple Notes uses a custom protobuf schema, but text is stored as length-prefixed strings
    text_parts = []
    i = 0

    while i < len(decompressed):
        # Look for string field markers (wire type 2 = length-delimited)
        if i + 2 < len(decompressed):
            byte = decompressed[i]
            wire_type = byte & 0x07

            if wire_type == 2:  # Length-delimited (string, bytes, embedded message)
                i += 1
                # Read varint length
                length = 0
                shift = 0
                while i < len(decompressed):
                    b = decompressed[i]
                    length |= (b & 0x7F) << shift
                    i += 1
                    if not (b & 0x80):
                        break
                    shift += 7

                # Extract the string if it looks like text
                if 0 < length < 10000 and i + length <= len(decompressed):
                    try:
                        candidate = decompressed[i:i + length]
                        # Check if it's valid UTF-8 text
                        text = candidate.decode('utf-8')
                        # Filter for readable content (has letters, not just control chars)
                        if (len(text) > 1 and
                            any(c.isalpha() for c in text) and
                            not text.startswith('\x00')):
                            # Skip UUIDs and technical strings
                            if not re.match(r'^[0-9a-f-]{36}$', text, re.I):
                                text_parts.append(text)
                    except (UnicodeDecodeError, Exception):
                        pass
                    i += length
                    continue
        i += 1

    # Join and clean up the text
    full_text = '\n'.join(text_parts)
    # Remove duplicate lines (protobuf often has repeated data)
    lines = []
    seen = set()
    for line in full_text.split('\n'):
        line = line.strip()
        if line and line not in seen:
            seen.add(line)
            lines.append(line)

    return '\n'.join(lines)


def get_connection():
    """Get a read-only connection to the Notes database."""
    return sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)


def format_date(timestamp):
    """Convert Core Data timestamp to readable date."""
    if timestamp is None:
        return "Unknown"
    try:
        unix_time = timestamp + CORE_DATA_EPOCH
        return datetime.fromtimestamp(unix_time).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return "Unknown"


def list_notes(limit=20):
    """List recent notes."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            o.Z_PK,
            o.ZTITLE1,
            o.ZMODIFICATIONDATE1,
            o.ZCREATIONDATE1,
            o.ZISPINNED,
            folder.ZTITLE2 as folder_name
        FROM ZICCLOUDSYNCINGOBJECT o
        LEFT JOIN ZICCLOUDSYNCINGOBJECT folder ON o.ZFOLDER = folder.Z_PK
        WHERE o.ZTITLE1 IS NOT NULL
          AND o.ZMARKEDFORDELETION != 1
        ORDER BY o.ZMODIFICATIONDATE1 DESC
        LIMIT ?
    """, (limit,))

    notes = cursor.fetchall()
    conn.close()

    print(f"\n{'ID':<8} {'Modified':<18} {'Folder':<20} {'Title'}")
    print("-" * 100)

    for note in notes:
        pk, title, mod_date, create_date, pinned, folder = note
        pin_marker = "📌 " if pinned else ""
        folder_name = folder or "Notes"
        title_display = (title[:50] + "...") if len(title or "") > 50 else (title or "Untitled")
        print(f"{pk:<8} {format_date(mod_date):<18} {folder_name:<20} {pin_marker}{title_display}")


def search_notes(query):
    """Search notes by title and content."""
    conn = get_connection()
    cursor = conn.cursor()

    # First search by title
    cursor.execute("""
        SELECT
            o.Z_PK,
            o.ZTITLE1,
            o.ZMODIFICATIONDATE1,
            n.ZDATA
        FROM ZICCLOUDSYNCINGOBJECT o
        LEFT JOIN ZICNOTEDATA n ON o.ZNOTEDATA = n.Z_PK
        WHERE o.ZTITLE1 IS NOT NULL
          AND o.ZMARKEDFORDELETION != 1
        ORDER BY o.ZMODIFICATIONDATE1 DESC
    """)

    results = []
    query_lower = query.lower()

    for row in cursor.fetchall():
        pk, title, mod_date, data = row
        title_match = query_lower in (title or "").lower()

        # Extract text content
        content = extract_text_from_protobuf(data) if data else ""
        content_match = query_lower in content.lower()

        if title_match or content_match:
            # Find matching snippet
            snippet = ""
            if content_match and content:
                idx = content.lower().find(query_lower)
                start = max(0, idx - 40)
                end = min(len(content), idx + len(query) + 40)
                snippet = "..." + content[start:end].replace('\n', ' ') + "..."

            results.append({
                'id': pk,
                'title': title,
                'date': format_date(mod_date),
                'snippet': snippet,
                'title_match': title_match
            })

    conn.close()

    print(f"\nFound {len(results)} notes matching '{query}':\n")
    print(f"{'ID':<8} {'Modified':<18} {'Title'}")
    print("-" * 80)

    for r in results[:20]:
        title_display = (r['title'][:45] + "...") if len(r['title'] or "") > 45 else (r['title'] or "Untitled")
        match_type = "📌" if r['title_match'] else "  "
        print(f"{r['id']:<8} {r['date']:<18} {match_type} {title_display}")
        if r['snippet']:
            print(f"         {r['snippet'][:70]}")
        print()


def read_note(note_id):
    """Read a specific note by ID."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            o.Z_PK,
            o.ZTITLE1,
            o.ZMODIFICATIONDATE1,
            o.ZCREATIONDATE1,
            folder.ZTITLE2 as folder_name,
            n.ZDATA
        FROM ZICCLOUDSYNCINGOBJECT o
        LEFT JOIN ZICCLOUDSYNCINGOBJECT folder ON o.ZFOLDER = folder.Z_PK
        LEFT JOIN ZICNOTEDATA n ON o.ZNOTEDATA = n.Z_PK
        WHERE o.Z_PK = ?
    """, (note_id,))

    row = cursor.fetchone()
    conn.close()

    if not row:
        print(f"Note {note_id} not found")
        return

    pk, title, mod_date, create_date, folder, data = row
    content = extract_text_from_protobuf(data) if data else "(No content)"

    print(f"\n{'=' * 60}")
    print(f"Title:    {title or 'Untitled'}")
    print(f"Folder:   {folder or 'Notes'}")
    print(f"Created:  {format_date(create_date)}")
    print(f"Modified: {format_date(mod_date)}")
    print(f"{'=' * 60}\n")
    print(content)
    print()


def list_folders():
    """List all folders."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            f.Z_PK,
            f.ZTITLE2,
            COUNT(n.Z_PK) as note_count
        FROM ZICCLOUDSYNCINGOBJECT f
        LEFT JOIN ZICCLOUDSYNCINGOBJECT n ON n.ZFOLDER = f.Z_PK AND n.ZTITLE1 IS NOT NULL
        WHERE f.ZTITLE2 IS NOT NULL
        GROUP BY f.Z_PK
        ORDER BY f.ZTITLE2
    """)

    folders = cursor.fetchall()
    conn.close()

    print(f"\n{'ID':<8} {'Notes':<8} {'Folder Name'}")
    print("-" * 50)

    for folder in folders:
        pk, name, count = folder
        print(f"{pk:<8} {count:<8} {name}")


def get_all_notes(since_hours=None, since_days=None):
    """Get all notes with their content, optionally filtered by recency."""
    conn = get_connection()
    cursor = conn.cursor()

    # Build time filter if specified
    time_filter = ""
    if since_hours is not None:
        # Convert hours to Core Data timestamp (seconds since 2001-01-01)
        import time
        cutoff = time.time() - CORE_DATA_EPOCH - (since_hours * 3600)
        time_filter = f"AND o.ZMODIFICATIONDATE1 >= {cutoff}"
    elif since_days is not None:
        import time
        cutoff = time.time() - CORE_DATA_EPOCH - (since_days * 86400)
        time_filter = f"AND o.ZMODIFICATIONDATE1 >= {cutoff}"

    cursor.execute(f"""
        SELECT
            o.Z_PK,
            o.ZTITLE1,
            o.ZMODIFICATIONDATE1,
            o.ZCREATIONDATE1,
            o.ZISPINNED,
            folder.ZTITLE2 as folder_name,
            n.ZDATA
        FROM ZICCLOUDSYNCINGOBJECT o
        LEFT JOIN ZICCLOUDSYNCINGOBJECT folder ON o.ZFOLDER = folder.Z_PK
        LEFT JOIN ZICNOTEDATA n ON o.ZNOTEDATA = n.Z_PK
        WHERE o.ZTITLE1 IS NOT NULL
          AND o.ZMARKEDFORDELETION != 1
          {time_filter}
        ORDER BY o.ZMODIFICATIONDATE1 DESC
    """)

    notes = []
    for row in cursor.fetchall():
        pk, title, mod_date, create_date, pinned, folder, data = row
        content = extract_text_from_protobuf(data) if data else ""

        notes.append({
            "id": pk,
            "title": title,
            "folder": folder or "Notes",
            "pinned": bool(pinned),
            "created": format_date(create_date),
            "modified": format_date(mod_date),
            "content": content if content else title  # Use title as content for short notes
        })

    conn.close()
    return notes


def export_notes(format_type="json", since_hours=None, since_days=None, output_path=None):
    """Export all notes to JSON, CSV, or Markdown."""
    notes = get_all_notes(since_hours=since_hours, since_days=since_days)

    if format_type == "json":
        output = json.dumps(notes, indent=2, ensure_ascii=False)

    elif format_type == "csv":
        output_buffer = io.StringIO()
        writer = csv.writer(output_buffer)
        writer.writerow([
            "ID", "Title", "Folder", "Pinned", "Created", "Modified", "Content"
        ])

        for note in notes:
            writer.writerow([
                note["id"],
                note["title"],
                note["folder"],
                note["pinned"],
                note["created"],
                note["modified"],
                note["content"]
            ])
        output = output_buffer.getvalue()

    elif format_type in ("md", "markdown"):
        lines = []
        lines.append("# Apple Notes Export")
        lines.append(f"\nExported {len(notes)} notes\n")

        for note in notes:
            lines.append("\n---\n")
            lines.append(f"## {note['title']}")
            lines.append(f"\n**Folder:** {note['folder']} | **Modified:** {note['modified']}")
            if note['pinned']:
                lines.append("**Pinned:** Yes")
            lines.append(f"\n{note['content']}")
        output = "\n".join(lines)
    else:
        output = ""

    # Write to file or stdout
    if output_path:
        # Create parent directories if needed
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            f.write(output)
        print(f"Exported {len(notes)} notes to {output_path}", file=sys.stderr)
    else:
        print(output)


def main():
    parser = argparse.ArgumentParser(
        description="Read, search, and export Apple Notes",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python3 apple_notes_reader.py list
    python3 apple_notes_reader.py search "meeting"
    python3 apple_notes_reader.py read 12345
    python3 apple_notes_reader.py folders
    python3 apple_notes_reader.py export --format json -o output/notes.json
    python3 apple_notes_reader.py export --format md --days 7
        """
    )

    subparsers = parser.add_subparsers(dest="command", help="Command")

    # List command
    list_parser = subparsers.add_parser("list", help="List recent notes")
    list_parser.add_argument("--limit", "-l", type=int, default=20, help="Number of notes")

    # Search command
    search_parser = subparsers.add_parser("search", help="Search notes")
    search_parser.add_argument("query", help="Search query")

    # Read command
    read_parser = subparsers.add_parser("read", help="Read a specific note")
    read_parser.add_argument("note_id", type=int, help="Note ID")

    # Folders command
    subparsers.add_parser("folders", help="List all folders")

    # Export command
    export_parser = subparsers.add_parser("export", help="Export notes")
    export_parser.add_argument("--format", "-f", choices=["json", "csv", "md", "markdown"], default="json")
    export_parser.add_argument("--hours", type=int, help="Only export notes modified in last N hours")
    export_parser.add_argument("--days", type=int, help="Only export notes modified in last N days")
    export_parser.add_argument("--output", "-o", help="Output file path (writes to specific file)")
    export_parser.add_argument("--output-dir", "-O", help="Output directory (auto-generates filename like notes.json)")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    if args.command == "list":
        list_notes(args.limit)

    elif args.command == "search":
        search_notes(args.query)

    elif args.command == "read":
        read_note(args.note_id)

    elif args.command == "folders":
        list_folders()

    elif args.command == "export":
        # Determine output path
        output_path = None
        if args.output:
            output_path = args.output
        elif args.output_dir:
            output_dir = Path(args.output_dir)
            ext = "md" if args.format in ("md", "markdown") else args.format
            filename = f"notes.{ext}"
            if args.days:
                filename = f"notes_last_{args.days}_days.{ext}"
            elif args.hours:
                filename = f"notes_last_{args.hours}_hours.{ext}"
            output_path = str(output_dir / filename)

        export_notes(
            format_type=args.format,
            since_hours=args.hours,
            since_days=args.days,
            output_path=output_path
        )


if __name__ == "__main__":
    main()
