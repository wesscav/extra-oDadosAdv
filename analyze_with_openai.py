#!/usr/bin/env python3
# python analyze_with_openai.py extraction_output.json -o extraction_structured.json
"""Call OpenAI Chat Completions with function-calling to extract structured fields.

Usage:
  python analyze_with_openai.py extraction_output.json -o extraction_structured.json

This script:
 - reads the OCR JSON produced by `extract_ocr.py`
 - extracts the `text` fields (optionally by page)
 - calls the OpenAI Chat API using a function schema to force JSON output
 - saves the returned structured JSON to disk

Security: set OPENAI_API_KEY in your environment, or create a `.env` file with
OPENAI_API_KEY="sk-..." (do not commit .env to source control).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

try:
    import openai
except Exception:
    openai = None

try:
    from dotenv import load_dotenv
except Exception:
    load_dotenv = None

from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type


DEFAULT_MODEL = "gpt-4o-mini"  # Modelo mais econômico (~60% mais barato) mantendo boa acurácia para extração estruturada

# Heurística para o "documento grande do INSS":
# - se a página 1 contiver algum desses termos
# - e o documento for "grande" (>= --inss-min-total-pages)
# então limitamos a análise às primeiras --inss-max-pages páginas.
INSS_KEYWORDS = [
    "inss",
    "instituto nacional",
    "do seguro social",
    "INSS",
    "Instituto Nacional do Seguro Social"
]
FUNCTION_SCHEMA = {
    "name": "extrair_campos_laudo",
    "description": "Extrai campos administrativos, médicos e processuais de um texto de laudo.",
    "parameters": {
        "type": "object",
        "properties": {
            "qualificacao_parte_autora": {
                "type": "object",
                "properties": {
                    "nome": {"type": ["string", "null"]},
                    "nacionalidade": {"type": ["string", "null"]},
                    "estado_civil": {"type": ["string", "null"]},
                    "profissao": {"type": ["string", "null"]},
                    "cpf": {"type": ["string", "null"]},
                    "representante_legal_nome": {"type": ["string", "null"]},
                    "representante_legal_cpf": {"type": ["string", "null"]},
                    "representante_legal_rg": {"type": ["string", "null"]},
                    "endereco_completo": {"type": ["string", "null"]}
                }
            },
            "dados_requerimento_inss": {
                "type": "object",
                "properties": {
                    "numero_beneficio_NB": {"type": ["string", "null"]},
                    "DER_data_entrada_requerimento": {"type": ["string", "null"]}
                }
            },
            "dados_medicos": {
                "type": "object",
                "properties": {
                    "laudo_principal": {
                        "type": "object",
                        "properties": {
                            "deficiencia_constatada": {"type": ["string", "null"]},
                            "CID_da_doenca": {"type": ["string", "null"]},
                            "data_do_laudo": {"type": ["string", "null"]},
                            "especialidade_do_medico": {"type": ["string", "null"]},
                            "nome_do_medico": {"type": ["string", "null"]},
                            "trecho_clinico_relevante": {"type": ["string", "null"]}
                        }
                    },
                    "relatorio_escolar": {
                        "type": "object",
                        "properties": {
                            "data_emissao": {"type": ["string", "null"]},
                            "primeiro_nome_do_autor": {"type": ["string", "null"]},
                            "resumo": {"type": ["string", "null"]},
                            "resumo_continuacao": {"type": ["string", "null"]}
                        }
                    },
                    "laudo_psiquiatrico_segundo_laudo": {
                        "type": "object",
                        "properties": {
                            "data_segundo_laudo": {"type": ["string", "null"]},
                            "nome_medico": {"type": ["string", "null"]},
                            "resumo": {"type": ["string", "null"]}
                        }
                    },
                    "diagnostico_final_tratamento": {
                        "type": "object",
                        "properties": {
                            "conclusao_medica": {"type": ["string", "null"]},
                            "deficiencia_e_CID": {"type": ["string", "null"]},
                            "deficiencia_associada_e_CID": {"type": ["string", "null"]},
                            "medicamento_prescrito": {"type": ["string", "null"]},
                            "finalidade_medicamento": {"type": ["string", "null"]}
                        }
                    }
                }
            },
            "dados_socioeconomicos": {
                "type": "object",
                "properties": {
                    "grau_parentesco_CadUnico": {"type": ["string", "null"]},
                    "nome_avo": {"type": ["string", "null"]},
                    "valor_exato_aposentadoria": {"type": ["string", "null"]},
                    "paginas_laudo_social": {"type": ["string", "null"]}
                }
            },
            "dados_processuais": {
                "type": "object",
                "properties": {
                    "numero_beneficio_NB_repetido": {"type": ["string", "null"]},
                    "locais_repeticao": {"type": ["string", "null"]},
                    "observacao_inconsistencia": {"type": ["string", "null"]}
                }
            }
        }
    }
}


def load_env(dotenv_path: Optional[str] = None) -> None:
    """Load .env if present and set environment variables."""
    if load_dotenv is None:
        return
    if dotenv_path and os.path.exists(dotenv_path):
        load_dotenv(dotenv_path)
    else:
        # try default .env or .ENV
        for fn in (".env", ".ENV"):
            if os.path.exists(fn):
                load_dotenv(fn)
                break


def read_ocr_json(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def normalize_input_to_ocr(obj: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize input JSON to a single OCR-like object with 'pages'.

    If the input is a combined file with key 'extractions' (a list of OCR objects),
    concatenate their pages into a single pages list while preserving a source tag.
    Otherwise, assume the input already follows the OCR format and return it.
    """
    if not isinstance(obj, dict):
        raise RuntimeError("Invalid OCR JSON: expected an object at root")

    if "extractions" in obj and isinstance(obj["extractions"], list):
        combined_pages: List[Dict[str, Any]] = []
        file_idx = 1
        for ex in obj["extractions"]:
            source = ex.get("source") or f"extraction_{file_idx}"
            for p in ex.get("pages", []):
                pn = p.get("page_number")
                text = p.get("text", "")
                combined_pages.append({
                    "page_number": len(combined_pages) + 1,
                    "source": source,
                    "orig_page_number": pn,
                    "text": f"[source: {source}] [orig_page: {pn}]\n" + (text or ""),
                })
            file_idx += 1

        return {"source": "combined", "page_count": len(combined_pages), "pages": combined_pages}

    # if already in expected format, return as-is
    return obj


def build_text_from_ocr(ocr: Dict[str, Any], pages: Optional[List[int]] = None) -> str:
    """Concatenate page text. If pages is given, include only those page numbers."""
    parts: List[str] = []
    for p in ocr.get("pages", []):
        pn = p.get("page_number")
        if pages is None or pn in pages:
            t = p.get("text", "")
            if t:
                parts.append(f"[page {pn}]\n" + t.strip())
    return "\n\n".join(parts)


def extract_page_numbers(ocr: Dict[str, Any], selected: Optional[List[int]]) -> List[int]:
    available = [p.get("page_number") for p in ocr.get("pages", []) if isinstance(p.get("page_number"), int)]
    if selected:
        return [pn for pn in selected if pn in available]
    return available


def chunk_page_numbers(pages: List[int], chunk_size: int) -> List[List[int]]:
    if chunk_size <= 0:
        return [pages]
    return [pages[i : i + chunk_size] for i in range(0, len(pages), chunk_size)]


def _get_total_pages(ocr_like: Dict[str, Any]) -> int:
    """Best-effort total pages for a single extraction object."""
    pc = ocr_like.get("page_count")
    if isinstance(pc, int) and pc > 0:
        return pc
    pages = ocr_like.get("pages")
    if isinstance(pages, list):
        return len(pages)
    return 0


def _get_page_text(ocr_like: Dict[str, Any], page_number: int) -> str:
    """Fetch the text for a given page_number (best-effort)."""
    for p in ocr_like.get("pages", []) or []:
        if p.get("page_number") == page_number:
            return (p.get("text") or "")
    return ""


def _contains_inss_keywords(text: str) -> bool:
    t = (text or "").lower()
    return any(k in t for k in INSS_KEYWORDS)


def _is_inss_document(ocr_like: Dict[str, Any], inss_min_total_pages: int) -> bool:
    """Heurística: documento INSS = palavras-chave na página 1.

    Observação:
    Antes exigíamos "documento grande" (>= inss_min_total_pages). Isso falha quando o PDF do
    INSS tem poucas páginas ou quando a extração vem "recortada". Para garantir a regra
    pedida (analisar as 6 primeiras páginas do INSS), classificamos como INSS apenas pela
    presença de palavras-chave na página 1.
    """
    first_page_text = _get_page_text(ocr_like, 1)
    return _contains_inss_keywords(first_page_text)


def _find_pages_containing(ocr_like: Dict[str, Any], pages: List[int], needle: str) -> List[int]:
    n = (needle or "").strip().lower()
    if not n:
        return []
    hits: List[int] = []
    for pn in pages:
        txt = _get_page_text(ocr_like, pn)
        if n in (txt or "").lower():
            hits.append(pn)
    return hits


def _is_laudo_document(ocr_like: Dict[str, Any]) -> bool:
    """Heurística simples para detectar se é um laudo médico."""
    t1 = _get_page_text(ocr_like, 1).lower()
    return ("laudo" in t1) and ("médic" in t1 or "medic" in t1 or "crm" in t1 or "rqe" in t1)


def _score_psiquiatria(ocr_like: Dict[str, Any], pages: List[int]) -> int:
    """Score para identificar laudo psiquiátrico/segundo laudo."""
    score = 0
    needles = ["psiquiatr", "psiquiátr", "psiquiatria", "psiquiatra"]
    for pn in pages[: min(len(pages), 2)]:  # olha no máximo 2 páginas iniciais selecionadas
        txt = (_get_page_text(ocr_like, pn) or "").lower()
        for n in needles:
            score += txt.count(n)
    return score


def _assign_laudo_roles(
    extractions: List[Dict[str, Any]],
    selected_pages_by_source: Dict[str, List[int]],
) -> Dict[str, str]:
    """Define papéis para laudos: 'principal' e 'segundo' sem misturar.

    Regra:
    - detecta documentos que parecem 'laudo'
    - escolhe o mais "psiquiatria" como 'segundo'
    - o outro como 'principal'
    - os demais: 'none'
    """
    laudos: List[Tuple[str, int]] = []  # (source, score)
    for ex in extractions:
        source = ex.get("source") or ""
        pages = selected_pages_by_source.get(source, []) or []
        if _is_laudo_document(ex):
            laudos.append((source, _score_psiquiatria(ex, pages)))

    roles: Dict[str, str] = {}
    for ex in extractions:
        s = ex.get("source") or ""
        roles[s] = "none"

    if len(laudos) >= 2:
        # escolhe 'segundo' pelo maior score; desempate pela ordem de aparição
        segundo_source = sorted(enumerate(laudos), key=lambda it: (-it[1][1], it[0]))[0][1][0]
        # 'principal' = primeiro laudo diferente do segundo na ordem original
        principal_source = next((s for (s, _) in laudos if s != segundo_source), laudos[0][0])
        roles[principal_source] = "principal"
        roles[segundo_source] = "segundo"
    elif len(laudos) == 1:
        roles[laudos[0][0]] = "principal"

    return roles


def select_page_numbers_for_extraction(
    ocr_like: Dict[str, Any],
    selected_pages: Optional[List[int]],
    inss_max_pages: int,
    inss_min_total_pages: int,
) -> List[int]:
    """Select which pages to include for ONE document/extraction.

    Precedence:
    - if selected_pages is provided, use only those pages (intersection with available)
    - else, apply INSS heuristic to limit pages for large INSS documents
    - otherwise include all available pages
    """
    available = [p.get("page_number") for p in ocr_like.get("pages", []) if isinstance(p.get("page_number"), int)]
    available = sorted(set(available))
    if not available:
        return []

    if selected_pages:
        return [pn for pn in selected_pages if pn in available]

    # Regra do INSS: se a página 1 indicar INSS, analise apenas as N primeiras páginas
    # (default: 6). Não depende do total de páginas.
    first_page_text = _get_page_text(ocr_like, 1)
    if _contains_inss_keywords(first_page_text):
        cap = max(1, int(inss_max_pages))
        return [pn for pn in available if pn <= cap]

    return available


def merge_structured_field(target: Dict[str, Any], source: Dict[str, Any]) -> None:
    for key, source_value in source.items():
        target_value = target.get(key)
        if isinstance(source_value, dict):
            if not isinstance(target_value, dict):
                target[key] = {}
                target_value = target[key]
            merge_structured_field(target_value, source_value)
        else:
            if source_value is not None:
                target[key] = source_value
            elif key not in target:
                target[key] = None


@retry(stop=stop_after_attempt(6), wait=wait_exponential(multiplier=2, min=2, max=60),
    retry=retry_if_exception_type(Exception))
def call_openai_chat(model: str, messages: List[Dict[str, Any]], functions: List[Dict[str, Any]]) -> Dict[str, Any]:
    if openai is None:
        raise RuntimeError("Python package 'openai' is not installed. Run pip install -r requirements.txt")

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY environment variable is not set")

    # Use new OpenAI SDK v1+ API (openai >= 1.0.0)
    print(f"[OpenAI] Chamando API com modelo: {model}")
    
    try:
        # Convert functions to tools format (new API)
        tools = [{"type": "function", "function": func} for func in functions]
        
        # Create client instance
        client = openai.OpenAI(api_key=api_key)
        
        # Call chat completions with tools
        resp = client.chat.completions.create(
            model=model,
            messages=messages,
            tools=tools,
            tool_choice="auto",
            temperature=0,
            max_tokens=2000,
        )
        
        print(f"[OpenAI] Chamada bem-sucedida")
        
        # Convert response to dict format compatible with old code
        result = {
            "id": resp.id,
            "object": resp.object,
            "created": resp.created,
            "model": resp.model,
            "choices": []
        }
        
        for choice in resp.choices:
            choice_dict = {
                "index": choice.index,
                "message": {
                    "role": choice.message.role,
                    "content": choice.message.content,
                },
                "finish_reason": choice.finish_reason
            }
            
            # Handle tool calls (new format) -> convert to function_call (old format)
            if choice.message.tool_calls:
                tool_call = choice.message.tool_calls[0]  # Get first tool call
                choice_dict["message"]["function_call"] = {
                    "name": tool_call.function.name,
                    "arguments": tool_call.function.arguments
                }
            
            result["choices"].append(choice_dict)
        
        return result
        
    except Exception as e:
        msg = str(e)
        print(f"[OpenAI] Erro na chamada: {type(e).__name__}: {msg}")
        
        # Tenta extrair mais detalhes do erro
        if hasattr(e, 'response'):
            print(f"[OpenAI] Response do erro: {e.response}")
        if hasattr(e, 'status_code'):
            print(f"[OpenAI] Status code: {e.status_code}")
        if hasattr(e, 'body'):
            print(f"[OpenAI] Body do erro: {e.body}")
        
        # Handle rate limit
        if "RateLimitError" in type(e).__name__:
            raise RuntimeError("Rate limit reached. Try again after a short wait, reduce request rate or check your account usage/quotas on platform.openai.com.")
        
        # re-raise the original error
        raise


def extract_from_response(resp: Dict[str, Any]) -> Dict[str, Any]:
    choices = resp.get("choices") or []
    if not choices:
        raise RuntimeError("No choices returned from OpenAI")
    message = choices[0].get("message") or choices[0].get("delta") or {}

    # If model used function calling, arguments will be in message["function_call"]["arguments"]
    func = message.get("function_call")
    if func and func.get("arguments"):
        args_str = func["arguments"]
        try:
            obj = json.loads(args_str)
        except Exception:
            # sometimes the model returns single quotes or trailing commas; attempt to sanitize
            try:
                obj = json.loads(args_str.replace("'", '"'))
            except Exception as e:
                raise RuntimeError(f"Failed to parse function arguments as JSON: {e}\n{args_str}")
        return obj

    # Fallback: try to parse message content
    content = message.get("content") or ""
    content = content.strip()
    if not content:
        raise RuntimeError("No content in response message")
    try:
        return json.loads(content)
    except Exception as e:
        raise RuntimeError(f"Could not parse model content as JSON: {e}\nContent: {content}")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Send OCR text to OpenAI and get structured JSON via function-calling")
    parser.add_argument("input", help="OCR JSON file produced by extract_ocr.py")
    parser.add_argument("-o", "--output", default="extraction_structured.json", help="Output JSON file")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Model to use (must support function-calling)")
    parser.add_argument("--dotenv", default=None, help="Path to .env or .ENV file to load OPENAI_API_KEY from")
    parser.add_argument("--pages", nargs="*", type=int, help="Optional list of page numbers to include (e.g. --pages 1 2)")
    parser.add_argument(
        "--inss-max-pages",
        type=int,
        default=6,
        help=(
            "Quando a página 1 contiver palavras-chave do INSS e o documento for grande "
            "(>= --inss-min-total-pages), limita a análise às primeiras N páginas (default: 6)."
        ),
    )
    parser.add_argument(
        "--inss-min-total-pages",
        type=int,
        default=20,
        help="Mínimo de páginas para considerar o documento 'grande' na heurística do INSS (default: 20).",
    )
    parser.add_argument(
        "--pages-per-call",
        type=int,
        default=0,
        help="Chunk size (number of pages) per OpenAI call; 0 means send all pages in one call",
    )
    parser.add_argument(
        "--delay-between-calls",
        type=float,
        default=0.0,
        help="Seconds to wait between OpenAI requests when using page chunking",
    )
    args = parser.parse_args(argv)

    load_env(args.dotenv)

    if not os.path.exists(args.input):
        print(f"Input file not found: {args.input}", file=sys.stderr)
        return 2

    system_msg = (
        "Você é um assistente que analisa laudos e extrai campos jurídicos e médicos. "
        "Retorne apenas JSON seguindo o schema de função. Se o dado não existir, retorne null. "
        "Datas: use formato DD/MM/YYYY (ex: 05/12/2024). "
        "Se houver baixa confiança, inclua o valor e marque '[confiança baixa]'."
    )

    structured_result: Dict[str, Any] = {}
    ocr_raw = read_ocr_json(args.input)

    # Se for um JSON combinado (vários PDFs), processe cada extração separadamente
    # para conseguir aplicar regras por documento (ex.: limitar páginas do INSS).
    if isinstance(ocr_raw, dict) and isinstance(ocr_raw.get("extractions"), list):
        extractions: List[Dict[str, Any]] = [ex for ex in ocr_raw.get("extractions", []) if isinstance(ex, dict)]
        if not extractions:
            print("Nenhuma extração válida foi encontrada em 'extractions'.", file=sys.stderr)
            return 3

        # pré-calcula páginas selecionadas por documento (para heurísticas de papéis)
        selected_pages_by_source: Dict[str, List[int]] = {}
        for ex_idx, ex in enumerate(extractions, start=1):
            source = ex.get("source") or f"extraction_{ex_idx}"
            page_numbers = select_page_numbers_for_extraction(
                ex,
                args.pages,
                args.inss_max_pages,
                args.inss_min_total_pages,
            )
            selected_pages_by_source[source] = page_numbers

        laudo_roles_by_source = _assign_laudo_roles(extractions, selected_pages_by_source)

        for ex_idx, ex in enumerate(extractions, start=1):
            source = ex.get("source") or f"extraction_{ex_idx}"
            page_numbers = selected_pages_by_source.get(source) or []
            if not page_numbers:
                continue

            # Regras de extração para dados pessoais:
            # - dados pessoais do paciente/parte autora (qualificacao_parte_autora.*) devem vir do PDF do INSS.
            # - nunca usar "Horlando Braga Filho" ou dados de "Procuradores / Representantes Legais" como dados pessoais do paciente.
            is_inss_doc = _is_inss_document(ex, args.inss_min_total_pages)

            laudo_role = laudo_roles_by_source.get(source, "none")

            chunks = chunk_page_numbers(page_numbers, args.pages_per_call)
            if not chunks:
                continue

            for chunk_idx, chunk in enumerate(chunks):
                chunk_text = build_text_from_ocr(ex, pages=chunk)
                if not chunk_text.strip():
                    continue

                personal_data_hint = ""  # análise em todas as páginas do INSS, sem restrição a seção específica

                personal_data_policy = (
                    "POLÍTICA DE DADOS PESSOAIS (OBRIGATÓRIA):\n"
                    "- Os campos de 'qualificacao_parte_autora' (nome, nacionalidade, estado_civil, profissao, cpf, endereco_completo,\n"
                    "  representante_legal_nome/cpf/rg) representam dados pessoais do paciente/parte autora.\n"
                )
                if is_inss_doc:
                    personal_data_policy += (
                        "- ESTE documento é o PDF do INSS.\n"
                        f"- Analise o conteúdo de todas as {len(page_numbers)} páginas e extraia 'qualificacao_parte_autora' de qualquer parte relevante do documento.\n"
                        "- ATENÇÃO: NUNCA use dados da seção 'Procuradores / Representantes Legais' como dados do paciente.\n"
                        "  - IGNORE 'Horlando Braga Filho' e seu CPF (028.951.113-59) - ele é o advogado/procurador, NÃO o paciente.\n"
                        "\n"
                        "REGRAS PARA REPRESENTANTE LEGAL (CRÍTICO):\n"
                        "- Procure por seções com o título 'PROCURAÇÃO' ou texto contendo 'Outorgante' e 'representado (a) por'.\n"
                        "- FORMATO TÍPICO DA PROCURAÇÃO:\n"
                        "  'PROCURAÇÃO\n"
                        "   Outorgante: [Nome do Paciente], brasileiro, [estado civil], [profissão], CPF: XXX.XXX.XXX-XX e RG: XXXXXXXXX,\n"
                        "   representado (a) por [Nome do Representante Legal], CPF: XXX.XXX.XXX-XX e RG: XXXXXXXXX'\n"
                        "\n"
                        "- REGRA DE EXTRAÇÃO:\n"
                        "  1. OUTORGANTE = PACIENTE (pessoa que dá a procuração) → Preencha 'nome', 'cpf' da qualificacao_parte_autora\n"
                        "  2. REPRESENTADO POR = REPRESENTANTE LEGAL (quem representa o paciente) → Preencha:\n"
                        "     - representante_legal_nome: nome completo que vem APÓS 'representado (a) por' ou 'representado(a) por'\n"
                        "     - representante_legal_cpf: CPF que vem logo após o nome do representante\n"
                        "     - representante_legal_rg: RG que vem logo após o CPF do representante\n"
                        "\n"
                        "- EXEMPLO REAL:\n"
                        "  Texto: 'Outorgante: Heliabison Matias Correia, brasileiro, Solteiro(a), Estudante, CPF: 078.428.503-99\n"
                        "         e RG: 2020096219-6, representado (a) por Daiane Cunha Matias, CPF: 021.409.413-81 e RG: 2004003002105'\n"
                        "  EXTRAÇÃO CORRETA:\n"
                        "  - nome: 'Heliabison Matias Correia'\n"
                        "  - cpf: '078.428.503-99'\n"
                        "  - representante_legal_nome: 'Daiane Cunha Matias'\n"
                        "  - representante_legal_cpf: '021.409.413-81'\n"
                        "  - representante_legal_rg: '2004003002105'\n"
                        "\n"
                        "- ATENÇÃO: NÃO confunda o representante legal (familiar/tutor na procuração) com o advogado/procurador (Horlando Braga Filho).\n"
                    )
                else:
                    personal_data_policy += (
                        "- ESTE documento NÃO é o PDF do INSS.\n"
                        "- Portanto, retorne TODOS os campos de 'qualificacao_parte_autora' como null neste documento.\n"
                        "  (ou seja: NÃO extraia nome/CPF/endereço do paciente daqui, mesmo que apareça no texto).\n"
                    )

                laudo_policy = (
                    "POLÍTICA DOS LAUDOS (OBRIGATÓRIA):\n"
                    "- Existem 2 laudos médicos distintos. Não misture médico/especialidade/datas/CIDs entre eles.\n"
                )
                if laudo_role == "principal":
                    laudo_policy += (
                        "- ESTE documento é o PRIMEIRO LAUDO (laudo_principal).\n"
                        "- Preencha COMPLETAMENTE 'dados_medicos.laudo_principal' (incluindo nome_do_medico e especialidade_do_medico) e campos correlatos do laudo.\n"
                        "- O campo 'trecho_clinico_relevante' (descrição do laudo) DEVE começar com 'Recomenda' (ex: 'Recomenda acompanhamento...', 'Recomenda-se que...').\n"
                        "- Retorne 'dados_medicos.laudo_psiquiatrico_segundo_laudo' como null (ou subcampos null).\n"
                    )
                elif laudo_role == "segundo":
                    laudo_policy += (
                        "- ESTE documento é o SEGUNDO LAUDO (laudo_psiquiatrico_segundo_laudo).\n"
                        "- Preencha COMPLETAMENTE 'dados_medicos.laudo_psiquiatrico_segundo_laudo'.\n"
                        "- Retorne 'dados_medicos.laudo_principal' como null (ou subcampos null).\n"
                    )
                else:
                    laudo_policy += (
                        "- ESTE documento não deve preencher campos de laudo, a menos que esteja claramente contido nele.\n"
                        "- Se não for um dos 2 laudos, retorne ambos os blocos de laudo como null.\n"
                    )

                conclusao_policy = (
                    "POLÍTICA DE CONCLUSÃO MÉDICA (OBRIGATÓRIA):\n"
                    "- Extraia 'diagnostico_final_tratamento' dos laudos (deficiência/CID, medicamento, finalidade).\n"
                    "- 'conclusao_medica': síntese textual da conclusão clínica do médico sobre o paciente "
                    "(diagnóstico final, comprometimento, necessidade de acompanhamento). Preencha se houver nos laudos.\n"
                )
                relatorio_escolar_policy = (
                    "POLÍTICA DO RELATÓRIO ESCOLAR (OBRIGATÓRIA):\n"
                    "- Nos campos 'resumo' e 'resumo_continuacao' do relatorio_escolar: extraia SOMENTE o que é importante sobre o aluno "
                    "(dificuldades, necessidades, limitações, recomendações, desempenho).\n"
                    "- NÃO inclua texto introdutório como 'este relatório visa fornecer informações...', 'com foco nas necessidades especiais...' ou similares.\n"
                )

                user_msg = (
                    f"Documento fonte: {source}\n"
                    + "Analise o texto a seguir e preencha os campos do schema. Retorne somente o JSON.\n"
                    + personal_data_policy
                    + personal_data_hint
                    + laudo_policy
                    + conclusao_policy
                    + relatorio_escolar_policy
                    + "Texto:\n"
                    + chunk_text
                )

                messages = [
                    {"role": "system", "content": system_msg},
                    {"role": "user", "content": user_msg},
                ]

                try:
                    resp = call_openai_chat(args.model, messages, [FUNCTION_SCHEMA])
                    chunk_structured = extract_from_response(resp)
                except Exception as e:
                    print(
                        f"Error calling OpenAI (document {ex_idx}/{len(extractions)}, chunk {chunk_idx + 1}/{len(chunks)}): {e}",
                        file=sys.stderr,
                    )
                    return 1

                if not structured_result:
                    structured_result = chunk_structured
                else:
                    merge_structured_field(structured_result, chunk_structured)

                if (chunk_idx < len(chunks) - 1) and args.delay_between_calls > 0:
                    time.sleep(args.delay_between_calls)

            # atraso também entre documentos (útil quando pages-per-call=0)
            if (ex_idx < len(extractions)) and args.delay_between_calls > 0:
                time.sleep(args.delay_between_calls)

    else:
        # Caso "single": mantém compatibilidade, mas ainda aplica a heurística do INSS.
        ocr = ocr_raw
        try:
            ocr = normalize_input_to_ocr(ocr)
        except Exception as e:
            print(f"Failed to normalize input JSON: {e}", file=sys.stderr)
            return 3

        page_numbers = select_page_numbers_for_extraction(
            ocr,
            args.pages,
            args.inss_max_pages,
            args.inss_min_total_pages,
        )
        if not page_numbers:
            print("Nenhuma página foi encontrada nos dados OCR para os filtros fornecidos.", file=sys.stderr)
            return 3

        is_inss_doc = _is_inss_document(ocr, args.inss_min_total_pages)

        chunks = chunk_page_numbers(page_numbers, args.pages_per_call)
        if not chunks:
            print("Não há páginas válidas para processar.", file=sys.stderr)
            return 3

        for chunk_idx, chunk in enumerate(chunks):
            chunk_text = build_text_from_ocr(ocr, pages=chunk)
            if not chunk_text.strip():
                continue

            personal_data_hint = ""  # análise em todas as páginas do INSS, sem restrição a seção específica

            personal_data_policy = (
                "POLÍTICA DE DADOS PESSOAIS (OBRIGATÓRIA):\n"
                "- Os campos de 'qualificacao_parte_autora' (nome, nacionalidade, estado_civil, profissao, cpf, endereco_completo,\n"
                "  representante_legal_nome/cpf/rg) representam dados pessoais do paciente/parte autora.\n"
            )
            if is_inss_doc:
                personal_data_policy += (
                    "- ESTE documento é o PDF do INSS.\n"
                    f"- Analise o conteúdo de todas as {len(page_numbers)} páginas e extraia 'qualificacao_parte_autora' de qualquer parte relevante do documento.\n"
                    "- ATENÇÃO: NUNCA use dados da seção 'Procuradores / Representantes Legais' como dados do paciente.\n"
                    "  - IGNORE 'Horlando Braga Filho' e seu CPF (028.951.113-59) - ele é o advogado/procurador, NÃO o paciente.\n"
                    "\n"
                    "REGRAS PARA REPRESENTANTE LEGAL (CRÍTICO):\n"
                    "- Procure por seções com o título 'PROCURAÇÃO' ou texto contendo 'Outorgante' e 'representado (a) por'.\n"
                    "- FORMATO TÍPICO DA PROCURAÇÃO:\n"
                    "  'PROCURAÇÃO\n"
                    "   Outorgante: [Nome do Paciente], brasileiro, [estado civil], [profissão], CPF: XXX.XXX.XXX-XX e RG: XXXXXXXXX,\n"
                    "   representado (a) por [Nome do Representante Legal], CPF: XXX.XXX.XXX-XX e RG: XXXXXXXXX'\n"
                    "\n"
                    "- REGRA DE EXTRAÇÃO:\n"
                    "  1. OUTORGANTE = PACIENTE (pessoa que dá a procuração) → Preencha 'nome', 'cpf' da qualificacao_parte_autora\n"
                    "  2. REPRESENTADO POR = REPRESENTANTE LEGAL (quem representa o paciente) → Preencha:\n"
                    "     - representante_legal_nome: nome completo que vem APÓS 'representado (a) por' ou 'representado(a) por'\n"
                    "     - representante_legal_cpf: CPF que vem logo após o nome do representante\n"
                    "     - representante_legal_rg: RG que vem logo após o CPF do representante\n"
                    "\n"
                    "- EXEMPLO REAL:\n"
                    "  Texto: 'Outorgante: Heliabison Matias Correia, brasileiro, Solteiro(a), Estudante, CPF: 078.428.503-99\n"
                    "         e RG: 2020096219-6, representado (a) por Daiane Cunha Matias, CPF: 021.409.413-81 e RG: 2004003002105'\n"
                    "  EXTRAÇÃO CORRETA:\n"
                    "  - nome: 'Heliabison Matias Correia'\n"
                    "  - cpf: '078.428.503-99'\n"
                    "  - representante_legal_nome: 'Daiane Cunha Matias'\n"
                    "  - representante_legal_cpf: '021.409.413-81'\n"
                    "  - representante_legal_rg: '2004003002105'\n"
                    "\n"
                    "- ATENÇÃO: NÃO confunda o representante legal (familiar/tutor na procuração) com o advogado/procurador (Horlando Braga Filho).\n"
                )
            else:
                personal_data_policy += (
                    "- ESTE documento NÃO é o PDF do INSS.\n"
                    "- Portanto, retorne TODOS os campos de 'qualificacao_parte_autora' como null neste documento.\n"
                    "  (ou seja: NÃO extraia nome/CPF/endereço do paciente daqui, mesmo que apareça no texto).\n"
                )

            conclusao_policy = (
                "POLÍTICA DE CONCLUSÃO MÉDICA (OBRIGATÓRIA):\n"
                "- Extraia 'diagnostico_final_tratamento' dos laudos (deficiência/CID, medicamento, finalidade).\n"
                "- 'conclusao_medica': síntese textual da conclusão clínica do médico sobre o paciente "
                "(diagnóstico final, comprometimento, necessidade de acompanhamento). Preencha se houver nos laudos.\n"
            )
            relatorio_escolar_policy = (
                "POLÍTICA DO RELATÓRIO ESCOLAR (OBRIGATÓRIA):\n"
                "- Nos campos 'resumo' e 'resumo_continuacao' do relatorio_escolar: extraia SOMENTE o que é importante sobre o aluno "
                "(dificuldades, necessidades, limitações, recomendações, desempenho).\n"
                "- NÃO inclua texto introdutório como 'este relatório visa fornecer informações...', 'com foco nas necessidades especiais...' ou similares.\n"
            )

            user_msg = (
                "Analise o texto a seguir e preencha os campos do schema. Retorne somente o JSON.\n"
                + personal_data_policy
                + personal_data_hint
                + conclusao_policy
                + relatorio_escolar_policy
                + "Texto:\n"
                + chunk_text
            )

            messages = [
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_msg},
            ]

            try:
                resp = call_openai_chat(args.model, messages, [FUNCTION_SCHEMA])
                chunk_structured = extract_from_response(resp)
            except Exception as e:
                print(f"Error calling OpenAI (chunk {chunk_idx + 1}/{len(chunks)}): {e}", file=sys.stderr)
                return 1

            if not structured_result:
                structured_result = chunk_structured
            else:
                merge_structured_field(structured_result, chunk_structured)

            if (chunk_idx < len(chunks) - 1) and args.delay_between_calls > 0:
                time.sleep(args.delay_between_calls)

    if not structured_result:
        print("A API não retornou nenhum conteúdo estruturado.", file=sys.stderr)
        return 4

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(structured_result, f, ensure_ascii=False, indent=2)

    print(f"Saved structured extraction to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
