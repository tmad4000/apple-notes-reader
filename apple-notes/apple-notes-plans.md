# Apple Notes Reader - Future Plans

## Auto-Sync / Watch Feature

### Goal
Automatically detect new and updated Apple Notes in real-time and export/sync them.

### Approaches

#### Option 1: File System Watcher (Recommended)
- Use `watchdog` library to monitor `NoteStore.sqlite-wal` file
- WAL file changes on every write - very responsive
- Trigger callback on change, debounce to avoid rapid-fire events
- Pros: Simple, reliable, low overhead
- Cons: Requires `pip install watchdog`

#### Option 2: Polling with Change Detection
- Check `ZMODIFICATIONDATE1 > last_sync_time` periodically
- Export only changed/new notes
- Pros: No dependencies, works everywhere
- Cons: Not real-time, uses more resources if polling frequently

#### Option 3: macOS FSEvents (Native)
- Use `PyObjC` to tap into native file system events
- Most macOS-native approach
- Pros: Instant detection, low overhead
- Cons: macOS only, heavier dependency

### Proposed Implementation

```bash
# Watch for changes and output new/updated notes as JSON lines
python3 apple_notes_reader.py watch

# Watch and export to a file (appends)
python3 apple_notes_reader.py watch --output notes_stream.jsonl

# Watch with webhook callback
python3 apple_notes_reader.py watch --webhook http://localhost:8080/notes
```

### Data Flow
1. Monitor `~/Library/Group Containers/group.com.apple.notes/NoteStore.sqlite-wal`
2. On change detected, query for notes with `ZMODIFICATIONDATE1 > last_check`
3. Output changed notes as JSON
4. Update `last_check` timestamp

### Use Cases
- Sync notes to external system (Obsidian, Notion, etc.)
- Feed notes into AI pipeline for processing
- Backup/archive notes incrementally
- Trigger workflows on new notes (webhooks, scripts)

---

## Unified SQLite Database

### Goal
Create a single, clean SQLite database that consolidates Apple Notes and Contacts into a unified schema that other apps can easily query.

### Why
- Apple's native databases use complex schemas with Core Data conventions (Z_PK, ZICCLOUDSYNCINGOBJECT, etc.)
- Note content is stored as gzip-compressed protobuf - not directly queryable
- Other apps (AI tools, search, dashboards) could benefit from a simpler format

### Proposed Schema

```sql
-- Main items table for all data types
CREATE TABLE items (
    id TEXT PRIMARY KEY,           -- e.g., "note:14671" or "contact:35E6AFC6:123"
    source TEXT NOT NULL,          -- 'apple_notes', 'apple_contacts'
    type TEXT NOT NULL,            -- 'note', 'contact'
    title TEXT,
    content TEXT,                  -- Plain text, already extracted
    folder TEXT,                   -- For notes
    created_at DATETIME,
    modified_at DATETIME,
    synced_at DATETIME,            -- When we last synced this record
    metadata JSON                  -- Flexible extra fields (emails, phones, pinned, etc.)
);

-- Full-text search index
CREATE VIRTUAL TABLE items_fts USING fts5(title, content, content=items);

-- Track sync state
CREATE TABLE sync_state (
    source TEXT PRIMARY KEY,
    last_sync DATETIME,
    last_modification_seen REAL    -- Core Data timestamp of most recent item
);
```

### Proposed Commands

```bash
# Initial sync - populate the unified database
python3 sync.py init

# Incremental sync - update only changed items
python3 sync.py update

# Full-text search across everything
python3 sync.py search "meeting with john"

# Query via SQL directly
sqlite3 ~/code/apple-notes-reader/unified.db "SELECT * FROM items WHERE type='contact' AND modified_at > '2025-12-01'"
```

### Benefits
- **Simple queries**: `SELECT * FROM items WHERE content LIKE '%project%'`
- **Full-text search**: Built-in FTS5 for fast text search
- **Cross-source search**: Find notes mentioning a contact's name
- **App integration**: Any app/language can read SQLite
- **Incremental updates**: Only sync what changed
- **Single file**: Easy to backup, move, or share

### Implementation Steps
1. Create `sync.py` with schema initialization
2. Add `sync_notes()` function to extract and insert notes
3. Add `sync_contacts()` function to extract and insert contacts
4. Track last sync time to enable incremental updates
5. Add FTS5 triggers to keep search index updated
6. Add CLI commands for init/update/search

---

## Other Future Ideas

### Improved Content Extraction
- Better protobuf parsing for full note content
- Handle attachments (images, drawings, tables)
- Preserve formatting (bold, lists, links)

### Search Improvements
- Fuzzy search
- Search by date range
- Search by folder

### Export Formats
- Markdown export
- HTML export
- Obsidian-compatible format with backlinks

### MCP Server
- Wrap as Model Context Protocol server
- Direct integration with Claude Code / AI tools
- Query notes via natural language
