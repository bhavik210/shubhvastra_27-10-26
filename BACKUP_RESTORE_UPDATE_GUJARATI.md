SHUBHVASTRA BACKUP / RESTORE UPDATE

- Utilities now provides Full Backup ZIP and a portable SQLite database snapshot (.db) download.
- Restore accepts Shubhvastra backup ZIP and compatible .db, .sqlite, or .sqlite3 files.
- .rar and CSV are not direct restore formats.
- The database file must contain the current Shubhvastra app tables and compatible columns. An older database with a different schema needs migration first.
- Restore replaces current records. Download a fresh backup before restoring.
- Sidebar colors changed to off-white with black text.
- Testing mode remains enabled; protect the public app URL and do not use open access for real business data.
