from fastapi import FastAPI, UploadFile, File
import pdfplumber
import io
import re

app = FastAPI()


@app.get("/")
def health():
    return {"status": "ok"}


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def pick_col_idx(headers, keys):
    for i, h in enumerate(headers):
        hh = norm(h)
        if any(k in hh for k in keys):
            return i
    return None


@app.post("/parse")
async def parse_pdf(file: UploadFile = File(...)):
    data = await file.read()

    with pdfplumber.open(io.BytesIO(data)) as pdf:
        page = pdf.pages[0]

        tables = page.extract_tables({
            "vertical_strategy": "lines",
            "horizontal_strategy": "lines",
            "intersection_tolerance": 5,
            "snap_tolerance": 3,
            "join_tolerance": 3,
            "edge_min_length": 20,
            "min_words_vertical": 1,
            "min_words_horizontal": 1,
        })

    if not tables:
        return {"items": []}

    table = None
    for t in tables:
        if t and len(t) >= 2 and len(t[0]) >= 3:
            table = t
            break

    if not table:
        return {"items": []}

    headers = table[0]
    rows = table[1:]

    ord_i = pick_col_idx(headers, ["ord", "№", "no"])
    item_i = pick_col_idx(headers, ["пози", "item"])
    dn_i = pick_col_idx(headers, ["номин", "diameter", "dn"])
    qty_i = pick_col_idx(headers, ["колич", "qty"])

    items = []
    for r in rows:
        if not r or all(not (c and c.strip()) for c in r):
            continue

        def get(i):
            if i is None or i >= len(r):
                return ""
            return (r[i] or "").strip()

        ord_no = get(ord_i) or None
        item_id = get(item_i) or None
        dn = get(dn_i) or None
        qty_raw = get(qty_i)

        qty = None
        if qty_raw:
            m = re.search(r"\d+", qty_raw)
            qty = int(m.group()) if m else None

        if not item_id and not dn and qty is None:
            continue

        items.append({
            "ord_no": ord_no,
            "item_id": item_id,
            "dn": dn,
            "qty": qty,
            "sheet": 1
        })

    return {"items": items}
