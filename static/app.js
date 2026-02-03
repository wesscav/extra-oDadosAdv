// Autenticação real com Supabase

const els = {
  form: document.getElementById("uploadForm"),
  files: document.getElementById("files"),
  dropzone: document.getElementById("dropzone"),
  fileHelp: document.getElementById("fileHelp"),
  submitBtn: document.getElementById("submitBtn"),
  status: document.getElementById("status"),

  logoutBtn: document.getElementById("logoutBtn"),

  modalBackdrop: document.getElementById("modalBackdrop"),
  closeModalBtn: document.getElementById("closeModalBtn"),
  cancelBtn: document.getElementById("cancelBtn"),
  confirmBtn: document.getElementById("confirmBtn"),

  summary: document.getElementById("summary"),
};

let currentUser = null;
let currentSession = null;
let currentToken = null;
let structuredDraft = null;

const ALWAYS_NACIONALIDADE = "brasileiro(a)";

function setStatus(text, kind = "") {
  els.status.textContent = text || "";
  els.status.className = "status" + (kind ? ` ${kind}` : "");
}

function fmt(v) {
  if (v === null || v === undefined || v === "") return "—";
  return String(v);
}

function valueForInput(v) {
  if (v === null || v === undefined) return "";
  return String(v);
}

function deepClone(obj) {
  return JSON.parse(JSON.stringify(obj || {}));
}

function capitalizeName(name) {
  if (!name || typeof name !== "string") return name;
  
  // Lista de preposições e artigos que devem ficar em minúscula (exceto se forem a primeira palavra)
  const lowercaseWords = new Set(['da', 'de', 'do', 'das', 'dos', 'e', 'em', 'na', 'no', 'a', 'o']);
  
  const words = name.trim().split(/\s+/);
  const result = words.map((word, i) => {
    // Primeira palavra sempre capitalizada
    if (i === 0) {
      return word.charAt(0).toUpperCase() + word.slice(1).toLowerCase();
    }
    // Preposições e artigos em minúscula
    if (lowercaseWords.has(word.toLowerCase())) {
      return word.toLowerCase();
    }
    // Outras palavras capitalizadas
    return word.charAt(0).toUpperCase() + word.slice(1).toLowerCase();
  });
  
  return result.join(' ');
}

function formatCPF(cpf) {
  if (!cpf || typeof cpf !== "string") return cpf;
  
  // Remove tudo que não é dígito
  const digits = cpf.replace(/\D/g, '');
  
  // Se não tem 11 dígitos, retorna original
  if (digits.length !== 11) return cpf;
  
  // Formata XXX.XXX.XXX-XX
  return `${digits.slice(0, 3)}.${digits.slice(3, 6)}.${digits.slice(6, 9)}-${digits.slice(9)}`;
}

function formatCID(cid) {
  if (!cid || typeof cid !== "string") return cid;
  
  cid = cid.trim().toUpperCase();
  
  // Se já começa com CID, normaliza
  if (cid.startsWith('CID')) {
    cid = cid.replace(/CID\s*-?\s*/i, 'CID-');
    return cid;
  }
  
  // Se é só o código (ex: F84.0), adiciona CID-
  if (cid.length >= 3 && /^[A-Z]/.test(cid)) {
    return `CID-${cid}`;
  }
  
  return cid;
}

function capitalizeMedicalTerm(term) {
  if (!term || typeof term !== "string") return term;
  
  const lowercaseWords = new Set(['de', 'da', 'do', 'das', 'dos', 'e', 'em', 'na', 'no', 'a', 'o', 'com', 'por']);
  const uppercaseTerms = new Set(['tea', 'tdah', 'toc', 'tpt', 'tag']);
  
  const words = term.trim().split(/\s+/);
  const result = words.map((word, i) => {
    const wordLower = word.toLowerCase();
    
    // Primeira palavra
    if (i === 0) {
      if (uppercaseTerms.has(wordLower)) {
        return word.toUpperCase();
      }
      return word.charAt(0).toUpperCase() + word.slice(1).toLowerCase();
    }
    // Siglas em maiúscula
    if (uppercaseTerms.has(wordLower)) {
      return word.toUpperCase();
    }
    // Preposições em minúscula
    if (lowercaseWords.has(wordLower)) {
      return wordLower;
    }
    // Outras palavras capitalizadas
    return word.charAt(0).toUpperCase() + word.slice(1).toLowerCase();
  });
  
  return result.join(' ');
}

function getFieldType(path) {
  if (!path || path.length === 0) return 'lowercase';
  
  const last = path[path.length - 1];
  
  const nameFields = new Set([
    'nome',
    'representante_legal_nome',
    'nome_do_medico',
    'nome_medico',
    'primeiro_nome_do_autor',
    'nome_avo',
  ]);
  
  const addressFields = new Set(['endereco_completo']);
  
  const cpfFields = new Set([
    'cpf',
    'representante_legal_cpf',
  ]);
  
  const cidFields = new Set([
    'CID_da_doenca',
    'cid',
  ]);
  
  const medicalFields = new Set([
    'especialidade_do_medico',
    'deficiencia_constatada',
    'deficiencia_e_CID',
    'deficiencia_associada_e_CID',
    'medicamento_prescrito',
  ]);
  
  if (nameFields.has(last) || addressFields.has(last)) {
    return 'name';
  } else if (cpfFields.has(last)) {
    return 'cpf';
  } else if (cidFields.has(last)) {
    return 'cid';
  } else if (medicalFields.has(last)) {
    return 'medical';
  }
  
  return 'lowercase';
}

function setDeep(structured, path, value) {
  if (!structured || typeof structured !== "object") return;
  if (!Array.isArray(path) || path.length === 0) return;

  // regra fixa: nacionalidade sempre "brasileiro(a)"
  if (path.length === 2 && path[0] === "qualificacao_parte_autora" && path[1] === "nacionalidade") {
    if (!structured.qualificacao_parte_autora || typeof structured.qualificacao_parte_autora !== "object") {
      structured.qualificacao_parte_autora = {};
    }
    structured.qualificacao_parte_autora.nacionalidade = ALWAYS_NACIONALIDADE;
    return;
  }

  let cur = structured;
  for (let i = 0; i < path.length - 1; i++) {
    const key = path[i];
    if (!cur[key] || typeof cur[key] !== "object") cur[key] = {};
    cur = cur[key];
  }
  const last = path[path.length - 1];
  const trimmed = (value ?? "").toString().trim();
  
  // Aplica formatação apropriada baseada no tipo de campo
  let normalized;
  if (trimmed === "") {
    normalized = null;
  } else {
    const fieldType = getFieldType(path);
    
    switch (fieldType) {
      case 'name':
        normalized = capitalizeName(trimmed);
        break;
      case 'cpf':
        normalized = formatCPF(trimmed);
        break;
      case 'cid':
        normalized = formatCID(trimmed);
        break;
      case 'medical':
        normalized = capitalizeMedicalTerm(trimmed);
        break;
      default:
        normalized = trimmed.toLowerCase();
    }
  }
  
  cur[last] = normalized;
}

function ensureDefaults(structured) {
  if (!structured || typeof structured !== "object") return structured;
  if (!structured.qualificacao_parte_autora || typeof structured.qualificacao_parte_autora !== "object") {
    structured.qualificacao_parte_autora = {};
  }
  structured.qualificacao_parte_autora.nacionalidade = ALWAYS_NACIONALIDADE;
  return structured;
}

function openModal() {
  els.modalBackdrop.classList.remove("hidden");
  els.modalBackdrop.setAttribute("aria-hidden", "false");
}

function closeModal() {
  els.modalBackdrop.classList.add("hidden");
  els.modalBackdrop.setAttribute("aria-hidden", "true");
}

function autosizeTextarea(el) {
  if (!el || el.tagName?.toLowerCase() !== "textarea") return;
  // reseta e recalcula para caber TODO o conteúdo (sem scroll interno)
  el.style.height = "auto";
  el.style.height = `${el.scrollHeight}px`;
}

async function authHeaders(extraHeaders = {}) {
  if (!currentSession || !currentSession.access_token) {
    console.error("Sessão não encontrada");
    throw new Error("Você precisa estar logado.");
  }
  
  try {
    // SEMPRE tenta renovar a sessão antes de fazer uma requisição
    // Isso garante que sempre temos um token válido
    try {
      console.log("🔄 Renovando sessão antes da requisição...");
      const newSession = await SupabaseAuth.getSession();
      if (newSession && newSession.access_token) {
        currentSession = newSession;
        console.log("✅ Sessão renovada com sucesso");
      }
    } catch (refreshError) {
      console.warn("⚠️ Não foi possível renovar a sessão, usando token atual:", refreshError);
      // Continua com o token atual se a renovação falhar
    }
    
    return { 
      ...extraHeaders, 
      Authorization: `Bearer ${currentSession.access_token}` 
    };
  } catch (error) {
    console.error("Erro ao obter token:", error);
    throw new Error("Falha ao obter token de autenticação. Faça login novamente.");
  }
}

function get(structured, path) {
  let cur = structured;
  for (const key of path) {
    if (!cur || typeof cur !== "object") return null;
    cur = cur[key];
    if (cur === undefined || cur === null) return null;
  }
  return cur;
}

function renderSummaryFromStructured(structured) {
  els.summary.innerHTML = "";

  // Campos esperados no resumo (não inclui socioeconômicos e processuais)
  const blocks = [
    [
      "Qualificação (Dados Pessoais)",
      [
        ["Nome", ["qualificacao_parte_autora", "nome"]],
        ["Nacionalidade", ["qualificacao_parte_autora", "nacionalidade"]],
        ["Estado civil", ["qualificacao_parte_autora", "estado_civil"]],
        ["Profissão", ["qualificacao_parte_autora", "profissao"]],
        ["CPF (autor)", ["qualificacao_parte_autora", "cpf"]],
        ["Representante legal", ["qualificacao_parte_autora", "representante_legal_nome"]],
        ["CPF (representante)", ["qualificacao_parte_autora", "representante_legal_cpf"]],
        ["RG (representante)", ["qualificacao_parte_autora", "representante_legal_rg"]],
        ["Endereço completo", ["qualificacao_parte_autora", "endereco_completo"]],
      ],
    ],
    [
      "Dados do Processo Administrativo (INSS)",
      [
        ["Número do benefício (NB)", ["dados_requerimento_inss", "numero_beneficio_NB"]],
        ["Data de entrada do requerimento (DER)", ["dados_requerimento_inss", "DER_data_entrada_requerimento"]],
      ],
    ],
    [
      "Dados Clínicos Gerais",
      [
        ["Deficiência constatada (laudo)", ["dados_medicos", "laudo_principal", "deficiencia_constatada"]],
        ["CID", ["dados_medicos", "laudo_principal", "CID_da_doenca"]],
      ],
    ],
    [
      "Detalhamento do Primeiro Laudo Médico",
      [
        ["Data do laudo", ["dados_medicos", "laudo_principal", "data_do_laudo"]],
        ["Especialidade do médico", ["dados_medicos", "laudo_principal", "especialidade_do_medico"]],
        ["Nome do médico", ["dados_medicos", "laudo_principal", "nome_do_medico"]],
        ["Descrição do laudo", ["dados_medicos", "laudo_principal", "trecho_clinico_relevante"]],
      ],
    ],
    [
      "Dados Escolares/Pedagógicos",
      [
        ["Data de emissão do relatório escolar", ["dados_medicos", "relatorio_escolar", "data_emissao"]],
        ["Primeiro nome do autor", ["dados_medicos", "relatorio_escolar", "primeiro_nome_do_autor"]],
        ["Resumo do relatório escolar", ["dados_medicos", "relatorio_escolar", "resumo"]],
        // o texto do template pode variar; aqui mostramos como “continuação”
        ["Continuação do resumo do relatório escolar", ["dados_medicos", "relatorio_escolar", "resumo_continuacao"]],
      ],
    ],
    [
      "Detalhamento do Segundo Laudo (Psiquiátrico)",
      [
        ["Data do segundo laudo", ["dados_medicos", "laudo_psiquiatrico_segundo_laudo", "data_segundo_laudo"]],
        ["Nome do médico", ["dados_medicos", "laudo_psiquiatrico_segundo_laudo", "nome_medico"]],
        ["Resumo do laudo", ["dados_medicos", "laudo_psiquiatrico_segundo_laudo", "resumo"]],
      ],
    ],
    [
      "Conclusão Médica e Medicamentos",
      [
        ["Conclusão médica", ["dados_medicos", "diagnostico_final_tratamento", "conclusao_medica"]],
        ["Deficiência e CID (principal)", ["dados_medicos", "diagnostico_final_tratamento", "deficiencia_e_CID"]],
        ["Deficiência e CID (secundária/associada)", ["dados_medicos", "diagnostico_final_tratamento", "deficiencia_associada_e_CID"]],
        ["Medicamento prescrito", ["dados_medicos", "diagnostico_final_tratamento", "medicamento_prescrito"]],
        ["Finalidade do medicamento", ["dados_medicos", "diagnostico_final_tratamento", "finalidade_medicamento"]],
      ],
    ],
  ];

  function wantsTextarea(path) {
    const last = path[path.length - 1] || "";
    return (
      last.includes("resumo") ||
      last.includes("trecho_") ||
      last.includes("finalidade_") ||
      last.includes("endereco") ||
      last.includes("observacao") ||
      last.includes("conclusao_medica")
    );
  }

  for (const [title, fields] of blocks) {
    const block = document.createElement("div");
    block.className = "block";

    const h = document.createElement("div");
    h.className = "block-title";
    h.textContent = title;
    block.appendChild(h);

    const kv = document.createElement("div");
    kv.className = "kv";
    for (const [label, path] of fields) {
      const field = document.createElement("div");
      field.className = "field";

      const k = document.createElement("div");
      k.className = "k";
      k.textContent = label;

      const isNacionalidade = path.length === 2 && path[0] === "qualificacao_parte_autora" && path[1] === "nacionalidade";
      const currentVal = isNacionalidade ? ALWAYS_NACIONALIDADE : get(structured, path);

      // garante default antes de renderizar
      if (isNacionalidade) {
        setDeep(structured, path, ALWAYS_NACIONALIDADE);
      }

      const v = wantsTextarea(path) ? document.createElement("textarea") : document.createElement("input");
      if (v.tagName.toLowerCase() === "input") v.type = "text";
      v.className = "field-input";
      
      // Não força lowercase no display - mantém capitalização original
      const displayValue = valueForInput(currentVal);
      v.value = displayValue;
      
      if (isNacionalidade) {
        v.readOnly = true;
        v.title = 'Valor fixo: "brasileiro(a)"';
      }

      v.addEventListener("input", () => {
        setDeep(structured, path, v.value);
        autosizeTextarea(v);
      });

      // ajusta altura inicial para textareas (após value set)
      requestAnimationFrame(() => autosizeTextarea(v));

      field.appendChild(k);
      field.appendChild(v);
      kv.appendChild(field);
    }
    block.appendChild(kv);
    els.summary.appendChild(block);
  }
}

function updateFileHelp() {
  const files = els.files.files ? Array.from(els.files.files) : [];
  if (!files.length) {
    els.fileHelp.textContent = "Nenhum arquivo selecionado.";
    return;
  }
  const lines = files.map((f, i) => `${i + 1}. ${f.name}`);
  els.fileHelp.textContent = `${files.length} arquivo(s):\n` + lines.join(" | ");
}

els.files.addEventListener("change", updateFileHelp);

function setDropzoneActive(active) {
  if (!els.dropzone) return;
  els.dropzone.classList.toggle("is-dragover", !!active);
}

function setFilesFromList(fileList) {
  const incoming = Array.from(fileList || []).filter((f) => f && typeof f.name === "string");
  if (!incoming.length) return;

  const allowedExtensions = ['.pdf', '.png', '.jpg', '.jpeg'];
  const validFiles = incoming.filter((f) => {
    const name = f.name.toLowerCase();
    return allowedExtensions.some(ext => name.endsWith(ext));
  });
  
  if (validFiles.length !== incoming.length) {
    setStatus("Alguns arquivos foram ignorados (apenas PDF, PNG ou JPG aceitos).", "error");
  } else {
    setStatus("");
  }

  // Limita ao que o usuário escolheu/soltou; validação final (mín. 1 arquivo) continua no submit.
  const selected = validFiles;
  try {
    const dt = new DataTransfer();
    for (const f of selected) dt.items.add(f);
    els.files.files = dt.files;
  } catch {
    // fallback: se o navegador não permitir programaticamente, mantemos o input como está
    setStatus("Seu navegador não permite arrastar e soltar aqui. Clique para selecionar os arquivos.", "error");
    return;
  }
  updateFileHelp();
}

if (els.dropzone) {
  els.dropzone.addEventListener("click", () => els.files?.click());
  els.dropzone.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      els.files?.click();
    }
  });
  els.dropzone.addEventListener("dragenter", (e) => {
    e.preventDefault();
    setDropzoneActive(true);
  });
  els.dropzone.addEventListener("dragover", (e) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = "copy";
    setDropzoneActive(true);
  });
  els.dropzone.addEventListener("dragleave", () => setDropzoneActive(false));
  els.dropzone.addEventListener("drop", (e) => {
    e.preventDefault();
    setDropzoneActive(false);
    setFilesFromList(e.dataTransfer?.files);
  });
}

els.closeModalBtn.addEventListener("click", closeModal);
els.cancelBtn.addEventListener("click", closeModal);

els.logoutBtn.addEventListener("click", async () => {
  try {
    // Faz logout no Supabase
    await SupabaseAuth.signOut();
    
    // Limpa variáveis locais
    currentUser = null;
    currentSession = null;
    
    console.log("Logout realizado com sucesso");
    window.location.href = "/login";
  } catch (err) {
    console.error("Erro ao fazer logout:", err);
    setStatus(err?.message || "Falha ao sair.", "error");
  }
});

// Verifica autenticação com Supabase
async function checkAuth() {
  try {
    await SupabaseAuth.init();
    
    const session = await SupabaseAuth.getSession();
    
    if (!session) {
      console.log("Nenhuma sessão ativa, redirecionando para login");
      window.location.href = "/login";
      return;
    }
    
    currentSession = session;
    currentUser = await SupabaseAuth.getUser();
    
    if (!currentUser) {
      console.log("Usuário não encontrado, redirecionando para login");
      window.location.href = "/login";
      return;
    }
    
    console.log("✅ Usuário autenticado:", currentUser.email);
    
    // Monitora mudanças na autenticação
    SupabaseAuth.onAuthStateChange((event, session) => {
      if (event === 'SIGNED_OUT') {
        window.location.href = "/login";
      } else if (event === 'TOKEN_REFRESHED') {
        currentSession = session;
        console.log("Token renovado automaticamente");
      }
    });
    
  } catch (error) {
    console.error("Erro ao verificar autenticação:", error);
    window.location.href = "/login";
  }
}

// Executa verificação de autenticação
checkAuth();

async function pollTaskStatus(taskId) {
  const maxAttempts = 300; // 5 minutos (300 * 1 segundo)
  let attempts = 0;

  while (attempts < maxAttempts) {
    try {
      // Renova a sessão a cada 10 tentativas (a cada 10 segundos) para manter o token válido
      if (attempts % 10 === 0) {
        try {
          const newSession = await SupabaseAuth.getSession();
          if (newSession && newSession.access_token) {
            currentSession = newSession;
            console.log("🔄 Token renovado durante polling (tentativa " + attempts + ")");
          }
        } catch (refreshErr) {
          console.warn("⚠️ Não foi possível renovar token durante polling:", refreshErr);
        }
      }
      
      const headersObj = await authHeaders({});
      const headers = new Headers();
      for (const [key, value] of Object.entries(headersObj)) {
        headers.append(key, value);
      }

      const resp = await fetch(`/api/task/${taskId}`, {
        method: "GET",
        headers: headers,
      });

      if (resp.status === 401) {
        // NÃO redireciona imediatamente - tenta renovar o token
        console.warn("⚠️ Recebido 401, tentando renovar token...");
        try {
          const newSession = await SupabaseAuth.getSession();
          if (newSession && newSession.access_token) {
            currentSession = newSession;
            console.log("✅ Token renovado após 401, continuando polling...");
            // Tenta novamente com o novo token
            attempts++;
            await new Promise((resolve) => setTimeout(resolve, 1000));
            continue;
          }
        } catch (refreshErr) {
          console.error("❌ Falha ao renovar token após 401:", refreshErr);
        }
        
        // Só redireciona se realmente não conseguiu renovar
        setStatus("Sessão expirada. Redirecionando para login...", "error");
        await SupabaseAuth.signOut();
        setTimeout(() => {
          window.location.href = "/login";
        }, 1500);
        return null;
      }

      if (!resp.ok) {
        const data = await resp.json().catch(() => ({}));
        throw new Error(data?.detail || "Falha ao verificar status da tarefa.");
      }

      const task = await resp.json();
      
      // Atualiza status na tela
      if (task.message) {
        setStatus(`${task.message} (${task.progress}%)`);
      }

      if (task.status === "completed") {
        return task.result;
      } else if (task.status === "failed") {
        throw new Error(task.error || "Falha ao processar documentos.");
      }

      // Aguarda 1 segundo antes de verificar novamente
      await new Promise((resolve) => setTimeout(resolve, 1000));
      attempts++;
    } catch (err) {
      console.error("Erro ao verificar status:", err);
      throw err;
    }
  }

  throw new Error("Timeout: o processamento está demorando mais que o esperado. Tente novamente mais tarde.");
}

els.form.addEventListener("submit", async (e) => {
  e.preventDefault();
  setStatus("");

  if (!currentUser) {
    setStatus("Faça login para continuar.", "error");
    window.location.href = "/login";
    return;
  }

  const files = els.files.files ? Array.from(els.files.files) : [];
  if (files.length < 1) {
    setStatus("Selecione pelo menos 1 arquivo (PDF, PNG ou JPG).", "error");
    return;
  }
  
  const allowedExtensions = ['.pdf', '.png', '.jpg', '.jpeg'];
  if (files.some((f) => !allowedExtensions.some(ext => f.name.toLowerCase().endsWith(ext)))) {
    setStatus("Todos os arquivos precisam ser PDF, PNG ou JPG.", "error");
    return;
  }

  els.submitBtn.disabled = true;
  setStatus("Iniciando processamento...");

  try {
    const fd = new FormData();
    for (const f of files) fd.append("files", f, f.name);

    const headersObj = await authHeaders();
    const headers = new Headers();
    for (const [key, value] of Object.entries(headersObj)) {
      headers.append(key, value);
    }

    // Envia os arquivos e recebe o task_id
    const resp = await fetch("/api/extract", {
      method: "POST",
      body: fd,
      headers: headers,
    });
    
    if (resp.status === 401) {
      // Tenta renovar o token antes de desistir
      console.warn("⚠️ Recebido 401 no /api/extract, tentando renovar token...");
      try {
        const newSession = await SupabaseAuth.getSession();
        if (newSession && newSession.access_token) {
          currentSession = newSession;
          console.log("✅ Token renovado, tente novamente");
          setStatus("Sessão renovada. Por favor, tente enviar novamente.", "error");
          els.submitBtn.disabled = false;
          return;
        }
      } catch (refreshErr) {
        console.error("❌ Falha ao renovar token:", refreshErr);
      }
      
      setStatus("Sessão expirada. Redirecionando para login...", "error");
      await SupabaseAuth.signOut();
      setTimeout(() => {
        window.location.href = "/login";
      }, 1500);
      return;
    }
    
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) throw new Error(data?.detail || "Falha na extração.");

    const taskId = data.task_id;
    if (!taskId) throw new Error("Task ID não recebido do servidor.");

    setStatus("Processando... isso pode levar alguns minutos.");

    // Faz polling do status da tarefa
    const result = await pollTaskStatus(taskId);
    
    if (!result) {
      throw new Error("Resultado não recebido.");
    }

    currentToken = result.token;
    structuredDraft = ensureDefaults(deepClone(result.structured || {}));
    renderSummaryFromStructured(structuredDraft);

    setStatus("Resumo pronto. Confirme no modal para gerar o DOCX.", "ok");
    openModal();
  } catch (err) {
    setStatus(err?.message || String(err), "error");
  } finally {
    els.submitBtn.disabled = false;
  }
});

els.confirmBtn.addEventListener("click", async () => {
  if (!currentToken) {
    setStatus("Token ausente. Refaça a extração.", "error");
    closeModal();
    return;
  }
  if (!currentUser) {
    setStatus("Sessão expirada. Faça login novamente.", "error");
    closeModal();
    window.location.href = "/login";
    return;
  }
  els.confirmBtn.disabled = true;
  els.cancelBtn.disabled = true;
  els.closeModalBtn.disabled = true;
  setStatus("Gerando DOCX...");

  try {
    const headersObj = await authHeaders({ "Content-Type": "application/json" });
    const headers = new Headers();
    for (const [key, value] of Object.entries(headersObj)) {
      headers.append(key, value);
    }

    const resp = await fetch("/api/generate-docx", {
      method: "POST",
      headers: headers,
      body: JSON.stringify({ token: currentToken, structured: structuredDraft }),
    });
    
    // Verifica se é erro de autenticação
    if (resp.status === 401) {
      // Tenta renovar o token antes de desistir
      console.warn("⚠️ Recebido 401 no /api/generate-docx, tentando renovar token...");
      try {
        const newSession = await SupabaseAuth.getSession();
        if (newSession && newSession.access_token) {
          currentSession = newSession;
          console.log("✅ Token renovado, tente gerar o DOCX novamente");
          setStatus("Sessão renovada. Por favor, clique em Confirmar novamente.", "error");
          els.confirmBtn.disabled = false;
          els.cancelBtn.disabled = false;
          els.closeModalBtn.disabled = false;
          return;
        }
      } catch (refreshErr) {
        console.error("❌ Falha ao renovar token:", refreshErr);
      }
      
      setStatus("Sessão expirada. Redirecionando para login...", "error");
      closeModal();
      await SupabaseAuth.signOut();
      setTimeout(() => {
        window.location.href = "/login";
      }, 1500);
      return;
    }
    
    if (!resp.ok) {
      const data = await resp.json().catch(() => ({}));
      throw new Error(data?.detail || "Falha ao gerar DOCX.");
    }
    const blob = await resp.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "template_gerado.docx";
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);

    setStatus("DOCX gerado e baixado.", "ok");
    closeModal();
    currentToken = null;
    structuredDraft = null;
  } catch (err) {
    setStatus(err?.message || String(err), "error");
  } finally {
    els.confirmBtn.disabled = false;
    els.cancelBtn.disabled = false;
    els.closeModalBtn.disabled = false;
  }
});

updateFileHelp();

