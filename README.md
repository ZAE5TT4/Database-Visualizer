# Database Visualizer

## Overview
Database Visualizer is a desktop tool that reads SQLite databases and generates an interactive HTML schema diagram.

The output diagram shows:
- tables and columns
- column types
- foreign key relationships
- draggable table blocks
- resizable table blocks (using the bottom resize bar)

## Folder Structure
Keep this structure:

```text
database_visualizer/
  database_visualizer.exe
  DB/
    your_database.db
```

## Quick Start (EXE)
1. Put `database_visualizer.exe` file in any folder.
2. Create a subfolder named `DB` in the same folder as the EXE.
3. Place your SQLite database files (`.db`, `.sqlite`, `.sqlite3`) into `DB`.
4. Run `database_visualizer.exe`.
5. Open the generated HTML file in the same folder as the EXE.

## Running From Python (Optional)
If you use the Python script directly:

```powershell
python database_visualizer.py
```

The script scans the local `DB` folder and generates diagram HTML files.

## Output Files
The tool generates:
- `<database_name>_diagram.html`
- `db_diagram.html` (compatibility copy)

## Interaction Controls
- Drag table: hold and drag the blue table header.
- Resize table: use the resize handle in the bottom resize bar.
- Move canvas: use browser scrollbars / mouse wheel if the workspace is larger than the screen.

## Requirements
- SQLite database file(s)
- For EXE usage: no Python installation required
- For script usage: Python 3.x

## Troubleshooting
### No tables appear
- Make sure your database is a valid SQLite file.
- Check that the database file is inside the `DB` folder.
- Refresh the diagram page with `Ctrl+F5`.

### EXE runs but no output
- Verify that `DB` exists next to the EXE.
- Ensure at least one database contains user tables (not only internal `sqlite_%` tables).

### Browser shows old diagram
- Force refresh with `Ctrl+F5`.
- Close old tabs and reopen the latest generated HTML file.

## Notes
- The EXE uses the folder where the EXE is located as its working base.
- Always keep the `DB` folder next to `database_visualizer.exe`.
