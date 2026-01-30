const els = {
  form: document.getElementById("uploadForm"),
  files: document.getElementById("files"),
  fileHelp: document.getElementById("fileHelp"),
  submitBtn: document.getElementById("submitBtn"),
  clearBtn: document.getElementById("clearBtn"),
  status: document.getElementById("status"),

  modalBackdrop: document.getElementById("modalBackdrop"),
  closeModalBtn: document.getElementById("closeModalBtn"),
  cancelBtn: document.getElementById("cancelBtn"),
  confirmBtn: document.getElementById("confirmBtn"),

  perDocInfo: document.getElementById("perDocInfo"),
  summary: document.getElementById("summary"),
  structuredJson: document.getElementById("structuredJson"),
};

let currentToken = null;

function setStatus(text, kind = "") {
  els.status.textContent = text || "";
  els.status.className = "status" + (kind ? ` ${kind}` : "");
}

function fmt(v) {
  if (v === null || v === undefined || v === "") return "—";
  return String(v);
}

function openModal() {
  els.modalBackdrop.classList.remove("hidden");
  els.modalBackdrop.setAttribute("aria-hidden", "false");
}

function closeModal() {
  els.modalBackdrop.classList.add("hidden");
  els.modalBackdrop.setAttribute("aria-hidden", "true");
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

function renderSummary(summary) {
  els.summary.innerHTML = "";
  const blocks = [
    ["Qualificação", summary?.qualificacao, [
      ["nome", "Nome"],
      ["cpf", "CPF"],
      ["representante_legal", "Representante legal"],
      ["endereco", "Endereço"],
    ]],
    ["INSS", summary?.inss, [
      ["nb", "NB"],
      ["der", "DER"],
    ]],
    ["Laudo principal", summary?.laudo_principal, [
      ["deficiencia", "Deficiência"],
      ["cid", "CID"],
      ["data", "Data"],
      ["medico", "Médico"],
    ]],
    ["Relatório escolar", summary?.relatorio_escolar, [
      ["data_emissao", "Data emissão"],
      ["primeiro_nome_autor", "Primeiro nome autor"],
    ]],
  ];

  for (const [title, obj, fields] of blocks) {
    const block = document.createElement("div");
    block.className = "block";

    const h = document.createElement("div");
    h.className = "block-title";
    h.textContent = title;
    block.appendChild(h);

    const kv = document.createElement("div");
    kv.className = "kv";
    for (const [key, label] of fields) {
      const k = document.createElement("div");
      k.className = "k";
      k.textContent = label;
      const v = document.createElement("div");
      v.className = "v";
      v.textContent = fmt(obj?.[key]);
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

els.form.addEventListener("submit", async (e) => {
  e.preventDefault();
  setStatus("");

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

    const resp = await fetch("/api/extract", { method: "POST", body: fd });
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) throw new Error(data?.detail || "Falha na extração.");

    currentToken = data.token;
    renderPerDocInfo(data.per_document || []);
    renderSummary(data.summary || {});
    els.structuredJson.textContent = JSON.stringify(data.structured || {}, null, 2);

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
  els.confirmBtn.disabled = true;
  els.cancelBtn.disabled = true;
  els.closeModalBtn.disabled = true;
  setStatus("Gerando DOCX...");

  try {
    const resp = await fetch("/api/generate-docx", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token: currentToken }),
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
  } catch (err) {
    setStatus(err?.message || String(err), "error");
  } finally {
    els.confirmBtn.disabled = false;
    els.cancelBtn.disabled = false;
    els.closeModalBtn.disabled = false;
  }
});

updateFileHelp();

