#!/bin/bash
# Script para testar o Docker localmente antes do deploy

set -e

echo "🐳 Testando build do Docker..."

# Build da imagem
docker build -t odados-adv-test .

echo "✅ Build concluído com sucesso!"
echo ""
echo "🚀 Iniciando container..."

# Para qualquer container anterior
docker stop odados-adv-test-container 2>/dev/null || true
docker rm odados-adv-test-container 2>/dev/null || true

# Verifica se .env existe
if [ ! -f .env ]; then
    echo "⚠️  Arquivo .env não encontrado. Criando a partir do .env.example..."
    cp .env.example .env
    echo "⚠️  ATENÇÃO: Configure as variáveis em .env antes de fazer deploy!"
fi

# Inicia o container com variáveis do .env
docker run -d \
    --name odados-adv-test-container \
    -p 8000:8000 \
    --env-file .env \
    odados-adv-test

echo "⏳ Aguardando inicialização (30s)..."
sleep 30

# Testa o health check
echo ""
echo "🏥 Testando health check..."
if curl -f http://localhost:8000/api/health; then
    echo ""
    echo "✅ Health check passou!"
else
    echo ""
    echo "❌ Health check falhou!"
    docker logs odados-adv-test-container
    exit 1
fi

echo ""
echo "📊 Logs do container:"
docker logs odados-adv-test-container | tail -20

echo ""
echo "✅ Tudo funcionando!"
echo ""
echo "📝 Comandos úteis:"
echo "  - Ver logs:        docker logs -f odados-adv-test-container"
echo "  - Parar container: docker stop odados-adv-test-container"
echo "  - Remover:         docker rm odados-adv-test-container"
echo "  - Acessar app:     http://localhost:8000"
echo ""
echo "🌐 Para testar no navegador: http://localhost:8000"
echo ""
