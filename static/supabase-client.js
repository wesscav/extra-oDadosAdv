// Configuração do cliente Supabase
// Certifique-se de adicionar as variáveis de ambiente no backend para servir essas configs

let supabaseClient = null;
let supabaseUrl = null;
let supabaseAnonKey = null;

// Busca as configurações do Supabase do backend
async function initSupabase() {
  if (supabaseClient) {
    console.log("✅ Cliente Supabase já inicializado (usando cache)");
    return supabaseClient;
  }

  try {
    console.log("🔄 Buscando configurações do Supabase...");
    
    // Busca as configurações públicas do backend
    const response = await fetch('/api/supabase-config');
    if (!response.ok) {
      throw new Error('Falha ao carregar configurações do Supabase (HTTP ' + response.status + ')');
    }
    
    const config = await response.json();
    console.log("📦 Configurações recebidas:", { url: config.url, hasAnonKey: !!config.anonKey });
    
    supabaseUrl = config.url;
    supabaseAnonKey = config.anonKey;

    // Verifica se o Supabase SDK foi carregado do CDN
    if (typeof supabase === 'undefined') {
      throw new Error('Supabase SDK não foi carregado do CDN. Verifique a conexão.');
    }
    
    console.log("🔄 Criando cliente Supabase...");
    
    // Importa o Supabase do CDN
    const { createClient } = supabase;
    supabaseClient = createClient(supabaseUrl, supabaseAnonKey, {
      auth: {
        autoRefreshToken: true, // Renova o token automaticamente
        persistSession: true, // Persiste a sessão no localStorage
        detectSessionInUrl: true, // Detecta token na URL (útil para magic links)
        flowType: 'pkce' // Usa PKCE para maior segurança
      }
    });
    
    console.log("✅ Cliente Supabase criado com sucesso (com auto-refresh habilitado)");
    
    return supabaseClient;
  } catch (error) {
    console.error('❌ Erro ao inicializar Supabase:', error);
    throw error;
  }
}

// Exporta funções de autenticação
const SupabaseAuth = {
  async init() {
    return await initSupabase();
  },

  async signIn(email, password) {
    console.log("🔄 SupabaseAuth.signIn chamado para:", email);
    const client = await initSupabase();
    console.log("🔄 Chamando signInWithPassword...");
    
    const { data, error } = await client.auth.signInWithPassword({
      email,
      password,
    });
    
    console.log("📦 Resposta do signInWithPassword:", { hasData: !!data, hasError: !!error });
    
    if (error) {
      console.error("❌ Erro do Supabase:", error);
      throw error;
    }
    
    console.log("✅ Login bem-sucedido, retornando dados");
    return data;
  },

  async signOut() {
    const client = await initSupabase();
    const { error } = await client.auth.signOut();
    if (error) throw error;
  },

  async getSession() {
    const client = await initSupabase();
    const { data, error } = await client.auth.getSession();
    if (error) throw error;
    return data.session;
  },

  async getUser() {
    const client = await initSupabase();
    const { data, error } = await client.auth.getUser();
    if (error) throw error;
    return data.user;
  },

  onAuthStateChange(callback) {
    initSupabase().then(client => {
      client.auth.onAuthStateChange(callback);
    });
  }
};

// Torna disponível globalmente
window.SupabaseAuth = SupabaseAuth;
