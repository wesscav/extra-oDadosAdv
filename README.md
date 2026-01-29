# Extração OCR de PDF

Este repositório contém um script simples para extrair texto de um PDF usando OCR (Tesseract).

Requisitos do sistema (macOS):

- tesseract: brew install tesseract
- poppler (para converter PDF->imagem): brew install poppler

Instalação do ambiente Python (assumindo virtualenv/venv):

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Como usar:

```bash
python extract_ocr.py "XMALC-LAUDO MÉDICO 16.12.25.pdf" -o saida.json
```

Saída:

- Um arquivo JSON com a estrutura: { source, page_count, pages: [{page_number, text, words:[{text,left,top,width,height,conf}]}] }

Notas:

- Se o Tesseract ou o Poppler não estiverem instalados, o script exibirá instruções rápidas.
- Ajuste a linguagem do Tesseract com a opção --lang (por padrão 'por').

Análise automática com a API da OpenAI
-----------------------------------

Há um script adicional `analyze_with_openai.py` para enviar o campo `text` do JSON OCR
para a API da OpenAI usando function-calling e retornar um JSON estruturado com os
campos desejados (qualificação, dados do INSS, dados médicos, etc.).

Instalação das dependências adicionais:

```bash
pip install -r requirements.txt
```

Exemplo de uso (carrega chave de OPENAI_API_KEY do ambiente ou de `.env`/`.ENV`):

```bash
# export OPENAI_API_KEY="sk-..."
python analyze_with_openai.py extraction_output.json -o extraction_structured.json
```

Observações:
- Não comite a chave da API. Use variáveis de ambiente ou um arquivo `.env` que esteja no `.gitignore`.
- Se o texto for muito grande, passe `--pages` para enviar apenas páginas específicas.

