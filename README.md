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

Interface web (upload de 4 PDFs + confirmação + geração de DOCX)
---------------------------------------------------------------

Foi adicionado um servidor web simples que:
- recebe **exatamente 4 PDFs** por upload
- faz a extração (pdfplumber com fallback OCR) + análise (OpenAI)
- mostra um **modal de confirmação** com o resumo e o JSON estruturado
- após confirmar, gera e baixa o **`.docx`** preenchido com o `template.docx`

Requisitos:
- Python 3
- `OPENAI_API_KEY` no ambiente ou em `.env`
- **Autenticação via Firebase** (Frontend) e validação de `idToken` no backend via `firebase-admin`

### Configuração do Firebase no backend (OBRIGATÓRIO)

As rotas `/api/extract` e `/api/generate-docx` **estão protegidas** e exigem autenticação.

O backend espera `Authorization: Bearer <idToken>` e valida com `firebase-admin`.

**Opção 1: Service Account Key (recomendado para produção)**

1. Baixe o arquivo `serviceAccountKey.json` do Firebase Console:
   - Acesse: https://console.firebase.google.com/
   - Project Settings > Service Accounts > Generate New Private Key
   
2. Configure a variável de ambiente:
   ```bash
   # Windows (PowerShell)
   $env:FIREBASE_SERVICE_ACCOUNT_JSON="C:\caminho\para\serviceAccountKey.json"
   
   # Linux/Mac
   export FIREBASE_SERVICE_ACCOUNT_JSON="/caminho/para/serviceAccountKey.json"
   ```

**Opção 2: JSON inline (para testes/desenvolvimento)**

```bash
# Windows (PowerShell) - escape as aspas duplas
$env:FIREBASE_SERVICE_ACCOUNT='{"type":"service_account","project_id":"horlandobraga-168fc",...}'

# Linux/Mac
export FIREBASE_SERVICE_ACCOUNT='{"type":"service_account","project_id":"horlandobraga-168fc",...}'
```

**Opção 3: Google Application Default Credentials (ADC)**

```bash
export GOOGLE_APPLICATION_CREDENTIALS="/caminho/para/serviceAccountKey.json"
```

**Variáveis opcionais:**
- `FIREBASE_PROJECT_ID="horlandobraga-168fc"` (útil se não usar service account completo)
- `FIREBASE_CHECK_REVOKED=1` (valida se o token foi revogado - adiciona latência)

### Configuração do Firebase no frontend (já configurado)

O arquivo `static/app.js` já está configurado com as credenciais do projeto:
- **Project ID**: `horlandobraga-168fc`
- **API Key**: `AIzaSyC5H6J8XkBAyiuv1wHCQMNVuxX1JnBU568`

**IMPORTANTE**: Você precisa criar usuários no Firebase Authentication:
1. Acesse: https://console.firebase.google.com/project/horlandobraga-168fc/authentication/users
2. Clique em "Add user"
3. Crie usuários com e-mail e senha
4. Use essas credenciais para fazer login na interface web

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
- Faça login com um usuário criado no Firebase Authentication
- Após o login, você poderá fazer upload dos 4 PDFs
