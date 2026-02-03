// Autenticação real com Supabase

// Elements
const loginForm = document.getElementById("loginForm");
const emailInput = document.getElementById("email");
const passwordInput = document.getElementById("password");
const loginBtn = document.getElementById("loginBtn");
const statusEl = document.getElementById("status");

function setStatus(message, type = "") {
  statusEl.textContent = message;
  statusEl.className = "status" + (type ? ` ${type}` : "");
}

// Verifica se o Supabase está disponível
function checkSupabaseAvailable() {
  if (typeof window.SupabaseAuth === 'undefined') {
    console.error("❌ SupabaseAuth não está disponível!");
    setStatus("Erro: Sistema de autenticação não carregado. Recarregue a página.", "error");
    return false;
  }
  console.log("✅ SupabaseAuth disponível");
  return true;
}

// Inicializa Supabase e verifica se já está logado
async function checkAuth() {
  if (!checkSupabaseAvailable()) {
    return;
  }
  
  try {
    console.log("🔄 Inicializando Supabase...");
    await SupabaseAuth.init();
    console.log("✅ Supabase inicializado");
    
    const session = await SupabaseAuth.getSession();
    
    if (session) {
      console.log("✅ Usuário já autenticado, redirecionando...");
      window.location.href = "/";
    } else {
      console.log("ℹ️ Nenhuma sessão ativa");
    }
  } catch (error) {
    console.error("❌ Erro ao verificar autenticação:", error);
    setStatus("Erro ao inicializar autenticação: " + error.message, "error");
  }
}

// Aguarda o carregamento do DOM e do Supabase
window.addEventListener('load', () => {
  console.log("🔄 Página carregada, verificando autenticação...");
  // Aguarda um pouco para garantir que os scripts foram carregados
  setTimeout(checkAuth, 100);
});

// Login com Supabase
loginForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  
  console.log("🔄 Tentando fazer login...");
  
  if (!checkSupabaseAvailable()) {
    return;
  }
  
  const email = emailInput.value.trim();
  const password = passwordInput.value.trim();
  
  if (!email || !password) {
    setStatus("Preencha e-mail e senha.", "error");
    return;
  }
  
  loginBtn.disabled = true;
  setStatus("Entrando...", "loading");
  
  try {
    console.log("🔄 Autenticando com Supabase...", email);
    
    // Autentica com Supabase
    const result = await SupabaseAuth.signIn(email, password);
    console.log("📦 Resultado do login:", result);
    
    if (!result || !result.session || !result.user) {
      console.error("❌ Resposta inválida do Supabase:", result);
      throw new Error("Falha ao obter sessão de autenticação.");
    }
    
    console.log("✅ Login realizado com sucesso:", result.user.email);
    setStatus("Login realizado! Redirecionando...", "success");
    
    // Redirect to main app
    setTimeout(() => {
      window.location.href = "/";
    }, 500);
    
  } catch (error) {
    console.error("❌ Erro no login:", error);
    console.error("❌ Tipo do erro:", typeof error);
    console.error("❌ Mensagem do erro:", error?.message);
    
    // Mensagens de erro amigáveis
    let errorMessage = "Erro ao fazer login. Tente novamente.";
    
    const errorMsg = error?.message || String(error);
    
    if (errorMsg.includes("Invalid login credentials")) {
      errorMessage = "E-mail ou senha incorretos.";
    } else if (errorMsg.includes("Email not confirmed")) {
      errorMessage = "Confirme seu e-mail antes de fazer login.";
    } else if (errorMsg.includes("network") || errorMsg.includes("fetch")) {
      errorMessage = "Erro de conexão. Verifique sua internet.";
    } else {
      errorMessage = `Erro: ${errorMsg}`;
    }
    
    setStatus(errorMessage, "error");
  } finally {
    loginBtn.disabled = false;
  }
});
