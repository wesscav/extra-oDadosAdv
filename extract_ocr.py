#!/usr/bin/env python3


## executar o script e salvar em extraction_output.json (padrão)
# venv/bin/python3 extract_ocr.py "XMALC-LAUDO MÉDICO 16.12.25.pdf" -o extraction_output.json

# venv/bin/python3 extract_ocr.py "08.XEMRD-LAUDO MEDICO 05.04.25.pdf" -o extraction_output.json


# python3 extract_ocr.py "XMALC-LAUDO MÉDICO 16.12.25.pdf" -o extraction_output.json

"""OCR extraction for PDF files.

Converts each PDF page to an image and runs Tesseract OCR to extract text
and word-level data (bounding boxes and confidences). Outputs a JSON file.

Usage:
    python extract_ocr.py input.pdf -o output.json

Notes:
 - Requires Tesseract OCR installed and on PATH.
 - Requires poppler (for pdf2image). You can set POPPLER_PATH env var if needed.
"""
import argparse
import json
import os
import platform
import sys
from typing import List, Dict, Any
import re

try:
    from pdf2image import convert_from_path
except Exception as e:
    convert_from_path = None

try:
    import pytesseract
    from pytesseract import Output

    # 1. Verifica se existe uma variável de ambiente (prioridade máxima)
    env_path = os.getenv('TESSERACT_CMD')
    if env_path:
        pytesseract.pytesseract.tesseract_cmd = env_path
    # 2. Se não tem variável e estamos no Windows, usa o caminho padrão local
    elif platform.system() == 'Windows':
        default_paths = [
            r'C:\Program Files\Tesseract-OCR\tesseract.exe',
            r'C:\Program Files (x86)\Tesseract-OCR\tesseract.exe',
            os.path.join(os.getenv('LOCALAPPDATA', ''), r'Tesseract-OCR\tesseract.exe')
        ]
        for path in default_paths:
            if os.path.exists(path):
                pytesseract.pytesseract.tesseract_cmd = path
                break

except Exception:
    pytesseract = None
    Output = None

try:
    from PIL import Image
except Exception:
    print("Missing Python dependency 'Pillow'.\nPlease activate your virtualenv and install dependencies:\n  source .venv/bin/activate\n  pip install -r requirements.txt\nOr run the script with the venv python directly:\n  .venv/bin/python3 extract_ocr.py <input.pdf> -o <output.json>", file=sys.stderr)
    sys.exit(1)


def check_dependencies() -> List[str]:
    missing = []
    if pytesseract is None:
        missing.append('pytesseract')
    if convert_from_path is None:
        missing.append('pdf2image')
    # tesseract binary
    if pytesseract is not None:
        try:
            _ = pytesseract.get_tesseract_version()
        except Exception:
            missing.append('tesseract (binary)')
    return missing


def ocr_page(image: Image.Image, lang: str = 'por') -> Dict[str, Any]:
    """Run OCR on a PIL Image and return structured data."""
    # full text
    text = pytesseract.image_to_string(image, lang=lang)

    data = pytesseract.image_to_data(image, output_type=Output.DICT, lang=lang)

    words = []
    n_boxes = len(data.get('text', []))
    for i in range(n_boxes):
        w = data['text'][i]
        if not w or w.strip() == '':
            continue
        # normalize confidence which may be string or numeric depending on pytesseract version
        conf_val = data['conf'][i]
        conf = None
        try:
            if isinstance(conf_val, (int, float)):
                conf = int(conf_val)
            else:
                s = str(conf_val).strip()
                if s.lstrip('-').isdigit():
                    conf = int(s)
        except Exception:
            conf = None

        words.append({
            'text': w,
            'left': int(data['left'][i]),
            'top': int(data['top'][i]),
            'width': int(data['width'][i]),
            'height': int(data['height'][i]),
            'conf': conf,
        })

    return {'text': text, 'words': words}


def extract_pdf(pdf_path: str, dpi: int = 300, poppler_path: str = None, lang: str = 'por', 
                first_page: int = None, last_page: int = None) -> Dict[str, Any]:
    """Extract OCR data for each page in the PDF.
    
    Args:
        pdf_path: Path to the PDF file
        dpi: DPI for image conversion
        poppler_path: Path to poppler binaries
        lang: Tesseract language(s)
        first_page: First page to process (1-indexed, inclusive)
        last_page: Last page to process (1-indexed, inclusive)
    """
    if convert_from_path is None:
        raise RuntimeError('pdf2image is not available')

    convert_kwargs = {'dpi': dpi}
    if poppler_path:
        convert_kwargs['poppler_path'] = poppler_path
    if first_page:
        convert_kwargs['first_page'] = first_page
    if last_page:
        convert_kwargs['last_page'] = last_page

    images = convert_from_path(pdf_path, **convert_kwargs)

    pages = []
    page_offset = (first_page - 1) if first_page else 0
    for i, img in enumerate(images, start=1):
        actual_page_num = page_offset + i
        print(f'OCR page {actual_page_num}/{last_page if last_page else "?"}...')
        page_data = ocr_page(img, lang=lang)
        pages.append({'page_number': actual_page_num, **page_data})

    return {'source': os.path.abspath(pdf_path), 'page_count': len(pages), 'pages': pages}


def main(argv: List[str]):
    parser = argparse.ArgumentParser(description='Extract text and word data from a PDF using OCR')
    parser.add_argument('pdfs', nargs='+', help='One or more input PDF files (supports multiple paths)')
    parser.add_argument('-o', '--output', help='Output JSON file (used when not using --split)', default='extraction_output.json')
    parser.add_argument('--split', action='store_true', help='Write one JSON file per input PDF instead of a combined output')
    parser.add_argument('--dpi', type=int, default=300, help='DPI for PDF to image conversion')
    parser.add_argument('--poppler-path', default=os.environ.get('POPPLER_PATH'), help='Path to poppler utilities (optional)')
    parser.add_argument('--lang', default='por', help='Tesseract language(s), e.g. "por" or "eng+por"')
    parser.add_argument('--first-page', type=int, help='First page to process (1-indexed)')
    parser.add_argument('--last-page', type=int, help='Last page to process (1-indexed)')
    parser.add_argument('--auto-detect-inss', action='store_true', help='Automatically detect INSS documents and process only first 6 pages')

    args = parser.parse_args(argv)

    missing = check_dependencies()
    if missing:
        print('Missing dependencies:', ', '.join(missing))
        print('\nOn macOS you can install them with:')
        print('  brew install tesseract poppler')
        print('And in the venv:')
        print('  pip install -r requirements.txt')
        sys.exit(2)

    results = []
    for pdf_path in args.pdfs:
        if not os.path.isfile(pdf_path):
            print('PDF file not found:', pdf_path, file=sys.stderr)
            continue

        first_page = args.first_page
        last_page = args.last_page

        # Auto-detect INSS documents
        if args.auto_detect_inss and not last_page:
            try:
                print(f'Detectando tipo de documento em {pdf_path}...')
                first_page_result = extract_pdf(
                    pdf_path, 
                    dpi=args.dpi, 
                    poppler_path=args.poppler_path, 
                    lang=args.lang,
                    first_page=1,
                    last_page=1
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
                        print('Documento INSS detectado - processando apenas primeiras 6 paginas')
                        first_page = 1
                        last_page = 6
                    else:
                        print('Documento padrao - processando todas as paginas')
            except Exception as e:
                print(f'Aviso: Falha na deteccao automatica: {e}. Processando documento completo.', file=sys.stderr)

        try:
            result = extract_pdf(
                pdf_path, 
                dpi=args.dpi, 
                poppler_path=args.poppler_path, 
                lang=args.lang,
                first_page=first_page,
                last_page=last_page
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
