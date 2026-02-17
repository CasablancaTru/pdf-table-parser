from fastapi import FastAPI, UploadFile, File
import pdfplumber
import re
import tempfile
from typing import List, Dict, Any, Optional

app = FastAPI()

TAG_RE = re.compile(r"\b\d{3}-[A-Z]{2,4}-\d{3,5}\b")   # 040-BFV-2982
DN_RE = re.compile(r"\bDN\s*\d+\b", re.IGNORECASE)     # DN100
INT_RE = re.compile(r"^\s*\d+\s*$")

def norm_cell(x: Any) -> str:
    if x is None:
        return ""
    return str(x).replace("\n", " ").strip()

def table_has_valve_headers(table: List[List[str]]) -> bool:
    # Ищем в первых 3 строках признаки нужной таблицы (Item / DN / Qty / Sheet)
    head = " ".join(" ".join(norm_cell(c) for c in row) for row in table[:3]).lower()
    return (
        ("qty" in head or "колич" in head) and
        ("dn" in head or "nominal" in head or "номин" in head) and
        ("item" in head or "позици" in head)
    )

def parse_qty(s: str) -> Optional[int]:
    s = norm_cell(s)
    if INT_RE.match(s):
        return int(s)
    # на случай "1 pcs." / "1 шт."
    m = re.search(r"\b(\d+)\b", s)
    return int(m.group(1)) if m else None

def parse_valve_table(table: List[List[str]], page_no: int) -> List[Dict[str, Any]]:
    # Преобразуем в матрицу строк
    t = [[norm_cell(c) for c in row] for row in table if any(norm_cell(c) for c in row)]
    if not t:
        return []

    # Находим строку-заголовок (там где есть Qty/Количество)
    header_idx = None
    for i, row in enumerate(t[:5]):
        row_l = " ".join(row).lower()
        if ("qty" in row_l or "колич" in row_l) and ("dn" in row_l or "номин" in row_l):
            header_idx = i
            break

    if header_idx is None:
        return []

    header = [c.lower() for c in t[header_idx]]
    # Пытаемся определить индексы колонок
    def find_col(keys):
        for k in keys:
            for idx, h in enumerate(header):
                if k in h:
                    return idx
        return None

    ord_i  = find_col(["ord", "№", "no."])
    item_i = find_col(["item", "позици"])
    dn_i   = find_col(["dn", "nominal", "номин"])
    qty_i  = find_col(["qty", "колич"])
    sheet_i = find_col(["sheet", "лист"])

    # Если какие-то колонки не нашли — попробуем “разумные” дефолты по типовой форме
    # (Ord | Item | DN | Qty | Sheet)
    if item_i is None and len(header) >= 2: item_i = 1
    if dn_i is None and len(header) >= 3: dn_i = 2
    if qty_i is None and len(header) >= 4: qty_i = 3

    items = []
    for row in t[header_idx + 1:]:
        # защитимся от кривых строк
        if len(row) < max(filter(lambda x: x is not None, [item_i, dn_i, qty_i])) + 1:
            continue

        item_val = row[item_i] if item_i is not None else ""
        dn_val   = row[dn_i] if dn_i is not None else ""
        qty_val  = row[qty_i] if qty_i is not None else ""

        # Фильтр: это должна быть “клапанная” строка
        if not TAG_RE.search(item_val):
            continue
        if not DN_RE.search(dn_val):
            continue

        ord_val = row[ord_i] if ord_i is not None and ord_i < len(row) else ""
        sheet_val = row[sheet_i] if sheet_i is not None and sheet_i < len(row) else ""

        items.append({
            "ord_no": parse_qty(ord_val),
            "item_id": TAG_RE.search(item_val).group(0),
            "dn": DN_RE.search(dn_val).group(0).upper().replace(" ", ""),
            "qty": parse_qty(qty_val),
            "sheet": parse_qty(sheet_val) if sheet_val else page_no,
            "page": page_no,
        })

    return items

@app.get("/")
def health():
    return {"status": "ok"}

@app.post("/parse")
async def parse_pdf(file: UploadFile = File(...)):
    # сохраняем во временный файл
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name

    results: List[Dict[str, Any]] = []

    with pdfplumber.open(tmp_path) as pdf:
        for p_idx, page in enumerate(pdf.pages, start=1):
            # настройки под “табличные” PDF
            tables = page.extract_tables({
                "vertical_strategy": "lines",
                "horizontal_strategy": "lines",
                "intersection_tolerance": 5,
                "snap_tolerance": 3,
                "join_tolerance": 3,
                "edge_min_length": 20,
                "min_words_vertical": 3,
                "min_words_horizontal": 1,
            }) or []

            for tb in tables:
                if not tb:
                    continue
                # берём только таблицы похожие на "List of valves..."
                if table_has_valve_headers(tb):
                    results.extend(parse_valve_table(tb, page_no=p_idx))

    return {"items": results}
