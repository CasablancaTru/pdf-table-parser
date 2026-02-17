from fastapi import FastAPI, UploadFile, File

app = FastAPI()

@app.get("/")
def health():
    return {"status": "ok"}

@app.post("/parse")
async def parse_pdf(file: UploadFile = File(...)):
    return {
        "items": [
            {
                "item_no": "1",
                "tag": "TEST-040-BFV-2987",
                "dn": "DN800",
                "qty": 1,
                "sheet": 1
            }
        ]
    }
