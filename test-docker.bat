@echo off
REM Script para testar o Docker localmente antes do deploy (Windows)

echo 🐳 Testando build do Docker...

REM Build da imagem
docker build -t odados-adv-test .

if %ERRORLEVEL% NEQ 0 (
    echo ❌ Erro no build!
    exit /b 1
)

echo ✅ Build concluído com sucesso!
echo.
echo 🚀 Iniciando container...

REM Para qualquer container anterior
docker stop odados-adv-test-container 2>NUL
docker rm odados-adv-test-container 2>NUL

REM Verifica se .env existe
if not exist .env (
    echo ⚠️  Arquivo .env não encontrado. Criando a partir do .env.example...
    copy .env.example .env
    echo ⚠️  ATENÇÃO: Configure as variáveis em .env antes de fazer deploy!
)

REM Inicia o container com variáveis do .env
docker run -d --name odados-adv-test-container -p 8000:8000 --env-file .env odados-adv-test

echo ⏳ Aguardando inicialização (30s)...
timeout /t 30 /nobreak >NUL

REM Testa o health check
echo.
echo 🏥 Testando health check...
curl -f http://localhost:8000/api/health

if %ERRORLEVEL% EQU 0 (
    echo.
    echo ✅ Health check passou!
) else (
    echo.
    echo ❌ Health check falhou!
    docker logs odados-adv-test-container
    exit /b 1
)

echo.
echo 📊 Logs do container:
docker logs odados-adv-test-container

echo.
echo ✅ Tudo funcionando!
echo.
echo 📝 Comandos úteis:
echo   - Ver logs:        docker logs -f odados-adv-test-container
echo   - Parar container: docker stop odados-adv-test-container
echo   - Remover:         docker rm odados-adv-test-container
echo   - Acessar app:     http://localhost:8000
echo.
echo 🌐 Para testar no navegador: http://localhost:8000
echo.

pause
