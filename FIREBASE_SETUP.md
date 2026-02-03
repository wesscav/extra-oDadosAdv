# Guia de Configuração - Firebase Authentication

Este guia explica como configurar a autenticação Firebase para proteger as rotas da aplicação.

## 🔐 O que foi implementado

### Rotas protegidas (requerem login):
- `POST /api/extract` - Extração de dados dos PDFs
- `POST /api/generate-docx` - Geração do documento .docx

### Rota pública:
- `GET /` - Interface web (página de login + upload)

## 📋 Passo a passo

### 1. Obter Service Account Key do Firebase

1. Acesse o [Firebase Console](https://console.firebase.google.com/project/horlandobraga-168fc/settings/serviceaccounts/adminsdk)
2. Clique em **"Generate new private key"**
3. Salve o arquivo `serviceAccountKey.json` em um local seguro
4. **⚠️ IMPORTANTE**: Adicione `serviceAccountKey.json` ao `.gitignore` (nunca commite esse arquivo!)

### 2. Configurar variável de ambiente

Escolha uma das opções:

**Opção A: Usando arquivo .env (recomendado)**

Crie um arquivo `.env` na raiz do projeto:

```bash
OPENAI_API_KEY=sk-proj-...
FIREBASE_SERVICE_ACCOUNT_JSON=C:\caminho\completo\para\serviceAccountKey.json
FIREBASE_PROJECT_ID=horlandobraga-168fc
```

**Opção B: Variável de ambiente do sistema (Windows)**

```powershell
$env:FIREBASE_SERVICE_ACCOUNT_JSON="C:\caminho\para\serviceAccountKey.json"
```

**Opção C: Variável de ambiente do sistema (Linux/Mac)**

```bash
export FIREBASE_SERVICE_ACCOUNT_JSON="/caminho/para/serviceAccountKey.json"
```

### 3. Criar usuários no Firebase Authentication

1. Acesse: https://console.firebase.google.com/project/horlandobraga-168fc/authentication/users
2. Clique em **"Add user"**
3. Preencha:
   - **Email**: exemplo@dominio.com
   - **Password**: SuaSenhaSegura123
4. Clique em **"Add user"**

Repita para criar todos os usuários que precisam ter acesso.

### 4. Testar a aplicação

```bash
# Instalar dependências
pip install -r requirements.txt

# Rodar servidor
uvicorn server:app --reload

# Abrir navegador
# http://127.0.0.1:8000
```

**Na interface web:**

1. **Faça login** com o e-mail e senha criados no Firebase
2. Após o login bem-sucedido, o formulário de upload será habilitado
3. Selecione **1 ou mais arquivos PDF**
4. Clique em **"Extrair e resumir"**
5. Confirme os dados no modal
6. Clique em **"Confirmar e gerar .docx"** para baixar o documento

## 🔍 Testando proteção das rotas

### Sem autenticação (deve retornar 401):

```bash
curl -X POST http://127.0.0.1:8000/api/extract
# {"detail":"Não autenticado. Envie Authorization: Bearer <idToken>."}
```

### Com autenticação (deve funcionar):

1. Faça login na interface web
2. Abra o DevTools do navegador (F12)
3. Vá para a aba **Network**
4. Faça upload dos PDFs
5. Veja a requisição para `/api/extract` e copie o header `Authorization: Bearer eyJ...`
6. Use esse token no curl:

```bash
curl -X POST http://127.0.0.1:8000/api/extract \
  -H "Authorization: Bearer eyJ..." \
  -F "files=@arquivo1.pdf" \
  -F "files=@arquivo2.pdf"
```

## ⚙️ Variáveis de ambiente disponíveis

| Variável | Obrigatório | Descrição |
|----------|-------------|-----------|
| `OPENAI_API_KEY` | ✅ Sim | Chave da API OpenAI |
| `FIREBASE_SERVICE_ACCOUNT_JSON` | ✅ Sim* | Caminho para serviceAccountKey.json |
| `FIREBASE_SERVICE_ACCOUNT` | ✅ Sim* | JSON string do service account |
| `GOOGLE_APPLICATION_CREDENTIALS` | ✅ Sim* | ADC do Google Cloud |
| `FIREBASE_PROJECT_ID` | ⚠️ Opcional | ID do projeto (recomendado) |
| `FIREBASE_CHECK_REVOKED` | ⚠️ Opcional | `1` para validar revogação |

\* Escolha **uma** das 3 opções de credencial do Firebase

## 🚨 Troubleshooting

### Erro: "Não autenticado"
- Verifique se você fez login na interface web
- Verifique se o token não expirou (expire após 1 hora)
- Faça logout e login novamente

### Erro: "Could not load the default credentials"
- Verifique se a variável `FIREBASE_SERVICE_ACCOUNT_JSON` está configurada corretamente
- Verifique se o caminho do arquivo está correto
- Verifique se o arquivo `serviceAccountKey.json` existe e é válido

### Erro: "Invalid email or password" no login
- Verifique se o usuário foi criado no Firebase Authentication
- Verifique se o e-mail e senha estão corretos
- Verifique se o método "Email/Password" está habilitado no Firebase Console

## 📚 Mais informações

- [Firebase Admin SDK - Python](https://firebase.google.com/docs/admin/setup)
- [Firebase Authentication](https://firebase.google.com/docs/auth)
- [Verificar ID Tokens](https://firebase.google.com/docs/auth/admin/verify-id-tokens)
