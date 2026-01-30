#!/usr/bin/env python3

# source .venv/bin/activate
## executar o script e salvar em extraction_output.json (padrão)
# venv/bin/python3 extract_ocr.py "XMALC-LAUDO MÉDICO 16.12.25.pdf" -o extraction_output.json

# venv/bin/python3 extract_ocr.py "07.XEMRD-RELATORIO ESCOLAR 05.12.24.pdf" -o extraction_output.json


# python3 extract_ocr.py "laudo_digital.pdf" -o extraction_output.json

"""OCR extraction for PDF files.

Converts each PDF page to an image and runs Tesseract OCR to extract text
and word-level data (bounding boxes and confidences). Outputs a JSON file.

Usage:
    python extract_ocr.py input.pdf -o output.json
"""
import argparse
import json
import os
import sys
from typing import List, Dict, Any
import re

try:
    import pdfplumber
except Exception:
    pdfplumber = None

try:
    from PIL import Image
except Exception:
    Image = None

try:
    import pytesseract
except Exception:
    pytesseract = None

try:
    from pdf2image import convert_from_path
except Exception:
    convert_from_path = None


def check_dependencies() -> List[str]:
    missing = []
    if pdfplumber is None:
        missing.append('pdfplumber')
    if pytesseract is None:
        missing.append('pytesseract')
    if convert_from_path is None:
        missing.append('pdf2image')
    return missing


def _configure_ocr() -> Dict[str, Any]:
    """Configura Tesseract/Poppler via variáveis de ambiente (Windows-friendly).

    - TESSERACT_CMD: caminho do tesseract.exe
    - POPPLER_PATH: pasta do poppler/bin (para pdf2image)
    """
    tesseract_cmd = os.environ.get("TESSERACT_CMD")
    if tesseract_cmd and pytesseract is not None:
        pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
    return {"tesseract_cmd": tesseract_cmd, "poppler_path": os.environ.get("POPPLER_PATH")}


def _should_fallback_to_ocr(text: str, min_chars: int) -> bool:
    return len((text or "").strip()) < min_chars


def _ocr_page_from_pdf_path(
    pdf_path: str,
    page_number_1based: int,
    *,
    lang: str,
    dpi: int,
    poppler_path: str | None,
) -> str:
    if convert_from_path is None or pytesseract is None:
        return ""
    images = convert_from_path(
        pdf_path,
        dpi=dpi,
        first_page=page_number_1based,
        last_page=page_number_1based,
        poppler_path=poppler_path,
    )
    if not images:
        return ""
    return pytesseract.image_to_string(images[0], lang=lang, config="--psm 6")


def extract_pdf_text_hybrid(
    pdf_path: str,
    *,
    ocr_lang: str = "por",
    ocr_min_chars: int = 30,
    ocr_dpi: int = 300,
) -> Dict[str, Any]:
    """Extrai texto do PDF com fallback para OCR por página.

    Returns same structure as the previous extract_pdf: {'source', 'page_count', 'pages'}
    Each page has 'page_number', 'text', and 'words' where each word has
    text,left,top,width,height,conf (conf will be None since pdfplumber doesn't provide it).
    """
    if pdfplumber is None:
        raise RuntimeError('pdfplumber is not available')

    cfg = _configure_ocr()
    pages = []
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            words = []
            # page.extract_words() returns dicts with x0,x1,top,bottom and text
            try:
                raw_words = page.extract_words()
            except Exception:
                raw_words = []

            for w in raw_words:
                x0 = float(w.get('x0', 0))
                x1 = float(w.get('x1', x0))
                top = float(w.get('top', 0))
                bottom = float(w.get('bottom', top))
                left = int(x0)
                top_i = int(top)
                width = int(x1 - x0)
                height = int(bottom - top)
                words.append({
                    'text': w.get('text', ''),
                    'left': left,
                    'top': top_i,
                    'width': width,
                    'height': height,
                    'conf': None,
                })

            method = "pdfplumber"
            if _should_fallback_to_ocr(text, ocr_min_chars):
                try:
                    ocr_text = _ocr_page_from_pdf_path(
                        pdf_path,
                        i,
                        lang=ocr_lang,
                        dpi=ocr_dpi,
                        poppler_path=cfg.get("poppler_path"),
                    )
                    if ocr_text and len(ocr_text.strip()) >= len(text.strip()):
                        text = ocr_text
                        method = "ocr"
                except Exception:
                    pass

            pages.append({'page_number': i, 'text': text, 'words': words, 'method': method})

    return {'source': os.path.abspath(pdf_path), 'page_count': len(pages), 'pages': pages}





def main(argv: List[str]):
    parser = argparse.ArgumentParser(description='Extract text and word data from a PDF (no OCR)')
    parser.add_argument('pdfs', nargs='+', help='One or more input PDF files (supports multiple paths)')
    parser.add_argument('-o', '--output', help='Output JSON file (used when not using --split)', default='extraction_output.json')
    parser.add_argument('--split', action='store_true', help='Write one JSON file per input PDF instead of a combined output')
    parser.add_argument('--lang', default='por', help='OCR language (Tesseract), default: por')
    parser.add_argument('--ocr-min-chars', type=int, default=30, help='Se o texto extraído tiver menos que N caracteres, usa OCR (default: 30).')
    parser.add_argument('--ocr-dpi', type=int, default=300, help='DPI para renderizar página antes do OCR (default: 300).')

    args = parser.parse_args(argv)

    missing = check_dependencies()
    if missing:
        print('Missing dependencies:', ', '.join(missing))
        print('\nOn macOS you can install pdfplumber with:')
        print('  pip install pdfplumber')
        sys.exit(2)

    results = []
    for pdf_path in args.pdfs:
        if not os.path.isfile(pdf_path):
            print('PDF file not found:', pdf_path, file=sys.stderr)
            continue

        try:
            result = extract_pdf_text_hybrid(
                pdf_path,
                ocr_lang=args.lang,
                ocr_min_chars=args.ocr_min_chars,
                ocr_dpi=args.ocr_dpi,
            )
        except Exception as e:
            print('Error during extraction for', pdf_path, ':', e, file=sys.stderr)
            continue

        # either write per-file or collect for combined
        if args.split:
            base = os.path.splitext(os.path.basename(pdf_path))[0]
            safe_base = re.sub(r"[^0-9A-Za-z-_]+", "_", base)
            out_path = args.output if args.output and len(args.pdfs) == 1 else f"{safe_base}.json"
            with open(out_path, 'w', encoding='utf-8') as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            print(f'Extraction finished for {pdf_path}: {out_path} (pages: {result["page_count"]})')
        else:
            results.append(result)

    if not args.split:
        # write combined output
        combined = { 'extractions': results }
        try:
            with open(args.output, 'w', encoding='utf-8') as f:
                json.dump(combined, f, ensure_ascii=False, indent=2)
            print(f'Combined extraction finished: {args.output} (files: {len(results)})')
        except Exception as e:
            print('Failed to write combined output:', e, file=sys.stderr)
            sys.exit(1)


if __name__ == '__main__':
    main(sys.argv[1:])
