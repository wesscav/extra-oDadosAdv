// ⚠️ MODO MOCK - Login sem validação real (apenas para desenvolvimento)
// Qualquer email/senha será aceito

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

// Check if already "logged in" (mock)
const mockUser = localStorage.getItem("mockUser");
if (mockUser) {
  window.location.href = "/";
}

// Mock login - aceita qualquer credencial
loginForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  
  const email = emailInput.value.trim();
  const password = passwordInput.value.trim();
  
  if (!email || !password) {
    setStatus("Preencha e-mail e senha.", "error");
    return;
  }
  
  loginBtn.disabled = true;
  setStatus("Entrando...", "loading");
  
  // Simula delay de rede
  await new Promise(resolve => setTimeout(resolve, 800));
  
  try {
    // Mock: Salva "usuário" no localStorage
    const mockUserData = {
      email: email,
      uid: "mock-uid-" + Date.now(),
      displayName: email.split("@")[0],
      emailVerified: true
    };
    
    localStorage.setItem("mockUser", JSON.stringify(mockUserData));
    
    // Gera um token fake para o backend aceitar
    const mockToken = btoa(JSON.stringify({
      uid: mockUserData.uid,
      email: mockUserData.email,
      exp: Date.now() + 3600000 // 1 hora
    }));
    
    localStorage.setItem("mockToken", mockToken);
    
    setStatus("Login realizado! Redirecionando...", "success");
    
    // Redirect to main app
    setTimeout(() => {
      window.location.href = "/";
    }, 500);
    
  } catch (error) {
    console.error("Mock login error:", error);
    setStatus("Erro inesperado. Tente novamente.", "error");
  } finally {
    loginBtn.disabled = false;
  }
});
