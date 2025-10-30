from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any
from aqorath.core import generate_preview, post_entry, list_templates

app = FastAPI(title="Aqorath Core API", version="0.1.0")


class PreviewRequest(BaseModel):
    template_key: str
    amount: float
    ctx: Optional[Dict[str, Any]] = None


class PostRequest(PreviewRequest):
    user: Optional[str] = None


@app.get("/templates")
def templates():
    return {"templates": list_templates()}


@app.post("/preview")
def preview(req: PreviewRequest):
    try:
        preview = generate_preview(req.template_key, req.amount, ctx=req.ctx or {})
        return preview
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/post")
def post(req: PostRequest):
    try:
        entry_id = post_entry(req.template_key, req.amount, ctx=req.ctx or {}, user=req.user)
        return {"entry_id": entry_id}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))