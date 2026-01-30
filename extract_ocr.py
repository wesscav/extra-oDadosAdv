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


def check_dependencies() -> List[str]:
    missing = []
    if pdfplumber is None:
        missing.append('pdfplumber')
    return missing


def extract_pdf_text_pdfplumber(pdf_path: str) -> Dict[str, Any]:
    """Extract text and word bboxes from a PDF using pdfplumber (no OCR).

    Returns same structure as the previous extract_pdf: {'source', 'page_count', 'pages'}
    Each page has 'page_number', 'text', and 'words' where each word has
    text,left,top,width,height,conf (conf will be None since pdfplumber doesn't provide it).
    """
    if pdfplumber is None:
        raise RuntimeError('pdfplumber is not available')

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

            pages.append({'page_number': i, 'text': text, 'words': words})

    return {'source': os.path.abspath(pdf_path), 'page_count': len(pages), 'pages': pages}





def main(argv: List[str]):
    parser = argparse.ArgumentParser(description='Extract text and word data from a PDF (no OCR)')
    parser.add_argument('pdfs', nargs='+', help='One or more input PDF files (supports multiple paths)')
    parser.add_argument('-o', '--output', help='Output JSON file (used when not using --split)', default='extraction_output.json')
    parser.add_argument('--split', action='store_true', help='Write one JSON file per input PDF instead of a combined output')
    parser.add_argument('--lang', default='por', help='Language hint (not used for text-extraction without OCR)')

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
            result = extract_pdf_text_pdfplumber(pdf_path)
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
