# Apple Notes Reader

A Python CLI tool to read, search, and export your Apple Notes directly from the SQLite database. No dependencies required - uses only Python standard library.

## Installation

No installation needed. Just clone and run:

```bash
git clone https://github.com/tmad4000/apple-notes-reader.git
cd apple-notes-reader
```

## Usage

```bash
# List recent notes (default 20)
python3 apple-notes/apple_notes_reader.py list

# List more notes
python3 apple-notes/apple_notes_reader.py list --limit 50

# Search notes by title and content
python3 apple-notes/apple_notes_reader.py search "meeting"

# Read a specific note by ID
python3 apple-notes/apple_notes_reader.py read 12345

# List all folders with note counts
python3 apple-notes/apple_notes_reader.py folders

# Export to specific file
python3 apple-notes/apple_notes_reader.py export -o notes.json

# Export to directory (auto-generates filename)
python3 apple-notes/apple_notes_reader.py export -O output --format md

# Export to stdout
python3 apple-notes/apple_notes_reader.py export --format json > notes.json

# Export notes from last 7 days
python3 apple-notes/apple_notes_reader.py export --days 7 -O output
```

## Output Options

All export commands support flexible output options:

| Option | Description | Example |
|--------|-------------|---------|
| `-o FILE` | Write to specific file path | `-o /path/to/notes.json` |
| `-O DIR` | Write to directory (auto-generates filename) | `-O output` |
| *(neither)* | Output to stdout (for piping) | `> file.json` |

Auto-generated filenames include filters when specified:
```bash
-O output --days 7    # -> output/notes_last_7_days.json
-O output             # -> output/notes.json
```

## Output Examples

**List:**
```
ID       Modified           Folder               Title
----------------------------------------------------------------------------------------------------
14671    2025-11-30 14:16   Notes                Meeting notes from standup
14680    2025-11-30 14:15   Notes                Project planning document
```

**Search:**
```
Found 67 notes matching 'project':

ID       Modified           Title
--------------------------------------------------------------------------------
14623    2025-11-30 05:48   The project planning document...
```

## How It Works

Apple Notes stores data in a SQLite database at:
```
~/Library/Group Containers/group.com.apple.notes/NoteStore.sqlite
```

The tool:
1. Opens the database in **read-only mode** (safe, won't corrupt data)
2. Queries `ZICCLOUDSYNCINGOBJECT` for note metadata (title, dates, folder)
3. Joins with `ZICNOTEDATA` for note content
4. Decompresses gzip data and parses the protobuf format to extract text

## Limitations

- **Read-only** - Cannot create or modify notes (by design, for safety)
- **Password-protected notes** - Encrypted notes cannot be decrypted
- **Formatting** - Rich text formatting may be lost in extraction
- **Attachments** - Images, drawings, and tables are not extracted
- **Short notes** - Very short notes may only have title extracted (used as content)

## License

MIT
