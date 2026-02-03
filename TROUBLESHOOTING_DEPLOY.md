# 🔍 Troubleshooting - Deploy AWS

## Problema: Redirecionamento para login em produção

Se localmente funciona mas na AWS redireciona para login, siga estes passos:

### 1️⃣ Verificar logs no Console do navegador

Acesse sua aplicação no AWS e abra o Console (F12):
- Procure por logs com prefixo `[AUTH-STATE]`, `[AUTH]`, `[SUBMIT]`
- Se aparecer "❌ Erro 401 - Token rejeitado pelo servidor", o problema é no backend

### 2️⃣ Verificar domínio autorizado no Firebase

**IMPORTANTE**: O Firebase precisa ter o domínio do AWS autorizado!

1. Acesse o Console do Firebase: https://console.firebase.google.com/
2. Selecione o projeto: `horlandobraga-168fc`
3. Vá em **Authentication** → **Settings** → **Authorized domains**
4. Adicione o domínio completo do seu App Runner, exemplo:
   - `seu-app.us-east-1.awsapprunner.com`
   - Ou o domínio customizado se você configurou

### 3️⃣ Verificar variáveis de ambiente no AWS

No AWS App Runner → Configuration → Environment variables:

Verifique se as 3 variáveis estão configuradas:
- ✅ `OPENAI_API_KEY`
- ✅ `FIREBASE_PROJECT_ID`
- ✅ `FIREBASE_SERVICE_ACCOUNT` (JSON completo)

### 4️⃣ Verificar se o JSON do Firebase está correto

O `FIREBASE_SERVICE_ACCOUNT` deve:
- Ser um JSON válido (começar com `{` e terminar com `}`)
- Estar em uma única linha
- Conter todas as chaves necessárias: `type`, `project_id`, `private_key`, `client_email`, etc.

### 5️⃣ Verificar logs do servidor AWS

No AWS App Runner → Logs:
- Procure por `[AUTH] Erro ao validar token`
- Se aparecer `JSONDecodeError`, o FIREBASE_SERVICE_ACCOUNT está mal formatado
- Se aparecer erro de Firebase, pode ser problema de credenciais

### 6️⃣ Testar manualmente

Após o deploy, teste:
1. Abra o Console do navegador (F12)
2. Faça login
3. Clique em "Extrair e Resumir"
4. Observe os logs no Console

Os logs devem mostrar:
```
[AUTH-STATE] Mudança de estado detectada. User: seu-email@...
[AUTH-STATE] ✅ Token obtido com sucesso! Tamanho: 1234 chars
[AUTH] Obtendo novo token (forceRefresh=true)
[SUBMIT] Enviando requisição /api/extract
[SUBMIT] Resposta /api/extract: status 200
```

Se aparecer status 401, há problema com autenticação.

### 🎯 Causa mais comum

**90% dos casos**: O domínio AWS não está autorizado no Firebase!

Solução rápida:
1. Copie o domínio completo da URL do AWS (ex: `xyz.us-east-1.awsapprunner.com`)
2. Adicione em Firebase Console → Authentication → Settings → Authorized domains
3. Aguarde 1-2 minutos para propagar
4. Teste novamente

---

## 📋 Checklist completo

- [ ] Domínio AWS adicionado no Firebase Authorized domains
- [ ] 3 variáveis de ambiente configuradas no AWS
- [ ] FIREBASE_SERVICE_ACCOUNT é um JSON válido em linha única
- [ ] Logs do navegador mostram token sendo obtido
- [ ] Logs do servidor não mostram erros de autenticação

Se todos os itens estiverem ✅ e ainda não funcionar, envie os logs do Console para análise.
