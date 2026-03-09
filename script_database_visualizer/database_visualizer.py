import json
import math
import sqlite3
import webbrowser
import sys
from collections import defaultdict, deque
from pathlib import Path


if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys.executable).resolve().parent
else:
    BASE_DIR = Path(__file__).resolve().parent
DB_DIR = BASE_DIR / "DB"
OUTPUT_SUFFIX = "_diagram.html"
LEGACY_OUTPUT_FILE = "db_diagram.html"
SUPPORTED_EXTENSIONS = {".db", ".sqlite", ".sqlite3"}


def esc(value):
    if value is None:
        return ""
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def get_tables(conn):
    cur = conn.cursor()
    cur.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type='table'
          AND name NOT LIKE 'sqlite_%'
        ORDER BY name
        """
    )
    return [row[0] for row in cur.fetchall()]


def get_table_columns(conn, table_name):
    cur = conn.cursor()
    cur.execute(f"PRAGMA table_info('{table_name}')")
    rows = cur.fetchall()

    result = []
    for row in rows:
        cid, name, col_type, notnull, default_value, pk = row
        result.append(
            {
                "cid": cid,
                "name": name,
                "type": col_type or "",
                "notnull": bool(notnull),
                "default": default_value,
                "pk": bool(pk),
            }
        )
    return result


def get_foreign_keys(conn, table_name):
    cur = conn.cursor()
    cur.execute(f"PRAGMA foreign_key_list('{table_name}')")
    rows = cur.fetchall()

    result = []
    for row in rows:
        _, _, ref_table, from_col, to_col, on_update, on_delete, _ = row
        result.append(
            {
                "from_table": table_name,
                "from_col": from_col,
                "to_table": ref_table,
                "to_col": to_col,
                "on_update": on_update,
                "on_delete": on_delete,
            }
        )
    return result


def table_height(table_data):
    header_h = 38
    row_h = 28
    padding = 10
    return header_h + max(1, len(table_data["columns"])) * row_h + padding


def connected_components(nodes, graph):
    seen = set()
    components = []
    for node in nodes:
        if node in seen:
            continue
        queue = deque([node])
        seen.add(node)
        comp = []
        while queue:
            cur = queue.popleft()
            comp.append(cur)
            for nxt in graph[cur]:
                if nxt not in seen:
                    seen.add(nxt)
                    queue.append(nxt)
        components.append(comp)
    return components


def place_component(nodes, graph, heights, x_start):
    level_to_nodes = defaultdict(list)
    local_positions = {}
    if not nodes:
        return local_positions, x_start

    root = max(nodes, key=lambda n: len(graph[n]))
    levels = {root: 0}
    queue = deque([root])
    while queue:
        cur = queue.popleft()
        for nxt in graph[cur]:
            if nxt not in levels:
                levels[nxt] = levels[cur] + 1
                queue.append(nxt)

    for node in nodes:
        level_to_nodes[levels.get(node, 0)].append(node)

    col_gap = 130
    row_gap = 70
    box_w = 300
    max_level = 0

    for level, level_nodes in sorted(level_to_nodes.items()):
        max_level = max(max_level, level)
        level_nodes.sort(key=lambda name: (-len(graph[name]), name))
        y = 70
        for name in level_nodes:
            local_positions[name] = {"x": x_start + level * (box_w + col_gap), "y": y}
            y += heights[name] + row_gap

    x_after = x_start + (max_level + 1) * (box_w + col_gap) + 150
    return local_positions, x_after


def make_layout(tables, relations):
    table_names = list(tables.keys())
    if not table_names:
        return {}, 1600, 1000

    graph = {name: set() for name in table_names}
    for rel in relations:
        src = rel["from_table"]
        dst = rel["to_table"]
        if src in graph and dst in graph and src != dst:
            graph[src].add(dst)
            graph[dst].add(src)

    heights = {name: table_height(tables[name]) for name in table_names}
    positions = {}
    x_cursor = 70
    max_y = 0
    max_x = 0

    components = connected_components(table_names, graph)
    components.sort(key=lambda comp: (-len(comp), sorted(comp)[0]))

    for component in components:
        local_positions, x_cursor = place_component(component, graph, heights, x_cursor)
        positions.update(local_positions)
        for name in component:
            max_x = max(max_x, positions[name]["x"] + 300)
            max_y = max(max_y, positions[name]["y"] + heights[name])

    workspace_w = max(1800, max_x + 200)
    workspace_h = max(1100, max_y + 180)
    return positions, workspace_w, workspace_h


def build_html(db_name, tables, relations, positions, workspace_w, workspace_h):
    tables_js = []
    for table_name, table_data in tables.items():
        pos = positions[table_name]
        tables_js.append(
            {
                "name": table_name,
                "x": pos["x"],
                "y": pos["y"],
                "width": 300,
                "columns": table_data["columns"],
            }
        )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ER Diagram: {esc(db_name)}</title>
<style>
    html, body {{
        margin: 0;
        padding: 0;
        width: 100%;
        height: 100%;
        overflow: hidden;
        font-family: Arial, sans-serif;
        background: #d8d8d8;
    }}

    #topbar {{
        height: 44px;
        background: #1f2a44;
        color: #fff;
        display: flex;
        align-items: center;
        padding: 0 14px;
        box-sizing: border-box;
        border-bottom: 2px solid #0e1530;
        font-weight: bold;
        font-size: 16px;
    }}

    #canvas {{
        position: relative;
        width: 100%;
        height: calc(100% - 44px);
        overflow: auto;
        background: #cfcfcf;
        background-image:
            linear-gradient(to right, rgba(0, 0, 0, 0.04) 1px, transparent 1px),
            linear-gradient(to bottom, rgba(0, 0, 0, 0.04) 1px, transparent 1px);
        background-size: 24px 24px;
    }}

    #workspace {{
        position: relative;
        width: {workspace_w}px;
        height: {workspace_h}px;
    }}

    svg#lines {{
        position: absolute;
        inset: 0;
        width: {workspace_w}px;
        height: {workspace_h}px;
        pointer-events: none;
        overflow: hidden;
    }}

    .table-box {{
        position: absolute;
        width: 300px;
        min-width: 220px;
        min-height: 120px;
        max-width: 900px;
        background: #efefef;
        border: 2px solid #666;
        box-shadow: 3px 3px 0 rgba(0, 0, 0, 0.18);
        user-select: none;
        resize: none;
        overflow: visible;
        box-sizing: border-box;
        display: flex;
        flex-direction: column;
    }}

    .table-header {{
        background: #001f99;
        color: #fff;
        font-weight: bold;
        padding: 7px 10px;
        font-size: 16px;
        border-bottom: 1px solid #00135f;
        cursor: grab;
        box-sizing: border-box;
        width: 100%;
        flex: 0 0 auto;
    }}

    .table-header:active {{
        cursor: grabbing;
    }}
    .table-content {{
        overflow: hidden;
        padding: 0;
        box-sizing: border-box;
        flex: 1 1 auto;
    }}

    .resize-bar {{
        position: relative;
        flex: 0 0 16px;
        height: 16px;
        border-top: 1px solid #b4b4b4;
        background: #e4e4e4;
        box-sizing: border-box;
    }}

    .resize-handle {{
        position: absolute;
        width: 12px;
        height: 12px;
        right: 2px;
        top: 1px;
        cursor: nwse-resize;
        z-index: 35;
        border: 1px solid #555;
        box-sizing: border-box;
        background:
            linear-gradient(135deg, transparent 35%, #666 35%, #666 45%, transparent 45%, transparent 55%, #666 55%, #666 65%, transparent 65%),
            #ececec;
    }}

    .row {{
        display: grid;
        grid-template-columns: minmax(140px, 1.2fr) minmax(120px, 1fr) minmax(260px, 1.8fr);
        align-items: center;
        min-height: 26px;
        border-top: 1px solid #b9b9b9;
        background: #efefef;
        position: relative;
        font-size: 14px;
        box-sizing: border-box;
        width: 100%;
    }}

    .row:nth-child(even) {{
        background: #e5e5e5;
    }}

    .col-name {{
        min-width: 0;
        padding: 4px 8px;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
    }}
    .col-type {{
        min-width: 0;
        padding: 4px 6px;
        border-left: 1px solid #c4c4c4;
        color: #444;
        font-size: 12px;
        text-align: left;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
    }}

    .col-def {{
        min-width: 0;
        padding: 4px 8px;
        border-left: 1px solid #c4c4c4;
        color: #222;
        font-size: 12px;
        text-align: left;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
    }}
    .anchor {{
        position: absolute;
        width: 10px;
        height: 10px;
        background: #ffda00;
        border: 1px solid #333;
        box-sizing: border-box;
        top: 50%;
        transform: translateY(-50%);
        z-index: 20;
        pointer-events: none;
    }}
    .anchor.left {{
        left: 0;
        transform: translate(-50%, -50%);
    }}
    .anchor.right {{
        right: 0;
        transform: translate(50%, -50%);
    }}

    .empty-note {{
        position: fixed;
        left: 16px;
        bottom: 16px;
        background: rgba(255, 255, 255, 0.95);
        border: 1px solid #888;
        padding: 10px 12px;
        font-size: 13px;
        box-shadow: 2px 2px 0 rgba(0, 0, 0, 0.12);
        max-width: 420px;
    }}
</style>
</head>
<body>
    <div id="topbar">Database Diagram: {esc(db_name)}</div>
    <div id="canvas">
        <div id="workspace">
            <svg id="lines"></svg>
        </div>
    </div>
    {"<div class='empty-note'>No foreign key relations were found in this database.</div>" if not relations else ""}

<script>
const TABLES = {json.dumps(tables_js, ensure_ascii=False)};
const RELATIONS = {json.dumps(relations, ensure_ascii=False)};

const workspace = document.getElementById("workspace");
const svg = document.getElementById("lines");
const resizeObserver = new ResizeObserver(() => drawRelations());

function buildColumnDefinition(col) {{
    const parts = [];
    parts.push(`"${{col.name}}"`);
    if (col.type) parts.push(col.type);
    if (col.notnull) parts.push("NOT NULL");
    if (col.pk) parts.push("PRIMARY KEY");
    if (col.default !== null && col.default !== undefined) {{
        parts.push("DEFAULT " + String(col.default));
    }}
    return parts.join(" ");
}}

function createTableBox(table) {{
    const box = document.createElement("div");
    box.className = "table-box";
    box.dataset.table = table.name;
    box.style.left = table.x + "px";
    box.style.top = table.y + "px";
    box.style.width = (table.width || 300) + "px";

    const header = document.createElement("div");
    header.className = "table-header";
    header.textContent = table.name;
    box.appendChild(header);

    const content = document.createElement("div");
    content.className = "table-content";

    table.columns.forEach(col => {{
        const row = document.createElement("div");
        row.className = "row";
        row.dataset.col = col.name;
        const name = document.createElement("div");
        name.className = "col-name";
        name.textContent = col.name;

        const type = document.createElement("div");
        type.className = "col-type";
        type.textContent = col.type || "";

        const def = document.createElement("div");
        def.className = "col-def";
        def.textContent = buildColumnDefinition(col);

        const leftAnchor = document.createElement("div");
        leftAnchor.className = "anchor left";

        const rightAnchor = document.createElement("div");
        rightAnchor.className = "anchor right";

        row.appendChild(leftAnchor);
        row.appendChild(name);
        row.appendChild(type);
        row.appendChild(def);
        row.appendChild(rightAnchor);
        content.appendChild(row);
    }});

    box.appendChild(content);
    workspace.appendChild(box);
    makeDraggable(box, header);
    makeResizable(box);
    resizeObserver.observe(box);
    content.addEventListener("scroll", drawRelations);
}}

function getRowElement(tableName, colName) {{
    const table = document.querySelector(`.table-box[data-table="${{CSS.escape(tableName)}}"]`);
    if (!table) return null;
    return table.querySelector(`.row[data-col="${{CSS.escape(colName)}}"]`);
}}

function getAnchorPoint(tableName, colName, side) {{
    const row = getRowElement(tableName, colName);
    if (!row) return null;
    const anchor = row.querySelector(".anchor." + side);
    if (!anchor) return null;

    const a = anchor.getBoundingClientRect();
    const w = workspace.getBoundingClientRect();
    return {{
        x: a.left - w.left + a.width / 2,
        y: a.top - w.top + a.height / 2
    }};
}}

function linePath(x1, y1, x2, y2) {{
    const dx = Math.abs(x2 - x1);
    const bend = Math.max(45, dx * 0.35);
    const mid1 = x1 + (x2 > x1 ? bend : -bend);
    const mid2 = x2 - (x2 > x1 ? bend : -bend);
    return `M ${{x1}} ${{y1}} C ${{mid1}} ${{y1}}, ${{mid2}} ${{y2}}, ${{x2}} ${{y2}}`;
}}

function drawRelations() {{
    svg.innerHTML = "";
    RELATIONS.forEach(rel => {{
        let start = getAnchorPoint(rel.from_table, rel.from_col, "right");
        let end = getAnchorPoint(rel.to_table, rel.to_col, "left");

        if (!start || !end) return;
        if (end.x < start.x) {{
            start = getAnchorPoint(rel.from_table, rel.from_col, "left");
            end = getAnchorPoint(rel.to_table, rel.to_col, "right");
            if (!start || !end) return;
        }}

        const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
        path.setAttribute("d", linePath(start.x, start.y, end.x, end.y));
        path.setAttribute("fill", "none");
        path.setAttribute("stroke", "#222");
        path.setAttribute("stroke-width", "2");

        const startDot = document.createElementNS("http://www.w3.org/2000/svg", "circle");
        startDot.setAttribute("cx", start.x);
        startDot.setAttribute("cy", start.y);
        startDot.setAttribute("r", "3");
        startDot.setAttribute("fill", "#fff");
        startDot.setAttribute("stroke", "#222");
        startDot.setAttribute("stroke-width", "1.5");

        const endDot = document.createElementNS("http://www.w3.org/2000/svg", "circle");
        endDot.setAttribute("cx", end.x);
        endDot.setAttribute("cy", end.y);
        endDot.setAttribute("r", "3");
        endDot.setAttribute("fill", "#ffda00");
        endDot.setAttribute("stroke", "#222");
        endDot.setAttribute("stroke-width", "1.5");

        svg.appendChild(path);
        svg.appendChild(startDot);
        svg.appendChild(endDot);
    }});
}}

function makeResizable(target) {{
    const bar = document.createElement("div");
    bar.className = "resize-bar";

    const handle = document.createElement("div");
    handle.className = "resize-handle";
    bar.appendChild(handle);
    target.appendChild(bar);

    const header = target.querySelector(".table-header");
    const content = target.querySelector(".table-content");

    let resizing = false;
    let startX = 0;
    let startY = 0;
    let startW = 0;
    let startH = 0;    function calcMinHeight() {{
        const headerH = header ? Math.ceil(header.getBoundingClientRect().height) : 0;
        const barH = Math.ceil(bar.getBoundingClientRect().height || 16);
        const contentH = content ? Math.ceil(content.scrollHeight) : 0;
        return headerH + barH + contentH + 4;
    }}

    const baseMinHeight = calcMinHeight();
    target.style.minHeight = baseMinHeight + "px";

    handle.addEventListener("mousedown", (e) => {{
        const rect = target.getBoundingClientRect();
        resizing = true;
        startX = e.clientX;
        startY = e.clientY;
        startW = rect.width;
        startH = rect.height;
        document.body.style.cursor = "nwse-resize";
        e.preventDefault();
        e.stopPropagation();
    }});

    document.addEventListener("mousemove", (e) => {{
        if (!resizing) return;
        const dx = e.clientX - startX;
        const dy = e.clientY - startY;
        const nextW = Math.max(220, Math.min(1200, Math.round(startW + dx)));
        const nextH = Math.max(baseMinHeight, Math.min(1200, Math.round(startH + dy)));
        target.style.width = nextW + "px";
        target.style.height = nextH + "px";
        drawRelations();
    }});

    document.addEventListener("mouseup", () => {{
        if (!resizing) return;
        resizing = false;
        document.body.style.cursor = "";
        drawRelations();
    }});
}}

function makeDraggable(target, handle) {{
    let dragging = false;
    let startX = 0;
    let startY = 0;
    let boxX = 0;
    let boxY = 0;

    handle.addEventListener("mousedown", (e) => {{
        dragging = true;
        startX = e.clientX;
        startY = e.clientY;
        boxX = parseInt(target.style.left, 10) || 0;
        boxY = parseInt(target.style.top, 10) || 0;
        document.body.style.cursor = "grabbing";
        e.preventDefault();
    }});

    document.addEventListener("mousemove", (e) => {{
        if (!dragging) return;
        target.style.left = (boxX + (e.clientX - startX)) + "px";
        target.style.top = (boxY + (e.clientY - startY)) + "px";
        drawRelations();
    }});

    document.addEventListener("mouseup", () => {{
        dragging = false;
        document.body.style.cursor = "";
    }});
}}

TABLES.forEach(createTableBox);
setTimeout(drawRelations, 80);
window.addEventListener("resize", drawRelations);
</script>
</body>
</html>
"""
    return html


def discover_databases(db_dir):
    if not db_dir.exists():
        return []

    db_files = []
    for path in sorted(db_dir.iterdir()):
        if not path.is_file():
            continue
        if path.suffix.lower() in SUPPORTED_EXTENSIONS or path.suffix == "":
            db_files.append(path)
    return db_files


def load_database_model(db_path):
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON;")
    try:
        table_names = get_tables(conn)
        tables = {}
        relations = []
        for table_name in table_names:
            columns = get_table_columns(conn, table_name)
            fks = get_foreign_keys(conn, table_name)
            tables[table_name] = {"columns": columns}
            relations.extend(fks)
        return tables, relations
    finally:
        conn.close()


def generate_diagram(db_path):
    tables, relations = load_database_model(db_path)
    if not tables:
        print(f"Skipped {db_path.name}: no user tables found.")
        return None

    positions, workspace_w, workspace_h = make_layout(tables, relations)
    html = build_html(db_path.name, tables, relations, positions, workspace_w, workspace_h)
    output_path = BASE_DIR / f"{db_path.stem}{OUTPUT_SUFFIX}"
    output_path.write_text(html, encoding="utf-8")
    print(f"Diagram created: {output_path.resolve()}")
    return output_path.resolve()


def pick_databases_from_args(args):
    if len(args) <= 1:
        return discover_databases(DB_DIR)

    requested = args[1]
    candidate = Path(requested)
    if not candidate.is_absolute():
        candidate = DB_DIR / requested
    return [candidate] if candidate.exists() and candidate.is_file() else []


def main():
    import sys

    db_paths = pick_databases_from_args(sys.argv)
    if not db_paths:
        print(f"No database files found in: {DB_DIR.resolve()}")
        print("Put your database files into the DB folder or pass a file name as an argument.")
        return

    created = []
    for db_path in db_paths:
        try:
            out = generate_diagram(db_path)
            if out is not None:
                created.append(out)
        except sqlite3.Error as exc:
            print(f"Skipped {db_path.name}: not a valid SQLite database ({exc}).")

    if len(created) == 1:
        legacy_path = BASE_DIR / LEGACY_OUTPUT_FILE
        if created[0] != legacy_path:
            legacy_path.write_text(created[0].read_text(encoding="utf-8"), encoding="utf-8")
            print(f"Compatibility copy created: {legacy_path.resolve()}")
        webbrowser.open(created[0].as_uri())
    elif created:
        print("Generated multiple diagrams. Open any HTML file from this list:")
        for path in created:
            print(f"  - {path}")
    else:
        print("No diagrams were generated.")


if __name__ == "__main__":
    main()
























