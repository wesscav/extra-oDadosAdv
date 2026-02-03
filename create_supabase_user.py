#!/usr/bin/env python3
"""
Script para criar usuários no Supabase via API.
"""
import os
from supabase import create_client, Client
from dotenv import load_dotenv

# Carrega variáveis de ambiente
load_dotenv()

# Inicializa cliente Supabase com service_role_key (privilégios admin)
url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

if not url or not key:
    print("❌ Erro: SUPABASE_URL e SUPABASE_SERVICE_ROLE_KEY não encontrados no .env")
    exit(1)

supabase: Client = create_client(url, key)

print("=" * 60)
print("CRIAR NOVO USUÁRIO NO SUPABASE")
print("=" * 60)

# Solicita dados do usuário
email = input("\nEmail do usuário: ").strip()
if not email:
    print("❌ Email é obrigatório")
    exit(1)

password = input("Senha (mínimo 6 caracteres): ").strip()
if not password or len(password) < 6:
    print("❌ Senha deve ter no mínimo 6 caracteres")
    exit(1)

print("\n🔄 Criando usuário...")

try:
    # Cria usuário usando o admin API
    response = supabase.auth.admin.create_user({
        "email": email,
        "password": password,
        "email_confirm": True  # Auto-confirma o email
    })
    
    print("\n" + "=" * 60)
    print("✅ USUÁRIO CRIADO COM SUCESSO!")
    print("=" * 60)
    print(f"   Email: {response.user.email}")
    print(f"   ID: {response.user.id}")
    print(f"   Email confirmado: Sim")
    print("=" * 60)
    print("\n✅ Agora você pode fazer login com:")
    print(f"   Email: {email}")
    print(f"   Senha: {password}")
    print("\n🌐 Acesse: http://localhost:8000/login")
    
except Exception as e:
    print("\n" + "=" * 60)
    print("❌ ERRO AO CRIAR USUÁRIO")
    print("=" * 60)
    print(f"Erro: {e}")
    
    # Dicas de troubleshooting
    if "User already registered" in str(e):
        print("\n💡 Este email já está cadastrado!")
        print("   Tente fazer login ou use outro email.")
    elif "Invalid email" in str(e):
        print("\n💡 Email inválido!")
        print("   Use um formato válido: usuario@exemplo.com")
    else:
        print("\n💡 Verifique se:")
        print("   1. As credenciais do Supabase no .env estão corretas")
        print("   2. O projeto do Supabase está ativo")
        print("   3. Você tem conexão com a internet")
    
    print("=" * 60)
