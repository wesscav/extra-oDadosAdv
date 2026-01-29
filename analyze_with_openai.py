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
import textwrap
from typing import Any, Dict, List, Optional

try:
    import openai
except Exception:
    openai = None

try:
    from dotenv import load_dotenv
except Exception:
    load_dotenv = None

from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type


DEFAULT_MODEL = "gpt-4-0613"


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

    openai.api_key = api_key

    # Use ChatCompletion API with function calling
    def _normalize_resp(obj: Any) -> Dict[str, Any]:
        """Normalize OpenAI SDK response object to a plain dict."""
        if isinstance(obj, dict):
            return obj
        # OpenAI OpenAIObject usually has to_dict()
        try:
            if hasattr(obj, "to_dict"):
                return obj.to_dict()
        except Exception:
            pass
        # Try to convert via JSON string
        try:
            return json.loads(str(obj))
        except Exception:
            # Fallback: expose minimal representation
            return {"raw": str(obj)}

    try:
        # Old-style call (may raise APIRemovedInV1 on newer openai versions)
        resp = openai.ChatCompletion.create(
            model=model,
            messages=messages,
            functions=functions,
            function_call="auto",
            temperature=0,
            max_tokens=2000,
        )
        return _normalize_resp(resp)
    except Exception as e:
        # Detect removed API (new openai package uses nested namespaces)
        msg = str(e)
        # Handle API removal or rate limit specifically to give clearer guidance
        if "RateLimitError" in msg or (hasattr(e, "__class__") and e.__class__.__name__ == "RateLimitError"):
            raise RuntimeError("Rate limit reached. Try again after a short wait, reduce request rate or check your account usage/quotas on platform.openai.com.")
        if "APIRemovedInV1" in msg or (hasattr(e, "__class__") and e.__class__.__name__ == "APIRemovedInV1"):
            # Try the new SDK call: openai.chat.completions.create
            if hasattr(openai, "chat") and hasattr(openai.chat, "completions"):
                resp = openai.chat.completions.create(
                    model=model,
                    messages=messages,
                    functions=functions,
                    function_call="auto",
                    temperature=0,
                    max_tokens=2000,
                )
                return _normalize_resp(resp)
        # re-raise if we can't handle it
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

    ocr = read_ocr_json(args.input)
    # normalize combined extraction files (those with key 'extractions') into a single OCR-like object
    try:
        ocr = normalize_input_to_ocr(ocr)
    except Exception as e:
        print(f"Failed to normalize input JSON: {e}", file=sys.stderr)
        return 3
    page_numbers = extract_page_numbers(ocr, args.pages)
    if not page_numbers:
        print("Nenhuma página foi encontrada nos dados OCR para os filtros fornecidos.", file=sys.stderr)
        return 3

    chunks = chunk_page_numbers(page_numbers, args.pages_per_call)
    if not chunks:
        print("Não há páginas válidas para processar.", file=sys.stderr)
        return 3

    system_msg = (
        "Você é um assistente que analisa laudos e extrai campos jurídicos e médicos. "
        "Retorne apenas JSON seguindo o schema de função. Se o dado não existir, retorne null. "
        "Se houver baixa confiança, inclua o valor e marque '[confiança baixa]'."
    )

    structured_result: Dict[str, Any] = {}
    for idx, chunk in enumerate(chunks):
        chunk_text = build_text_from_ocr(ocr, pages=chunk)
        if not chunk_text.strip():
            continue

        user_msg = (
            "Analise o texto a seguir e preencha os campos do schema. Retorne somente o JSON. "
            "Texto:\n" + chunk_text
        )

        messages = [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg},
        ]

        try:
            resp = call_openai_chat(args.model, messages, [FUNCTION_SCHEMA])
            chunk_structured = extract_from_response(resp)
        except Exception as e:
            print(f"Error calling OpenAI (chunk {idx + 1}/{len(chunks)}): {e}", file=sys.stderr)
            return 1

        if not structured_result:
            structured_result = chunk_structured
        else:
            merge_structured_field(structured_result, chunk_structured)

        if idx < len(chunks) - 1 and args.delay_between_calls > 0:
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
