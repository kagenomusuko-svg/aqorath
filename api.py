from fastapi import FastAPI, UploadFile, File, HTTPException, Depends, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pathlib import Path
import shutil
import os
from typing import Optional

from .storage import get_session, DB_PATH
from .company import Company
from .models import Account, JournalEntry, JournalLine
from sqlmodel import select

# Admin token (set in env): ADMIN_API_TOKEN
ADMIN_API_TOKEN = os.environ.get("ADMIN_API_TOKEN", "changeme")

app = FastAPI(title="Aqorath API")

# Base dir to store uploaded files (use DB_PATH parent)
BASE_DATA_DIR = Path(DB_PATH).parent / "aqorath_data"
BASE_DATA_DIR.mkdir(parents=True, exist_ok=True)
COMPANY_LOGOS_DIR = BASE_DATA_DIR / "company_logos"
COMPANY_LOGOS_DIR.mkdir(parents=True, exist_ok=True)

# Static files (including the immutable AC seal)
STATIC_DIR = Path(__file__).resolve().parent / "static"
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent / "templates"))

# Mount static (serves /static/...)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

AC_SEAL_PATH = STATIC_DIR / "ac_seal.png"


def require_admin_token(token: Optional[str] = None):
    """
    Dependency: check X-API-Key header or Authorization: Bearer <token>.
    FastAPI will inject header by name if declared in path function.
    Usage in endpoints: Depends(require_admin_token)
    """
    from fastapi import Header

    def _inner(x_api_key: Optional[str] = Header(None), authorization: Optional[str] = Header(None)):
        key = x_api_key
        if not key and authorization:
            if authorization.lower().startswith("bearer "):
                key = authorization.split(" ", 1)[1].strip()
        if key != ADMIN_API_TOKEN:
            raise HTTPException(status_code=403, detail="Invalid admin token")
        return True

    return _inner


@app.get("/", response_class=HTMLResponse)
def main_page(request: Request):
    """
    Render the main page. The AC seal is shown in the center (immutable).
    Company data shown if a company exists (first record).
    """
    company = None
    with get_session() as s:
        company = s.exec(select(Company)).scalars().first()
    return templates.TemplateResponse("main.html", {"request": request, "company": company})


@app.get("/ac/seal")
def get_ac_seal():
    if not AC_SEAL_PATH.exists():
        raise HTTPException(status_code=404, detail="AC seal not found")
    return FileResponse(AC_SEAL_PATH, media_type="image/png")


@app.post("/company", response_model=Company, dependencies=[Depends(require_admin_token())])
def create_company(company: Company):
    with get_session() as s:
        s.add(company)
        s.commit()
        s.refresh(company)
        return company


@app.get("/company/{company_id}", response_model=Company)
def get_company(company_id: int):
    with get_session() as s:
        c = s.exec(select(Company).where(Company.id == company_id)).one_or_none()
        if not c:
            raise HTTPException(status_code=404, detail="Company not found")
        return c


@app.put("/company/{company_id}", response_model=Company, dependencies=[Depends(require_admin_token())])
def update_company(company_id: int, data: Company):
    with get_session() as s:
        c = s.exec(select(Company).where(Company.id == company_id)).one_or_none()
        if not c:
            raise HTTPException(status_code=404, detail="Company not found")
        for k, v in data.dict(exclude_unset=True).items():
            setattr(c, k, v)
        s.add(c)
        s.commit()
        s.refresh(c)
        return c


@app.post("/company/{company_id}/logo", dependencies=[Depends(require_admin_token())])
def upload_company_logo(company_id: int, file: UploadFile = File(...)):
    # basic validation: only images
    if file.content_type not in ("image/png", "image/jpeg"):
        raise HTTPException(status_code=400, detail="Only PNG/JPEG images are allowed")
    ext = ".png" if file.content_type == "image/png" else ".jpg"
    target = COMPANY_LOGOS_DIR / f"company_{company_id}{ext}"
    with open(target, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    with get_session() as s:
        c = s.exec(select(Company).where(Company.id == company_id)).one_or_none()
        if not c:
            raise HTTPException(status_code=404, detail="Company not found")
        c.logo_path = str(target)
        s.add(c)
        s.commit()
        s.refresh(c)
        return {"logo_path": c.logo_path}


@app.get("/company/{company_id}/logo")
def get_company_logo(company_id: int):
    with get_session() as s:
        c = s.exec(select(Company).where(Company.id == company_id)).one_or_none()
        if not c or not c.logo_path:
            raise HTTPException(status_code=404, detail="Company logo not found")
        return FileResponse(Path(c.logo_path), media_type="image/png")