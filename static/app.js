import { initializeApp } from "https://www.gstatic.com/firebasejs/10.12.5/firebase-app.js";
import { getAuth, onAuthStateChanged, signOut } from "https://www.gstatic.com/firebasejs/10.12.5/firebase-auth.js";

// Firebase JS SDK v7.20.0+ (measurementId opcional)
const firebaseConfig = {
  apiKey: "AIzaSyC5H6J8XkBAyiuv1wHCQMNVuxX1JnBU568",
  authDomain: "horlandobraga-168fc.firebaseapp.com",
  projectId: "horlandobraga-168fc",
  storageBucket: "horlandobraga-168fc.firebasestorage.app",
  messagingSenderId: "405988871259",
  appId: "1:405988871259:web:ff0ef83ba7e118d19b837e",
  measurementId: "G-H024RSDR79",
};

const firebaseApp = initializeApp(firebaseConfig);
const auth = getAuth(firebaseApp);

const els = {
  form: document.getElementById("uploadForm"),
  files: document.getElementById("files"),
  fileHelp: document.getElementById("fileHelp"),
  submitBtn: document.getElementById("submitBtn"),
  clearBtn: document.getElementById("clearBtn"),
  status: document.getElementById("status"),

  logoutBtn: document.getElementById("logoutBtn"),

  modalBackdrop: document.getElementById("modalBackdrop"),
  closeModalBtn: document.getElementById("closeModalBtn"),
  cancelBtn: document.getElementById("cancelBtn"),
  confirmBtn: document.getElementById("confirmBtn"),

  perDocInfo: document.getElementById("perDocInfo"),
  summary: document.getElementById("summary"),
  structuredJson: document.getElementById("structuredJson"),
};

let currentUser = null;
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
  const normalized = trimmed === "" ? null : trimmed.toLowerCase();
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

async function authHeaders(extraHeaders = {}) {
  if (!currentUser) throw new Error("Você precisa estar logado.");
  const idToken = await currentUser.getIdToken();
  return { ...extraHeaders, Authorization: `Bearer ${idToken}` };
}

function renderPerDocInfo(perDocument = []) {
  els.perDocInfo.innerHTML = "";
  for (const d of perDocument) {
    const pages = Array.isArray(d.pages_analyzed) ? d.pages_analyzed.length : 0;
    const pill = document.createElement("div");
    pill.className = "pill";
    pill.textContent = `${d.source || "documento"} • páginas analisadas: ${pages}`;
    els.perDocInfo.appendChild(pill);
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
      last.includes("observacao")
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
      v.value = valueForInput(currentVal).toLowerCase();
      if (isNacionalidade) {
        v.readOnly = true;
        v.title = 'Valor fixo: "brasileiro(a)"';
      }

      v.addEventListener("input", () => {
        setDeep(structured, path, v.value);
        els.structuredJson.textContent = JSON.stringify(structuredDraft || structured, null, 2);
      });
      kv.appendChild(k);
      kv.appendChild(v);
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
  const lines = files.map((f, i) => `${i + 1}. ${f.name} (${Math.round(f.size / 1024)} KB)`);
  els.fileHelp.textContent = `${files.length} arquivo(s):\n` + lines.join(" | ");
}

els.files.addEventListener("change", updateFileHelp);

els.clearBtn.addEventListener("click", () => {
  els.files.value = "";
  updateFileHelp();
  setStatus("");
});

els.closeModalBtn.addEventListener("click", closeModal);
els.cancelBtn.addEventListener("click", closeModal);

els.logoutBtn.addEventListener("click", async () => {
  try {
    await signOut(auth);
    window.location.href = "/login";
  } catch (err) {
    setStatus(err?.message || "Falha ao sair.", "error");
  }
});

onAuthStateChanged(auth, (user) => {
  currentUser = user || null;
  
  // If not logged in, redirect to login page
  if (!currentUser) {
    window.location.href = "/login";
  }
});

els.form.addEventListener("submit", async (e) => {
  e.preventDefault();
  setStatus("");

  if (!currentUser) {
    setStatus("Faça login para continuar.", "error");
    window.location.href = "/login";
    return;
  }

  const files = els.files.files ? Array.from(els.files.files) : [];
  if (files.length !== 4) {
    setStatus("Selecione exatamente 4 PDFs.", "error");
    return;
  }
  if (files.some((f) => !f.name.toLowerCase().endsWith(".pdf"))) {
    setStatus("Todos os arquivos precisam ser PDF.", "error");
    return;
  }

  els.submitBtn.disabled = true;
  els.clearBtn.disabled = true;
  setStatus("Extraindo e analisando... isso pode levar alguns minutos, dependendo do tamanho dos PDFs.");

  try {
    const fd = new FormData();
    for (const f of files) fd.append("files", f, f.name);

    const resp = await fetch("/api/extract", {
      method: "POST",
      body: fd,
      headers: await authHeaders(),
    });
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) throw new Error(data?.detail || "Falha na extração.");

    currentToken = data.token;
    structuredDraft = ensureDefaults(deepClone(data.structured || {}));
    renderPerDocInfo(data.per_document || []);
    renderSummaryFromStructured(structuredDraft);
    els.structuredJson.textContent = JSON.stringify(structuredDraft || {}, null, 2);

    setStatus("Resumo pronto. Confirme no modal para gerar o DOCX.", "ok");
    openModal();
  } catch (err) {
    setStatus(err?.message || String(err), "error");
  } finally {
    els.submitBtn.disabled = false;
    els.clearBtn.disabled = false;
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
    const resp = await fetch("/api/generate-docx", {
      method: "POST",
      headers: await authHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({ token: currentToken, structured: structuredDraft }),
    });
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

