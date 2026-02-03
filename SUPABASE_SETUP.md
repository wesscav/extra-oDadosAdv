# Configuração da Autenticação com Supabase

Este documento explica como configurar a autenticação com Supabase para a aplicação.

## 1. Criar uma conta no Supabase

1. Acesse [https://supabase.com](https://supabase.com)
2. Clique em "Start your project"
3. Crie uma conta (pode usar GitHub, Google, etc.)

## 2. Criar um novo projeto

1. No dashboard do Supabase, clique em "New Project"
2. Escolha um nome para o projeto (ex: "horlando-braga-app")
3. Defina uma senha segura para o banco de dados
4. Escolha a região mais próxima (ex: South America - São Paulo)
5. Clique em "Create new project" e aguarde alguns minutos

## 3. Obter as credenciais necessárias

Após o projeto ser criado:

1. No menu lateral, clique em **Settings** (⚙️)
2. Clique em **API**
3. Você verá as seguintes informações:

### Credenciais necessárias:

- **Project URL**: `https://seu-projeto.supabase.co`
  - Copie o valor em "Project URL"
  
- **anon/public key**: `eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...`
  - Copie o valor em "Project API keys" → "anon public"
  
- **service_role key**: `eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...`
  - Copie o valor em "Project API keys" → "service_role"
  - ⚠️ **ATENÇÃO**: Esta chave é secreta e não deve ser exposta no frontend!

## 4. Configurar o arquivo .env

Crie ou edite o arquivo `.env` na raiz do projeto:

```env
# OpenAI API Key (já existente)
OPENAI_API_KEY=sk-proj-...

# Supabase - Configurações de autenticação
SUPABASE_URL=https://seu-projeto.supabase.co
SUPABASE_ANON_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
SUPABASE_SERVICE_ROLE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

Substitua os valores pelas credenciais que você copiou no passo anterior.

## 5. Configurar autenticação no Supabase

### 5.1. Habilitar Email/Password

1. No menu lateral do Supabase, clique em **Authentication**
2. Clique em **Providers**
3. Certifique-se de que **Email** está habilitado
4. (Opcional) Configure outras opções como:
   - **Disable sign ups**: Se você quiser criar usuários manualmente
   - **Email confirmations**: Se você quer que usuários confirmem o email

### 5.2. Configurar Email Templates (Opcional)

1. Ainda em **Authentication**, clique em **Email Templates**
2. Aqui você pode personalizar os emails de:
   - Confirmação de cadastro
   - Recuperação de senha
   - Magic Link

## 6. Criar usuários

### Opção A: Criar manualmente pelo dashboard

1. No menu lateral, clique em **Authentication**
2. Clique na aba **Users**
3. Clique em **Add user** → **Create new user**
4. Preencha:
   - Email do usuário
   - Senha (mínimo 6 caracteres)
   - (Opcional) Marque "Auto Confirm User" para não precisar confirmar o email
5. Clique em **Create user**

### Opção B: Criar via SQL (múltiplos usuários)

1. No menu lateral, clique em **SQL Editor**
2. Clique em **New query**
3. Cole o seguinte SQL:

```sql
-- Insere um novo usuário diretamente na tabela auth.users
INSERT INTO auth.users (
  instance_id,
  id,
  aud,
  role,
  email,
  encrypted_password,
  email_confirmed_at,
  created_at,
  updated_at,
  confirmation_token,
  raw_user_meta_data
)
VALUES (
  '00000000-0000-0000-0000-000000000000',
  gen_random_uuid(),
  'authenticated',
  'authenticated',
  'usuario@exemplo.com', -- SUBSTITUA pelo email desejado
  crypt('senha123', gen_salt('bf')), -- SUBSTITUA pela senha desejada
  NOW(), -- Auto-confirma o email
  NOW(),
  NOW(),
  '',
  '{"provider":"email","providers":["email"]}'::jsonb
);
```

4. Substitua `usuario@exemplo.com` e `senha123` pelos valores desejados
5. Clique em **Run** ou pressione `Ctrl+Enter`
6. Repita para cada usuário que deseja criar

### Opção C: Criar via API Python (script)

Crie um arquivo `create_user.py`:

```python
import os
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

# Inicializa cliente Supabase com service_role_key (admin)
url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
supabase: Client = create_client(url, key)

# Cria um novo usuário
email = "usuario@exemplo.com"
password = "senha123"

try:
    response = supabase.auth.admin.create_user({
        "email": email,
        "password": password,
        "email_confirm": True  # Auto-confirma o email
    })
    print(f"✅ Usuário criado: {response.user.email}")
    print(f"   ID: {response.user.id}")
except Exception as e:
    print(f"❌ Erro ao criar usuário: {e}")
```

Execute:
```bash
python create_user.py
```

## 7. Instalar dependências

Instale as novas dependências Python:

```bash
pip install -r requirements.txt
```

## 8. Testar a aplicação

1. Inicie o servidor:
```bash
python server.py
```

2. Acesse: [http://localhost:8000/login](http://localhost:8000/login)

3. Faça login com um dos usuários criados

## Solução de Problemas

### Erro: "Credenciais do Supabase não configuradas"
- Verifique se o arquivo `.env` está na raiz do projeto
- Verifique se as variáveis `SUPABASE_URL`, `SUPABASE_ANON_KEY` e `SUPABASE_SERVICE_ROLE_KEY` estão definidas
- Reinicie o servidor após editar o `.env`

### Erro: "Invalid login credentials"
- Verifique se o email e senha estão corretos
- Verifique se o usuário foi criado corretamente no Supabase
- Se habilitou "Email confirmations", certifique-se de que o usuário confirmou o email

### Erro: "Token inválido ou expirado"
- Faça logout e login novamente
- Verifique se as chaves API do Supabase estão corretas
- Verifique se o projeto do Supabase está ativo

## Recursos Adicionais

- [Documentação do Supabase](https://supabase.com/docs)
- [Supabase Auth Docs](https://supabase.com/docs/guides/auth)
- [Python Client Docs](https://supabase.com/docs/reference/python/introduction)
