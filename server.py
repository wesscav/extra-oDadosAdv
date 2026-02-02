#!/usr/bin/env python3
from __future__ import annotations

import io
import os
import json
import time
import uuid
import tempfile
from typing import Any, Dict, List, Optional, Tuple

import pdfplumber
import pytesseract
from pdf2image import convert_from_bytes
from fastapi import Body, Depends, FastAPI, File, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from docx import Document
import firebase_admin
from firebase_admin import auth as firebase_auth
from firebase_admin import credentials as firebase_credentials

from analyze_with_openai import (
    DEFAULT_MODEL,
    FUNCTION_SCHEMA,
    build_text_from_ocr,
    call_openai_chat,
    extract_from_response,
    load_env,
    merge_structured_field,
    select_page_numbers_for_extraction,
)
from fill_template import prepare_replacements, process_document


APP_ROOT = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(APP_ROOT, "static")
TEMPLATE_PATH = os.path.join(APP_ROOT, "template.docx")

# armazenamento temporário em memória (token -> payload)
_STORE: Dict[str, Dict[str, Any]] = {}
_STORE_TTL_SECONDS = 60 * 30  # 30 minutos
_ALWAYS_NACIONALIDADE = "brasileiro(a)"

_FIREBASE_APP: Optional[firebase_admin.App] = None


def _init_firebase_admin() -> firebase_admin.App:
    """Inicializa firebase-admin (lazy) para validação de idToken."""
    global _FIREBASE_APP
    if _FIREBASE_APP is not None:
        return _FIREBASE_APP

    # 1) Path para serviceAccountKey.json
    sa_path = os.environ.get("FIREBASE_SERVICE_ACCOUNT_JSON")
    if sa_path:
        cred = firebase_credentials.Certificate(sa_path)
        _FIREBASE_APP = firebase_admin.initialize_app(cred, {"projectId": os.environ.get("FIREBASE_PROJECT_ID")})
        return _FIREBASE_APP

    # 2) JSON string do service account
    sa_json = os.environ.get("FIREBASE_SERVICE_ACCOUNT")
    if sa_json:
        info = json.loads(sa_json)
        cred = firebase_credentials.Certificate(info)
        _FIREBASE_APP = firebase_admin.initialize_app(cred, {"projectId": os.environ.get("FIREBASE_PROJECT_ID")})
        return _FIREBASE_APP

    # 3) GOOGLE_APPLICATION_CREDENTIALS (ADC) ou credenciais padrão
    options: Dict[str, Any] = {}
    project_id = os.environ.get("FIREBASE_PROJECT_ID")
    if project_id:
        options["projectId"] = project_id
    _FIREBASE_APP = firebase_admin.initialize_app(options=options or None)
    return _FIREBASE_APP


def require_firebase_user(authorization: Optional[str] = Header(default=None)) -> Dict[str, Any]:
    """Dependency do FastAPI: exige Authorization: Bearer <idToken> e valida com firebase-admin."""
    if not authorization or not isinstance(authorization, str):
        raise HTTPException(status_code=401, detail="Não autenticado. Envie Authorization: Bearer <idToken>.")
    if not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Cabeçalho Authorization inválido. Use Bearer <idToken>.")

    token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise HTTPException(status_code=401, detail="Token ausente. Use Authorization: Bearer <idToken>.")

    try:
        _init_firebase_admin()
        check_revoked = os.environ.get("FIREBASE_CHECK_REVOKED", "").strip() in ("1", "true", "yes", "on")
        decoded = firebase_auth.verify_id_token(token, check_revoked=check_revoked)
        if not isinstance(decoded, dict) or not decoded.get("uid"):
            raise ValueError("Decoded token inválido.")
        return decoded
    except Exception:
        # não vaza detalhes de validação/credencial para o cliente
        raise HTTPException(status_code=401, detail="Sessão inválida ou expirada. Faça login novamente.")


def _cleanup_store() -> None:
    now = time.time()
    expired = [k for k, v in _STORE.items() if (now - float(v.get("created_at", now))) > _STORE_TTL_SECONDS]
    for k in expired:
        _STORE.pop(k, None)


def _force_brazilian_nationality(structured: Dict[str, Any]) -> Dict[str, Any]:
    """Força a nacionalidade como 'brasileiro(a)' no JSON estruturado."""
    try:
        qa = structured.get("qualificacao_parte_autora")
        if not isinstance(qa, dict):
            qa = {}
            structured["qualificacao_parte_autora"] = qa
        qa["nacionalidade"] = _ALWAYS_NACIONALIDADE
    except Exception:
        # best-effort
        return structured
    return structured


def _lowercase_strings(obj: Any) -> Any:
    """Converte recursivamente valores string para minúsculas (best-effort)."""
    if isinstance(obj, str):
        return obj.lower()
    if isinstance(obj, list):
        return [_lowercase_strings(v) for v in obj]
    if isinstance(obj, dict):
        return {k: _lowercase_strings(v) for k, v in obj.items()}
    return obj

def _configure_ocr() -> Dict[str, Optional[str]]:
    """Configura Tesseract/Poppler via variáveis de ambiente (Windows-friendly).

    - TESSERACT_CMD: caminho do tesseract.exe
    - POPPLER_PATH: pasta do poppler/bin (para pdf2image)
    """
    tesseract_cmd = os.environ.get("TESSERACT_CMD")
    if tesseract_cmd:
        # pytesseract usa esse atributo para apontar para o executável
        pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
    poppler_path = os.environ.get("POPPLER_PATH")
    return {"tesseract_cmd": tesseract_cmd, "poppler_path": poppler_path}


def _should_fallback_to_ocr(text: str, min_chars: int) -> bool:
    # heurística simples: se o texto for muito curto, é provável que a página seja imagem/scan
    return len((text or "").strip()) < min_chars


def _ocr_page_from_pdf_bytes(
    file_bytes: bytes,
    page_number_1based: int,
    lang: str,
    dpi: int,
    poppler_path: Optional[str],
) -> str:
    images = convert_from_bytes(
        file_bytes,
        dpi=dpi,
        first_page=page_number_1based,
        last_page=page_number_1based,
        poppler_path=poppler_path,
    )
    if not images:
        return ""
    # config: PSM 6 costuma funcionar bem para páginas com blocos de texto
    return pytesseract.image_to_string(images[0], lang=lang, config="--psm 6")


def extract_pdf_hybrid_text(
    file_bytes: bytes,
    source_name: str,
    *,
    ocr_lang: str = "por",
    ocr_min_chars: int = 30,
    ocr_dpi: int = 300,
) -> Dict[str, Any]:
    """Extrai texto do PDF (pdfplumber) com fallback para OCR (Tesseract) por página."""
    cfg = _configure_ocr()
    pages: List[Dict[str, Any]] = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            method = "pdfplumber"
            if _should_fallback_to_ocr(text, ocr_min_chars):
                try:
                    ocr_text = _ocr_page_from_pdf_bytes(
                        file_bytes,
                        page_number_1based=i,
                        lang=ocr_lang,
                        dpi=ocr_dpi,
                        poppler_path=cfg.get("poppler_path"),
                    )
                    if ocr_text and len(ocr_text.strip()) >= len(text.strip()):
                        text = ocr_text
                        method = "ocr"
                except Exception:
                    # se OCR falhar, mantemos o texto original (mesmo que vazio)
                    pass

            # words não são usados no pipeline atual; manter vazio reduz payload/tempo
            pages.append({"page_number": i, "text": text, "words": [], "method": method})
    return {"source": source_name, "page_count": len(pages), "pages": pages}


def _summarize_structured(structured: Dict[str, Any]) -> Dict[str, Any]:
    """Gera um resumo “human-friendly” do JSON estruturado para o modal."""
    def g(path: List[str]) -> Optional[Any]:
        cur: Any = structured
        for p in path:
            if not isinstance(cur, dict):
                return None
            cur = cur.get(p)
            if cur is None:
                return None
        return cur

    return {
        "qualificacao": {
            "nome": g(["qualificacao_parte_autora", "nome"]),
            "cpf": g(["qualificacao_parte_autora", "cpf"]),
            "endereco": g(["qualificacao_parte_autora", "endereco_completo"]),
            "representante_legal": g(["qualificacao_parte_autora", "representante_legal_nome"]),
        },
        "inss": {
            "nb": g(["dados_requerimento_inss", "numero_beneficio_NB"]) or g(["dados_processuais", "numero_beneficio_NB_repetido"]),
            "der": g(["dados_requerimento_inss", "DER_data_entrada_requerimento"]),
        },
        "laudo_principal": {
            "deficiencia": g(["dados_medicos", "laudo_principal", "deficiencia_constatada"]),
            "cid": g(["dados_medicos", "laudo_principal", "CID_da_doenca"]),
            "data": g(["dados_medicos", "laudo_principal", "data_do_laudo"]),
            "medico": g(["dados_medicos", "laudo_principal", "nome_do_medico"]),
        },
        "relatorio_escolar": {
            "data_emissao": g(["dados_medicos", "relatorio_escolar", "data_emissao"]),
            "primeiro_nome_autor": g(["dados_medicos", "relatorio_escolar", "primeiro_nome_do_autor"]),
        },
    }


def analyze_extractions_with_openai(
    extractions: List[Dict[str, Any]],
    model: str,
    pages_per_call: int,
    delay_between_calls: float,
    inss_max_pages: int,
    inss_min_total_pages: int,
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """Roda a etapa de estruturação (OpenAI) por documento, retornando resultado + metadados por doc."""
    system_msg = (
        "Você é um assistente que analisa laudos e extrai campos jurídicos e médicos. "
        "Retorne apenas JSON seguindo o schema de função. Se o dado não existir, retorne null. "
        "Se houver baixa confiança, inclua o valor e marque '[confiança baixa]'."
    )

    structured_result: Dict[str, Any] = {}
    per_doc: List[Dict[str, Any]] = []

    INSS_KEYWORDS = ["inss", "instituto nacional", "do seguro social"]

    def _is_inss_doc(ex: Dict[str, Any]) -> bool:
        # Documento do INSS: detecta por palavras-chave na página 1.
        # Não depende do total de páginas, para garantir que analisaremos as 6 primeiras páginas
        # mesmo em PDFs menores/recortados.
        t1 = ""
        if isinstance(ex.get("pages"), list) and ex["pages"]:
            t1 = (ex["pages"][0].get("text") or "")
        t1 = t1.lower()
        return any(k in t1 for k in INSS_KEYWORDS)

    def _pages_containing(ex: Dict[str, Any], pages: List[int], needle: str) -> List[int]:
        n = (needle or "").strip().lower()
        hits: List[int] = []
        for pn in pages:
            for p in ex.get("pages", []) or []:
                if p.get("page_number") == pn:
                    if n in ((p.get("text") or "").lower()):
                        hits.append(pn)
                    break
        return hits

    def _is_laudo_doc(ex: Dict[str, Any]) -> bool:
        t1 = ""
        if isinstance(ex.get("pages"), list) and ex["pages"]:
            t1 = (ex["pages"][0].get("text") or "").lower()
        return ("laudo" in t1) and ("médic" in t1 or "medic" in t1 or "crm" in t1 or "rqe" in t1)

    def _score_psiquiatria(ex: Dict[str, Any], pages: List[int]) -> int:
        score = 0
        needles = ["psiquiatr", "psiquiátr", "psiquiatria", "psiquiatra"]
        # olha só nas duas primeiras páginas analisadas
        for pn in pages[: min(len(pages), 2)]:
            txt = ""
            for p in ex.get("pages", []) or []:
                if p.get("page_number") == pn:
                    txt = (p.get("text") or "").lower()
                    break
            for n in needles:
                score += txt.count(n)
        return score

    # pré-calcula páginas analisadas e papéis dos laudos (principal x segundo)
    pages_by_source: Dict[str, List[int]] = {}
    laudo_candidates: List[Tuple[str, int]] = []
    for ex_idx, ex in enumerate(extractions, start=1):
        source = ex.get("source") or f"documento_{ex_idx}"
        pages = select_page_numbers_for_extraction(
            ex,
            selected_pages=None,
            inss_max_pages=inss_max_pages,
            inss_min_total_pages=inss_min_total_pages,
        )
        pages_by_source[source] = pages
        if _is_laudo_doc(ex):
            laudo_candidates.append((source, _score_psiquiatria(ex, pages)))

    laudo_roles: Dict[str, str] = { (ex.get("source") or f"documento_{i+1}") : "none" for i, ex in enumerate(extractions) }
    if len(laudo_candidates) >= 2:
        segundo = sorted(enumerate(laudo_candidates), key=lambda it: (-it[1][1], it[0]))[0][1][0]
        principal = next((s for (s, _) in laudo_candidates if s != segundo), laudo_candidates[0][0])
        laudo_roles[principal] = "principal"
        laudo_roles[segundo] = "segundo"
    elif len(laudo_candidates) == 1:
        laudo_roles[laudo_candidates[0][0]] = "principal"

    for ex_idx, ex in enumerate(extractions, start=1):
        source = ex.get("source") or f"documento_{ex_idx}"
        page_numbers = pages_by_source.get(source) or []
        per_doc.append(
            {
                "source": source,
                "page_count": ex.get("page_count"),
                "pages_analyzed": page_numbers,
            }
        )

        if not page_numbers:
            continue

        is_inss_doc = _is_inss_doc(ex)
        outorgante_pages = _pages_containing(ex, page_numbers, "outorgante") if is_inss_doc else []
        # fallback para casos onde a seção esteja rotulada de outra forma
        if is_inss_doc and not outorgante_pages:
            outorgante_pages = _pages_containing(ex, page_numbers, "procuração")
        if is_inss_doc and not outorgante_pages:
            outorgante_pages = _pages_containing(ex, page_numbers, "procuracao")

        laudo_role = laudo_roles.get(source, "none")

        chunks = [page_numbers] if pages_per_call <= 0 else [page_numbers[i : i + pages_per_call] for i in range(0, len(page_numbers), pages_per_call)]
        for chunk_idx, chunk in enumerate(chunks):
            chunk_text = build_text_from_ocr(ex, pages=chunk)
            if not chunk_text.strip():
                continue

            personal_data_policy = (
                "POLÍTICA DE DADOS PESSOAIS (OBRIGATÓRIA):\n"
                "- Os campos de 'qualificacao_parte_autora' representam dados pessoais do paciente/parte autora.\n"
            )
            if is_inss_doc:
                personal_data_policy += (
                    "- ESTE documento é o PDF do INSS.\n"
                    f"- Extraia 'qualificacao_parte_autora' SOMENTE a partir da(s) página(s) que contém 'OUTORGANTE'. Páginas detectadas: {outorgante_pages or 'nenhuma'}.\n"
                    "- Se não houver informação suficiente nessas páginas, retorne null.\n"
                    "- Nunca use 'Horlando Braga Filho' como dados pessoais do paciente/parte autora.\n"
                )
            else:
                personal_data_policy += (
                    "- ESTE documento NÃO é o PDF do INSS.\n"
                    "- Portanto, retorne TODOS os campos de 'qualificacao_parte_autora' como null.\n"
                )

            laudo_policy = (
                "POLÍTICA DOS LAUDOS (OBRIGATÓRIA):\n"
                "- Existem 2 laudos médicos distintos. Não misture médico/especialidade/datas/CIDs entre eles.\n"
            )
            if laudo_role == "principal":
                laudo_policy += (
                    "- ESTE documento é o PRIMEIRO LAUDO (laudo_principal). Preencha COMPLETAMENTE 'dados_medicos.laudo_principal'.\n"
                    "- Retorne 'dados_medicos.laudo_psiquiatrico_segundo_laudo' como null.\n"
                )
            elif laudo_role == "segundo":
                laudo_policy += (
                    "- ESTE documento é o SEGUNDO LAUDO (laudo_psiquiatrico_segundo_laudo). Preencha COMPLETAMENTE 'dados_medicos.laudo_psiquiatrico_segundo_laudo'.\n"
                    "- Retorne 'dados_medicos.laudo_principal' como null.\n"
                )
            else:
                laudo_policy += (
                    "- Se este documento não for um dos laudos, retorne ambos os blocos de laudo como null.\n"
                )

            user_msg = (
                f"Documento fonte: {source}\n"
                "Analise o texto a seguir e preencha os campos do schema. Retorne somente o JSON.\n"
                + personal_data_policy
                + laudo_policy
                + "Texto:\n"
                + chunk_text
            )

            messages = [
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_msg},
            ]

            resp = call_openai_chat(model, messages, [FUNCTION_SCHEMA])
            chunk_structured = extract_from_response(resp)
            if not structured_result:
                structured_result = chunk_structured
            else:
                merge_structured_field(structured_result, chunk_structured)

            if (chunk_idx < len(chunks) - 1) and delay_between_calls > 0:
                time.sleep(delay_between_calls)

        if (ex_idx < len(extractions)) and delay_between_calls > 0:
            time.sleep(delay_between_calls)

    return structured_result, per_doc


def generate_docx_from_structured(structured: Dict[str, Any], template_path: str) -> str:
    """Gera um DOCX preenchido e retorna o caminho do arquivo gerado (temp)."""
    replacements = prepare_replacements(structured)
    if os.path.exists(template_path):
        doc = Document(template_path)
        process_document(doc, replacements)
    else:
        doc = Document()
        doc.add_paragraph("Template não encontrado. Preencha/ajuste 'template.docx'.")
        doc.add_paragraph("Campos detectados:")
        for k, v in replacements.items():
            doc.add_paragraph(f"[{k}] = {v}")

    fd, out_path = tempfile.mkstemp(prefix="template_gerado_", suffix=".docx")
    os.close(fd)
    doc.save(out_path)
    return out_path


app = FastAPI(title="Extração de dados (PDF → JSON → DOCX)")

if os.path.isdir(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.on_event("startup")
def _startup() -> None:
    # carrega .env/.ENV se existir
    load_env(None)


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    index_path = os.path.join(STATIC_DIR, "index.html")
    if not os.path.exists(index_path):
        raise HTTPException(status_code=500, detail="static/index.html não encontrado.")
    with open(index_path, "r", encoding="utf-8") as f:
        return f.read()


@app.get("/login", response_class=HTMLResponse)
def login_page() -> str:
    login_path = os.path.join(STATIC_DIR, "login.html")
    if not os.path.exists(login_path):
        raise HTTPException(status_code=500, detail="static/login.html não encontrado.")
    with open(login_path, "r", encoding="utf-8") as f:
        return f.read()


@app.post("/api/extract")
async def api_extract(
    _user: Dict[str, Any] = Depends(require_firebase_user),
    files: List[UploadFile] = File(...),
    model: str = DEFAULT_MODEL,
    pages_per_call: int = 0,
    delay_between_calls: float = 0.0,
    inss_max_pages: int = 6,
    inss_min_total_pages: int = 20,
    ocr_lang: str = "por",
    ocr_min_chars: int = 30,
    ocr_dpi: int = 300,
) -> Dict[str, Any]:
    _cleanup_store()

    if len(files) != 4:
        raise HTTPException(status_code=400, detail="Envie exatamente 4 arquivos PDF.")

    extractions: List[Dict[str, Any]] = []
    for f in files:
        if not (f.filename or "").lower().endswith(".pdf"):
            raise HTTPException(status_code=400, detail=f"Arquivo não é PDF: {f.filename}")
        content = await f.read()
        if not content:
            raise HTTPException(status_code=400, detail=f"Arquivo vazio: {f.filename}")
        extractions.append(
            extract_pdf_hybrid_text(
                content,
                f.filename or "documento.pdf",
                ocr_lang=ocr_lang,
                ocr_min_chars=ocr_min_chars,
                ocr_dpi=ocr_dpi,
            )
        )

    try:
        structured, per_doc = analyze_extractions_with_openai(
            extractions=extractions,
            model=model,
            pages_per_call=pages_per_call,
            delay_between_calls=delay_between_calls,
            inss_max_pages=inss_max_pages,
            inss_min_total_pages=inss_min_total_pages,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    if not structured:
        raise HTTPException(status_code=500, detail="A API não retornou nenhum conteúdo estruturado.")

    structured = _force_brazilian_nationality(structured)
    structured = _lowercase_strings(structured)

    token = str(uuid.uuid4())
    _STORE[token] = {"created_at": time.time(), "structured": structured}

    return {
        "token": token,
        "per_document": per_doc,
        "summary": _summarize_structured(structured),
        "structured": structured,
    }


@app.post("/api/generate-docx")
def api_generate_docx(
    payload: Dict[str, Any] = Body(...),
    _user: Dict[str, Any] = Depends(require_firebase_user),
) -> FileResponse:
    _cleanup_store()
    token = payload.get("token")
    if not token or not isinstance(token, str):
        raise HTTPException(status_code=400, detail="Campo obrigatório: token")
    item = _STORE.get(token)
    if not item:
        raise HTTPException(status_code=404, detail="Token não encontrado ou expirado. Refaça a extração.")

    structured_override = payload.get("structured")
    if structured_override is not None:
        if not isinstance(structured_override, dict):
            raise HTTPException(status_code=400, detail="Campo 'structured' deve ser um objeto JSON.")
        structured = structured_override
    else:
        structured = item.get("structured")
        if not isinstance(structured, dict):
            raise HTTPException(status_code=500, detail="Conteúdo estruturado inválido no servidor.")

    structured = _force_brazilian_nationality(structured)
    structured = _lowercase_strings(structured)

    out_path = generate_docx_from_structured(structured, TEMPLATE_PATH)
    # opcional: invalidar token após uso (evita reuso)
    _STORE.pop(token, None)

    return FileResponse(
        out_path,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename="template_gerado.docx",
    )

