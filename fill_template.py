#!/usr/bin/env python3


# python fill_template.py extraction_structured.json --template template.docx -o template_gerado.docx

"""Fill a DOCX template using values from extraction_structured.json.

Usage:
  python fill_template.py extraction_structured.json --template template.docx -o template_gerado.docx

Behavior:
- Reads the structured JSON produced by `analyze_with_openai.py`.
- Replaces placeholders in the DOCX template of the form [Campo] with values found in JSON.
- If `--template` does not exist, a new blank `template_gerado.docx` will be created with placeholders replaced.

Note: this replacement strategy merges runs and may lose complex character-level formatting. It's suitable for templates with plain text placeholders.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from typing import Any, Dict, List, Optional

try:
    from docx import Document
except Exception:
    Document = None


PLACEHOLDER_PATTERN = re.compile(r"\[([^\]]+)\]")


def load_json(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_nested(data: Dict[str, Any], path: List[str]) -> Optional[Any]:
    cur = data
    for p in path:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(p)
        if cur is None:
            return None
    return cur


def first_non_null(data: Dict[str, Any], paths: List[List[str]]) -> Optional[Any]:
    for p in paths:
        val = get_nested(data, p)
        if val is not None and val != "":
            return val
    return None


def prepare_replacements(structured: Dict[str, Any]) -> Dict[str, str]:
    """Map placeholders to values extracted from structured JSON."""
    def s(v: Any) -> str:
        if v is None:
            return ""
        if isinstance(v, (list, dict)):
            return json.dumps(v, ensure_ascii=False)
        return str(v)

    replacements: Dict[str, str] = {}

    # qualification
    replacements["Nome"] = s(first_non_null(structured, [["qualificacao_parte_autora", "nome"]]))
    replacements["nacionalidade"] = s(first_non_null(structured, [["qualificacao_parte_autora", "nacionalidade"]]))
    replacements["estado civil"] = s(first_non_null(structured, [["qualificacao_parte_autora", "estado_civil"]]))
    replacements["profissão"] = s(first_non_null(structured, [["qualificacao_parte_autora", "profissao"]]))
    replacements["CPF"] = s(first_non_null(structured, [["qualificacao_parte_autora", "cpf"]]))
    replacements["Representante legal"] = s(first_non_null(structured, [["qualificacao_parte_autora", "representante_legal_nome"]]))
    replacements["CPF representante"] = s(first_non_null(structured, [["qualificacao_parte_autora", "representante_legal_cpf"]]))
    replacements["RG representante"] = s(first_non_null(structured, [["qualificacao_parte_autora", "representante_legal_rg"]]))
    replacements["endereço completo"] = s(first_non_null(structured, [["qualificacao_parte_autora", "endereco_completo"]]))

    # requerimento INSS
    replacements["Número do benefício"] = s(first_non_null(structured, [["dados_requerimento_inss", "numero_beneficio_NB"]]))
    replacements["data de entrada do requerimento"] = s(first_non_null(structured, [["dados_requerimento_inss", "DER_data_entrada_requerimento"]]))

    # dados medicos
    lp = structured.get("dados_medicos", {})
    replacements["deficiência constatada em laudo médico"] = s(first_non_null(structured, [["dados_medicos", "laudo_principal", "deficiencia_constatada"]]))
    replacements["CID da doença"] = s(first_non_null(structured, [["dados_medicos", "laudo_principal", "CID_da_doenca"]]))
    replacements["data do laudo médico"] = s(first_non_null(structured, [["dados_medicos", "laudo_principal", "data_do_laudo"]]))
    replacements["especialidade do médico"] = s(first_non_null(structured, [["dados_medicos", "laudo_principal", "especialidade_do_medico"]]))
    replacements["nome do médico"] = s(first_non_null(structured, [["dados_medicos", "laudo_principal", "nome_do_medico"]]))
    replacements["descrição do laudo"] = s(first_non_null(structured, [["dados_medicos", "laudo_principal", "trecho_clinico_relevante"]]))

    # relatorio escolar
    replacements["data de emissão do relatório escolar"] = s(first_non_null(structured, [["dados_medicos", "relatorio_escolar", "data_emissao"]]))
    replacements["primeiro nome do autor"] = s(first_non_null(structured, [["dados_medicos", "relatorio_escolar", "primeiro_nome_do_autor"]]))
    replacements["resumo do relatório escolar"] = s(first_non_null(structured, [["dados_medicos", "relatorio_escolar", "resumo"]]))
    replacements["continuação do resumo do relatório escolar"] = s(first_non_null(structured, [["dados_medicos", "relatorio_escolar", "resumo_continuacao"]]))

    # segundo laudo
    replacements["data do “segundo laudo”"] = s(first_non_null(structured, [["dados_medicos", "laudo_psiquiatrico_segundo_laudo", "data_segundo_laudo"]]))
    replacements["Nome do médico segundo"] = s(first_non_null(structured, [["dados_medicos", "laudo_psiquiatrico_segundo_laudo", "nome_medico"]]))
    replacements["resumo do laudo médico"] = s(first_non_null(structured, [["dados_medicos", "laudo_psiquiatrico_segundo_laudo", "resumo"]]))

    # diagnostico e tratamento
    replacements["deficiência e a CID correspondente"] = s(first_non_null(structured, [["dados_medicos", "diagnostico_final_tratamento", "deficiencia_e_CID"]]))
    replacements["deficiência associada e CID correspondente"] = s(first_non_null(structured, [["dados_medicos", "diagnostico_final_tratamento", "deficiencia_associada_e_CID"]]))
    replacements["medicamento prescrito"] = s(first_non_null(structured, [["dados_medicos", "diagnostico_final_tratamento", "medicamento_prescrito"]]))
    replacements["descrição da finalidade do medicamento"] = s(first_non_null(structured, [["dados_medicos", "diagnostico_final_tratamento", "finalidade_medicamento"]]))

    # dados socioeconomicos
    replacements["detalhar o grau de parentesco das pessoas listadas no cadastro único"] = s(first_non_null(structured, [["dados_socioeconomicos", "grau_parentesco_CadUnico"]]))
    replacements["nome da avó"] = s(first_non_null(structured, [["dados_socioeconomicos", "nome_avo"]]))
    replacements["valor exato da aposentadoria – R$ ___ "] = s(first_non_null(structured, [["dados_socioeconomicos", "valor_exato_aposentadoria"]]))
    replacements["páginas do laudo social – “anexo 05, pgs. XX”"] = s(first_non_null(structured, [["dados_socioeconomicos", "paginas_laudo_social"]]))

    # dados processuais
    replacements["Número do benefício / NB"] = replacements.get("Número do benefício", "")

    return replacements


def replace_in_paragraph(paragraph, replacements: Dict[str, str]) -> None:
    text = "".join(run.text for run in paragraph.runs)
    if not text:
        return
    new_text = text
    for ph, val in replacements.items():
        # replace exact placeholder with brackets in the document
        new_text = new_text.replace(f"[{ph}]", val)
    if new_text != text:
        # remove all existing runs
        for i in range(len(paragraph.runs) - 1, -1, -1):
            r = paragraph.runs[i]
            r.clear()
            # remove run by setting text to empty; docx doesn't provide direct removal
            r.text = ""
        # add a single run with new_text
        paragraph.add_run(new_text)


def replace_in_table(table: Any, replacements: Dict[str, str]) -> None:
    for row in table.rows:
        for cell in row.cells:
            for p in cell.paragraphs:
                replace_in_paragraph(p, replacements)


def process_document(doc: Any, replacements: Dict[str, str]) -> None:
    for p in doc.paragraphs:
        replace_in_paragraph(p, replacements)
    for tbl in doc.tables:
        replace_in_table(tbl, replacements)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Fill DOCX template with fields from structured JSON")
    parser.add_argument("input_json", help="Structured JSON file (from analyze_with_openai.py)")
    parser.add_argument("--template", default="template.docx", help="Path to DOCX template")
    parser.add_argument("-o", "--output", default="template_gerado.docx", help="Output filled DOCX")
    args = parser.parse_args(argv)

    if Document is None:
        print("Missing dependency 'python-docx'. Install with: pip install python-docx", file=sys.stderr)
        return 2

    if not os.path.exists(args.input_json):
        print(f"Input JSON not found: {args.input_json}", file=sys.stderr)
        return 2

    structured = load_json(args.input_json)
    replacements = prepare_replacements(structured)

    # If template not exists, create a blank doc with placeholders inserted
    if not os.path.exists(args.template):
        doc = Document()
        # create a minimal template based on the user's sample header
        doc.add_paragraph("Ao Juízo da 27° Vara do Juizado Especial Federal da Comarca de Itapipoca/CE.")
        doc.add_paragraph("[Nome], [nacionalidade], [estado civil], [profissão], [CPF:], representado (a) por [Representante legal], [CPF representante] e [RG representante], residentes e domiciliados (as) na [endereço completo] (anexo 01), ...")
        doc.save(args.output)
        print(f"Template not found. Created minimal template and saved to {args.output}")
        return 0

    doc = Document(args.template)
    process_document(doc, replacements)
    doc.save(args.output)
    print(f"Generated filled document: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
