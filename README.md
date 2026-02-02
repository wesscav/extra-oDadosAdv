# Extração OCR de PDF

Este repositório contém um script simples para extrair texto de um PDF usando OCR (Tesseract).

Requisitos do sistema (OCR - Tesseract):

macOS:
- tesseract: `brew install tesseract`

Windows:
- Instale o **Tesseract OCR** e garanta que o `tesseract.exe` esteja no PATH, ou defina:
  - `TESSERACT_CMD="C:\caminho\para\tesseract.exe"`
- Para OCR em PDFs (converter página → imagem), instale o **Poppler** e defina:
  - `POPPLER_PATH="C:\caminho\para\poppler\bin"`

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

Interface web (upload de 1–10 PDFs + confirmação + geração de DOCX)
---------------------------------------------------------------

Foi adicionado um servidor web simples que:
- recebe **de 1 a 10 PDFs** por upload
- faz a extração (pdfplumber com fallback OCR) + análise (OpenAI)
- mostra um **modal de confirmação** com o resumo e o JSON estruturado
- após confirmar, gera e baixa o **`.docx`** preenchido com o `template.docx`

Requisitos:
- Python 3
- `OPENAI_API_KEY` no ambiente ou em `.env`
- Autenticação via Firebase (Frontend) e validação de `idToken` no backend via `firebase-admin`

Configuração do Firebase no backend (segurança):
- O backend espera `Authorization: Bearer <idToken>` em `/api/extract` e `/api/generate-docx`
- Configure UMA das opções abaixo para o `firebase-admin` conseguir validar tokens:
  - `FIREBASE_SERVICE_ACCOUNT_JSON="C:\caminho\para\serviceAccountKey.json"`
  - ou `FIREBASE_SERVICE_ACCOUNT='{"type":"service_account",...}'` (JSON string)
  - ou `GOOGLE_APPLICATION_CREDENTIALS="C:\caminho\para\serviceAccountKey.json"`
- Opcional:
  - `FIREBASE_PROJECT_ID="horlandobraga-168fc"`
  - `FIREBASE_CHECK_REVOKED=1` (se quiser checar revogação — pode adicionar custo/latência)

Instalar dependências:

```bash
pip install -r requirements.txt
```

Rodar o servidor:

```bash
uvicorn server:app --reload
```

Abrir no navegador:
- `http://127.0.0.1:8000/`
