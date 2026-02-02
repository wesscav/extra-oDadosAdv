# 🚀 Guia Rápido: Deploy no AWS App Runner

## O que foi configurado

✅ **Dockerfile** - Com Tesseract e Poppler pré-instalados  
✅ **Health check** - Endpoint `/api/health` configurado  
✅ **Docker Compose** - Para testes locais  
✅ **Scripts de teste** - `test-docker.sh` e `test-docker.bat`  
✅ **GitHub Actions** - CI/CD com testes automáticos  
✅ **Documentação completa** - `DEPLOY.md` com detalhes

---

## Passo a Passo Rápido (5 minutos)

### 1️⃣ Teste Local (Opcional)

```bash
# Teste o Docker localmente antes de fazer deploy
./test-docker.sh

# Ou no Windows
test-docker.bat

# Ou com docker-compose
docker-compose up
```

Acesse http://localhost:8000 para testar.

---

### 2️⃣ Suba o Código para o GitHub

```bash
# Inicializar repositório (se ainda não tiver)
git init
git add .
git commit -m "feat: configuração para AWS App Runner"

# Conectar ao GitHub (crie um repositório novo no GitHub primeiro)
git remote add origin https://github.com/SEU-USUARIO/SEU-REPO.git
git branch -M main
git push -u origin main
```

---

### 3️⃣ Configure o AWS App Runner

#### Via Console AWS (Mais fácil)

1. **Acesse**: https://console.aws.amazon.com/apprunner/

2. **Clique em "Create service"**

3. **Source and deployment**:
   - Repository type: **Source code repository**
   - Connect to GitHub:
     - Clique em **"Add new"** (primeira vez)
     - Autorize o AWS Connector for GitHub
     - Selecione seu repositório
   - Branch: **`main`**
   - Deployment trigger: **Automatic**
   - Clique em **Next**

4. **Build settings**:
   - Configuration: **Use a Dockerfile**
   - Dockerfile path: `Dockerfile`
   - Port: `8000`
   - Clique em **Next**

5. **Service settings**:
   - Service name: `odados-adv-extraction`
   - Virtual CPU: **1 vCPU** (ou 2 para melhor performance)
   - Memory: **2 GB** (ou 4 GB para PDFs grandes)

6. **Environment variables** (IMPORTANTE):
   
   Adicione estas variáveis:
   
   | Name | Value | Type |
   |------|-------|------|
   | `OPENAI_API_KEY` | `sk-proj-...` | Plaintext |
   | `FIREBASE_PROJECT_ID` | `seu-project-id` | Plaintext |
   | `FIREBASE_SERVICE_ACCOUNT` | Copie o JSON completo | Plaintext |
   
   **Dica**: Para `FIREBASE_SERVICE_ACCOUNT`, copie todo o conteúdo do arquivo `serviceAccountKey.json` e cole como uma string única.

7. **Health check**:
   - Protocol: **HTTP**
   - Path: `/api/health`
   - Interval: **20 seconds**
   - Timeout: **10 seconds**

8. **Review and create**:
   - Revise tudo
   - Clique em **"Create & deploy"**
   - ⏳ Aguarde ~5-10 minutos

---

### 4️⃣ Pronto! 🎉

Após o deploy:

1. **URL do serviço**: App Runner fornecerá uma URL como:
   ```
   https://xxxxx.us-east-1.awsapprunner.com
   ```

2. **Teste o health check**:
   ```bash
   curl https://xxxxx.us-east-1.awsapprunner.com/api/health
   ```

3. **Acesse a aplicação**:
   ```
   https://xxxxx.us-east-1.awsapprunner.com/login
   ```

---

## Deploy Automático

Agora, sempre que você fizer push para `main`:

```bash
git add .
git commit -m "feat: nova funcionalidade"
git push origin main
```

O App Runner detectará automaticamente e fará o deploy em ~3-5 minutos! 🚀

---

## Verificar Status e Logs

### Via Console AWS

1. Acesse [AWS App Runner](https://console.aws.amazon.com/apprunner/)
2. Clique no seu serviço
3. **Event log** - Ver status do deploy
4. **Logs** - Ver logs da aplicação (CloudWatch)
5. **Metrics** - CPU, memória, requests

### Via AWS CLI

```bash
# Listar serviços
aws apprunner list-services

# Ver detalhes do serviço
aws apprunner describe-service --service-arn <arn>

# Ver logs (CloudWatch)
aws logs tail /aws/apprunner/odados-adv-extraction --follow
```

---

## Custos Estimados 💰

Com configuração básica (1 vCPU, 2 GB):

- **App Runner**: ~$25-40/mês
- **Data Transfer**: Incluído até 100 GB/mês
- **CloudWatch Logs**: ~$5/mês
- **OpenAI API**: Variável (depende do uso)

**Total**: ~$30-50/mês + OpenAI

---

## Troubleshooting 🔧

### ❌ Erro: "Tesseract not found"

**Causa**: App Runner está usando runtime gerenciado em vez de Docker.

**Solução**: No App Runner, edite o serviço e mude para **"Use a Dockerfile"**.

---

### ❌ Erro: Health check falhou

**Verificar**:
1. Porta está correta? (8000)
2. Path do health check: `/api/health`
3. Logs no CloudWatch mostram algum erro?

**Solução**: Verifique os logs e variáveis de ambiente.

---

### ❌ Erro: "OPENAI_API_KEY not set"

**Solução**: 
1. Console AWS > App Runner > Seu serviço
2. Configuration > Environment variables
3. Adicione a variável `OPENAI_API_KEY`

---

### 🐌 Deploy muito lento

**Soluções**:
1. Aumente CPU para 2 vCPU e Memory para 4 GB
2. Verifique se os PDFs não são muito grandes
3. Considere usar S3 para armazenar arquivos temporários

---

## Próximos Passos Opcionais

- [ ] **Domínio customizado**: Configure seu próprio domínio no App Runner
- [ ] **Alertas**: Configure alertas de erro no CloudWatch
- [ ] **Backup**: Armazene templates no S3
- [ ] **CI/CD avançado**: Adicione testes automatizados antes do deploy
- [ ] **Monitoramento**: Integre com Datadog/New Relic

---

## Links Úteis

- 📘 [Documentação AWS App Runner](https://docs.aws.amazon.com/apprunner/)
- 🐳 [Best practices Docker](https://docs.docker.com/develop/dev-best-practices/)
- 🔥 [Firebase Admin SDK](https://firebase.google.com/docs/admin/setup)
- 🤖 [OpenAI API](https://platform.openai.com/docs/)

---

## Suporte

Problemas? Verifique:
1. ✅ Todos os arquivos foram commitados no GitHub
2. ✅ Variáveis de ambiente estão corretas no App Runner
3. ✅ Logs no CloudWatch (busque por erros)
4. ✅ Teste local funcionou: `./test-docker.sh`

Se precisar de ajuda, consulte o `DEPLOY.md` completo com mais detalhes técnicos.

---

**Pronto para começar? Execute o passo 1 acima! 🚀**
