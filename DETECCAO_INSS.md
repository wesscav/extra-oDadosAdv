# Detecção Automática de Documentos INSS

## O Que Foi Implementado

Sistema inteligente de detecção de documentos do INSS que processa **apenas as 6 primeiras páginas** (onde estão as informações relevantes), ignorando as ~70 páginas restantes que são apenas anexos e formulários padronizados.

## Como Funciona

### 1. Detecção Automática

O sistema:
1. Extrai **apenas a primeira página** do documento (rápido: ~5 segundos)
2. Procura por palavras-chave no texto:
   - `inss`
   - `instituto nacional do seguro social`
   - `benefício previdenciário`
   - `auxílio-doença`
   - `perícia médica federal`
3. Se detectar → processa apenas páginas 1-6
4. Se não detectar → processa tudo normalmente

### 2. Economia de Recursos

**Exemplo Real (everton5.pdf):**
- **Sem otimização:** 63 páginas × ~7s = ~7 minutos
- **Com otimização:** 6 páginas × ~7s = ~40 segundos
- **Economia:** 85% de tempo + 90% de custo (se usar OpenAI depois)

## Como Usar

### Via Linha de Comando

```bash
# Com detecção automática (recomendado)
python extract_ocr.py "documento.pdf" -o output.json --poppler-path "CAMINHO_DO_POPPLER" --auto-detect-inss

# Forçar limite de páginas manualmente
python extract_ocr.py "documento.pdf" -o output.json --poppler-path "CAMINHO_DO_POPPLER" --first-page 1 --last-page 6

# Processar intervalo específico
python extract_ocr.py "documento.pdf" -o output.json --poppler-path "CAMINHO_DO_POPPLER" --first-page 3 --last-page 10
```

### Via API (webapp)

```bash
# Iniciar o servidor
cd webapp
uvicorn app:app --reload
```

A API automaticamente detecta documentos INSS ao processar uploads. O parâmetro `auto_detect_inss` é `True` por padrão.

```python
# Exemplo de chamada à API
import requests

files = {'files': open('documento_inss.pdf', 'rb')}
data = {
    'dpi': 300,
    'lang': 'por',
    'auto_detect_inss': True  # Padrão
}

response = requests.post('http://localhost:8000/api/ocr', files=files, data=data)
result = response.json()

# O resultado inclui:
# - document_type: "INSS" ou "padrão"
# - filename: nome do arquivo
# - pages: apenas as páginas processadas
```

## Estrutura do JSON de Saída

```json
{
  "extractions": [
    {
      "source": "caminho/completo/documento.pdf",
      "page_count": 6,
      "document_type": "INSS",
      "filename": "documento.pdf",
      "pages": [
        {
          "page_number": 1,
          "text": "INSS - Instituto Nacional...",
          "words": [...]
        }
      ]
    }
  ]
}
```

## Adicionando Novos Tipos de Documento

Para adicionar detecção de outros tipos (ex: Tribunal de Justiça), edite:

### extract_ocr.py (linha ~175)

```python
# Após a detecção INSS, adicione:

# Detectar documentos do Tribunal de Justiça (exemplo)
if 'tribunal de justiça' in first_page_text or 'tj-' in first_page_text:
    print('Documento TJ detectado - processando apenas primeiras 10 paginas')
    first_page = 1
    last_page = 10
```

### webapp/app.py (linha ~110)

```python
# Após os keywords do INSS, adicione:

tj_keywords = ['tribunal de justiça', 'comarca', 'processo judicial']
is_tj = any(keyword in first_page_text for keyword in tj_keywords)

if is_tj:
    doc_type = "TJ"
    first_page = 1
    last_page = 10
```

## Testes Realizados

✅ **everton5.pdf** (63 páginas)
- Detectado como INSS ✓
- Processadas apenas 6 páginas ✓
- Tempo: ~40 segundos ✓
- Economizou ~6 minutos ✓

## Próximos Passos Sugeridos

1. **Frontend:** Mostrar indicador visual "Documento INSS detectado - otimizando processamento"
2. **Logs:** Salvar estatísticas de processamento (tempo economizado, páginas ignoradas)
3. **Configuração:** Permitir que usuário ajuste limite de páginas por tipo via interface
4. **IA Avançada:** Usar OpenAI para detectar quando informações relevantes terminam (além de keywords fixos)

## Observações Importantes

- A detecção é **case-insensitive** (não diferencia maiúsculas/minúsculas)
- Se a detecção falhar, o documento é processado completamente (fallback seguro)
- O sistema funciona tanto no Windows (local) quanto em servidores Linux (Docker/Deploy)
- Encoding corrigido para Windows (sem caracteres especiais nos prints)
