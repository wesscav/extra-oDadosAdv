import { initializeApp } from "https://www.gstatic.com/firebasejs/10.12.5/firebase-app.js";
import { getAuth, signInWithEmailAndPassword } from "https://www.gstatic.com/firebasejs/10.12.5/firebase-auth.js";

// Firebase config
const firebaseConfig = {
  apiKey: "AIzaSyC5H6J8XkBAyiuv1wHCQMNVuxX1JnBU568",
  authDomain: "horlandobraga-168fc.firebaseapp.com",
  projectId: "horlandobraga-168fc",
  storageBucket: "horlandobraga-168fc.firebasestorage.app",
  messagingSenderId: "405988871259",
  appId: "1:405988871259:web:ff0ef83ba7e118d19b837e",
  measurementId: "G-H024RSDR79",
};

const app = initializeApp(firebaseConfig);
const auth = getAuth(app);

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

// Check if already logged in
auth.onAuthStateChanged((user) => {
  if (user) {
    // Already logged in, redirect to main app
    window.location.href = "/";
  }
});

// Login form submit
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
  
  try {
    await signInWithEmailAndPassword(auth, email, password);
    setStatus("Login realizado! Redirecionando...", "success");
    
    // Redirect to main app after successful login
    setTimeout(() => {
      window.location.href = "/";
    }, 500);
  } catch (error) {
    console.error("Login error:", error);
    
    let errorMessage = "Erro ao fazer login. Tente novamente.";
    
    if (error.code === "auth/user-not-found" || error.code === "auth/wrong-password") {
      errorMessage = "E-mail ou senha incorretos.";
    } else if (error.code === "auth/invalid-email") {
      errorMessage = "E-mail inválido.";
    } else if (error.code === "auth/too-many-requests") {
      errorMessage = "Muitas tentativas. Tente novamente mais tarde.";
    } else if (error.code === "auth/network-request-failed") {
      errorMessage = "Erro de conexão. Verifique sua internet.";
    }
    
    setStatus(errorMessage, "error");
  } finally {
    loginBtn.disabled = false;
  }
});
