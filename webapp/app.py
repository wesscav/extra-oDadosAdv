from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

import extract_ocr


ROOT_DIR = Path(__file__).resolve().parents[1]
STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(title="extra-oDadosAdv - upload OCR", version="0.1.0")


def _apply_tesseract_cmd_from_env() -> None:
    """
    Allows setting the Tesseract binary path on Windows:
      set TESSERACT_CMD=C:\\Program Files\\Tesseract-OCR\\tesseract.exe
    """
    tesseract_cmd = os.environ.get("TESSERACT_CMD")
    if not tesseract_cmd:
        return
    try:
        if extract_ocr.pytesseract is not None:
            extract_ocr.pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
    except Exception:
        # best-effort; dependency checks will still surface issues
        return


def _read_index_html() -> str:
    index_path = STATIC_DIR / "index.html"
    return index_path.read_text(encoding="utf-8")


@app.get("/api/health")
def health() -> Dict[str, Any]:
    _apply_tesseract_cmd_from_env()
    missing = extract_ocr.check_dependencies()
    return {
        "ok": len(missing) == 0,
        "missing": missing,
        "env": {
            "POPPLER_PATH": os.environ.get("POPPLER_PATH"),
            "TESSERACT_CMD": os.environ.get("TESSERACT_CMD"),
        },
    }


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    return HTMLResponse(_read_index_html())


@app.post("/api/ocr")
async def ocr_endpoint(
    files: List[UploadFile] = File(...),
    dpi: int = Form(300),
    lang: str = Form("por"),
    poppler_path: Optional[str] = Form(None),
    auto_detect_inss: bool = Form(True),
) -> JSONResponse:
    _apply_tesseract_cmd_from_env()

    missing = extract_ocr.check_dependencies()
    if missing:
        raise HTTPException(
            status_code=500,
            detail={
                "message": "Dependências ausentes para OCR.",
                "missing": missing,
                "hint": "Instale Tesseract e Poppler e/ou configure POPPLER_PATH e TESSERACT_CMD.",
            },
        )

    poppler_path_final = poppler_path or os.environ.get("POPPLER_PATH")
    if not files:
        raise HTTPException(status_code=400, detail={"message": "Nenhum arquivo enviado."})

    results: List[Dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="extra-oDadosAdv-") as tmpdir:
        tmpdir_path = Path(tmpdir)

        for uf in files:
            filename = uf.filename or "arquivo.pdf"
            suffix = Path(filename).suffix.lower()
            if suffix != ".pdf":
                raise HTTPException(
                    status_code=400,
                    detail={"message": f"Arquivo inválido: {filename}. Envie apenas PDFs."},
                )

            target_path = tmpdir_path / filename
            try:
                with target_path.open("wb") as f:
                    shutil.copyfileobj(uf.file, f)
            finally:
                try:
                    await uf.close()
                except Exception:
                    pass

            first_page = None
            last_page = None
            doc_type = "padrão"

            # Auto-detect INSS documents
            if auto_detect_inss:
                try:
                    # Extract only first page to detect document type
                    first_page_result = extract_ocr.extract_pdf(
                        str(target_path),
                        dpi=dpi,
                        poppler_path=poppler_path_final,
                        lang=lang,
                        first_page=1,
                        last_page=1,
                    )

                    if first_page_result['pages']:
                        first_page_text = first_page_result['pages'][0]['text'].lower()

                        inss_keywords = [
                            'inss',
                            'instituto nacional do seguro social',
                            'instituto nacional de seguro social',
                            'benefício previdenciário',
                            'auxílio-doença',
                            'perícia médica federal'
                        ]

                        is_inss = any(keyword in first_page_text for keyword in inss_keywords)

                        if is_inss:
                            doc_type = "INSS"
                            first_page = 1
                            last_page = 6
                            print(f'📄 {filename}: Documento INSS detectado - processando apenas páginas 1-6')
                        else:
                            print(f'📄 {filename}: Documento padrão - processando todas as páginas')
                except Exception as e:
                    print(f'⚠️ {filename}: Falha na detecção automática: {e}. Processando documento completo.')

            try:
                result = extract_ocr.extract_pdf(
                    str(target_path),
                    dpi=dpi,
                    poppler_path=poppler_path_final,
                    lang=lang,
                    first_page=first_page,
                    last_page=last_page,
                )
                result['document_type'] = doc_type
                result['filename'] = filename
            except Exception as e:
                raise HTTPException(
                    status_code=500,
                    detail={
                        "message": f"Falha ao processar {filename}.",
                        "error": str(e),
                        "hint": "No Windows, normalmente é preciso configurar POPPLER_PATH (pasta bin do Poppler).",
                    },
                )

            results.append(result)

    combined: Dict[str, Any] = {"extractions": results}
    return JSONResponse(content=combined)


# Static assets (optional; we serve index via route to avoid shadowing /api)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

