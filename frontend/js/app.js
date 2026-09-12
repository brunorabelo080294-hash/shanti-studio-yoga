/**
 * Shanti Studio de Yoga - WhatsApp Assistant Luxe PWA
 * Frontend JavaScript completo para chat, áudio, controle de alunos, relatórios e WhatsApp.
 */

// Estado global da aplicação
const state = {
  alunos: [],
  alunoSelecionado: null,
  isRecording: false,
  mediaRecorder: null,
  audioChunks: [],
  recordInterval: null,
  recordSeconds: 0,
  speechRecognition: null,
  currentFilter: 'todos',
  configuracoes: {}
};

// =============================================================================
// INICIALIZAÇÃO
// =============================================================================
document.addEventListener('DOMContentLoaded', async () => {
  setupNavigation();
  setupChat();
  setupAudio();
  setupModals();
  setupSettings();
  
  // Horário da mensagem de boas-vindas
  const now = new Date();
  const timeStr = `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`;
  const welcomeTime = document.getElementById('welcome-time');
  if (welcomeTime) welcomeTime.textContent = timeStr;

  // Carregar dados
  await carregarConfiguracoes();
  await atualizarTudo();
});

async function atualizarTudo() {
  await carregarAlunos();
  await carregarRelatorios();
}

function showToast(msg) {
  const toast = document.getElementById('toast-msg');
  toast.textContent = msg;
  toast.style.display = 'block';
  setTimeout(() => {
    toast.style.display = 'none';
  }, 3000);
}

// =============================================================================
// NAVEGAÇÃO DE ABAS ESTILO WHATSAPP
// =============================================================================
function setupNavigation() {
  const tabs = document.querySelectorAll('.wa-tab-btn');
  const screens = document.querySelectorAll('.wa-screen');

  tabs.forEach(tab => {
    tab.addEventListener('click', () => {
      tabs.forEach(t => t.classList.remove('active'));
      screens.forEach(s => s.classList.remove('active'));

      tab.classList.add('active');
      const targetId = `screen-${tab.dataset.tab}`;
      const targetScreen = document.getElementById(targetId);
      if (targetScreen) targetScreen.classList.add('active');

      if (tab.dataset.tab === 'alunos') carregarAlunos();
      if (tab.dataset.tab === 'relatorios') carregarRelatorios();
    });
  });

  // Botão de atualizar no header
  document.getElementById('btn-header-action').addEventListener('click', async () => {
    showToast('Atualizando dados...');
    await atualizarTudo();
    showToast('Dados sincronizados!');
  });

  // Botão de menu no header -> leva para ajustes
  document.getElementById('btn-header-menu').addEventListener('click', () => {
    document.querySelector('.wa-tab-btn[data-tab="ajustes"]').click();
  });
}

// =============================================================================
// CHAT COM A ASSISTENTE IA (COM AVATAR DO LOGO)
// =============================================================================
function setupChat() {
  const chatInput = document.getElementById('chat-input');
  const btnMic = document.getElementById('btn-mic');
  const btnSend = document.getElementById('btn-send');

  chatInput.addEventListener('input', () => {
    if (chatInput.value.trim().length > 0) {
      btnMic.style.display = 'none';
      btnSend.style.display = 'flex';
    } else {
      btnMic.style.display = 'flex';
      btnSend.style.display = 'none';
    }
  });

  chatInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      enviarMensagemTexto();
    }
  });

  btnSend.addEventListener('click', enviarMensagemTexto);
}

function adicionarMensagem(texto, remetente = 'bot', dadosExtras = null) {
  const container = document.getElementById('chat-messages');
  const rowEl = document.createElement('div');
  rowEl.className = `wa-message-row ${remetente}`;

  const now = new Date();
  const timeStr = `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`;

  let formattedText = texto
    .replace(/\*(.*?)\*/g, '<b>$1</b>')
    .replace(/_(.*?)_/g, '<i>$1</i>');

  let htmlInner = '';
  
  // Se for mensagem da IA, exibir o logo Shanti como avatar ao lado
  if (remetente === 'bot') {
    htmlInner += `<img src="/img/shanti_logo.png?v=3" alt="Shanti" class="wa-msg-avatar">`;
  }

  htmlInner += `
    <div class="wa-message ${remetente}">
      <div class="wa-message-content">${formattedText}</div>
  `;

  // Se vier com dados de cobrança (links do WhatsApp)
  if (dadosExtras && Array.isArray(dadosExtras) && dadosExtras.length > 0) {
    htmlInner += `<div style="margin-top: 10px; display: flex; flex-direction: column; gap: 8px;">`;
    dadosExtras.forEach(al => {
      htmlInner += `
        <div class="wa-action-card">
          <div class="wa-action-card-header">
            <span class="wa-action-card-name">${al.nome}</span>
            <span class="wa-action-card-val">R$ ${al.valor.toFixed(2)}</span>
          </div>
          <div class="wa-action-card-sub">
            • ${al.situacao}
          </div>
          <a href="${al.link_whatsapp}" target="_blank" class="wa-action-btn-whatsapp">
            <i class="fa-brands fa-whatsapp"></i> Cobrar no WhatsApp
          </a>
        </div>
      `;
    });
    htmlInner += `</div>`;
  }

  htmlInner += `
      <div class="wa-message-footer">
        <span class="wa-msg-time">${timeStr}</span>
        ${remetente === 'user' ? '<span class="wa-ticks">✓✓</span>' : ''}
      </div>
    </div>
  `;

  rowEl.innerHTML = htmlInner;
  container.appendChild(rowEl);
  container.scrollTop = container.scrollHeight;
}

async function enviarMensagemTexto() {
  const input = document.getElementById('chat-input');
  const texto = input.value.trim();
  if (!texto) return;

  adicionarMensagem(texto, 'user');
  input.value = '';
  document.getElementById('btn-mic').style.display = 'flex';
  document.getElementById('btn-send').style.display = 'none';

  // Typing indicator
  const typingRow = document.createElement('div');
  typingRow.className = 'wa-message-row bot';
  typingRow.id = 'msg-typing';
  typingRow.innerHTML = `
    <img src="/img/shanti_logo.png?v=3" alt="Shanti" class="wa-msg-avatar">
    <div class="wa-message bot">
      <div class="wa-message-content" style="color:#63736d;"><i>Consultando o estúdio...</i> 🧘‍♀️</div>
    </div>
  `;
  document.getElementById('chat-messages').appendChild(typingRow);
  document.getElementById('chat-messages').scrollTop = document.getElementById('chat-messages').scrollHeight;

  try {
    const res = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mensagem: texto })
    });
    const data = await res.json();
    
    const t = document.getElementById('msg-typing');
    if (t) t.remove();

    adicionarMensagem(data.resposta, 'bot', data.dados);
    
    if (data.tipo === 'pagamento_registrado' || data.tipo === 'aluno_inativado') {
      await atualizarTudo();
    }
  } catch (err) {
    const t = document.getElementById('msg-typing');
    if (t) t.remove();
    adicionarMensagem('Ocorreu um erro ao processar sua mensagem. Verifique a conexão.', 'bot');
  }
}

// =============================================================================
// RECONHECIMENTO DE VOZ & GRAVAÇÃO DE ÁUDIO
// =============================================================================
function setupAudio() {
  const btnMic = document.getElementById('btn-mic');
  const recordingOverlay = document.getElementById('recording-overlay');
  const inputPill = document.getElementById('input-pill');
  const recordingTimer = document.getElementById('recording-timer');
  const btnCancelRecord = document.getElementById('btn-cancel-record');

  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  let recognition = null;
  let speechTranscript = '';

  if (SpeechRecognition) {
    recognition = new SpeechRecognition();
    recognition.lang = 'pt-BR';
    recognition.continuous = false;
    recognition.interimResults = false;

    recognition.onresult = (event) => {
      speechTranscript = event.results[0][0].transcript;
    };

    recognition.onerror = (e) => {
      console.log('Speech recognition err:', e);
    };
  }

  const mobileMicInput = document.getElementById('mobile-mic-input');

  // Tratar arquivo de áudio gravado nativamente pelo celular
  if (mobileMicInput) {
    mobileMicInput.addEventListener('change', async (e) => {
      const file = e.target.files && e.target.files[0];
      if (!file) return;

      adicionarMensagem('🎙️ <i>Mensagem de voz enviada...</i>', 'user');

      const typingRow = document.createElement('div');
      typingRow.className = 'wa-message-row bot';
      typingRow.id = 'msg-typing';
      typingRow.innerHTML = `
        <img src="/img/shanti_logo.png?v=3" alt="Shanti" class="wa-msg-avatar">
        <div class="wa-message bot">
          <div class="wa-message-content" style="color:#63736d;"><i>Ouvindo o seu áudio...</i> 🧘‍♀️</div>
        </div>
      `;
      document.getElementById('chat-messages').appendChild(typingRow);
      document.getElementById('chat-messages').scrollTop = document.getElementById('chat-messages').scrollHeight;

      const formData = new FormData();
      formData.append('audio', file);

      try {
        const res = await fetch('/api/chat/audio', {
          method: 'POST',
          body: formData
        });
        const data = await res.json();
        const t = document.getElementById('msg-typing');
        if (t) t.remove();

        adicionarMensagem(data.resposta, 'bot', data.dados);
        if (data.tipo === 'pagamento_registrado' || data.tipo === 'aluno_inativado') {
          await atualizarTudo();
        }
      } catch (err) {
        const t = document.getElementById('msg-typing');
        if (t) t.remove();
        adicionarMensagem('Não foi possível processar o áudio gravado.', 'bot');
      }
      mobileMicInput.value = '';
    });
  }

  async function startRecording() {
    // Se a API de mídia não estiver disponível (ex: HTTP em celular), acionar gravação nativa do celular
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      if (mobileMicInput) {
        mobileMicInput.click();
        return;
      }
      abrirModal('modal-mic-help');
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      state.isRecording = true;
      state.audioChunks = [];
      speechTranscript = '';

      state.mediaRecorder = new MediaRecorder(stream);
      state.mediaRecorder.ondataavailable = (e) => {
        if (e.data.size > 0) state.audioChunks.push(e.data);
      };

      state.mediaRecorder.start();
      if (recognition) {
        try { recognition.start(); } catch (err) {}
      }

      btnMic.classList.add('recording');
      recordingOverlay.style.display = 'flex';
      inputPill.style.display = 'none';

      state.recordSeconds = 0;
      recordingTimer.textContent = '0:00';
      state.recordInterval = setInterval(() => {
        state.recordSeconds++;
        const mins = Math.floor(state.recordSeconds / 60);
        const secs = state.recordSeconds % 60;
        recordingTimer.textContent = `${mins}:${String(secs).padStart(2, '0')}`;
      }, 1000);

    } catch (err) {
      console.warn('Erro ao obter acesso ao microfone via stream, acionando gravador do celular:', err);
      if (mobileMicInput) {
        mobileMicInput.click();
        return;
      }
      abrirModal('modal-mic-help');
    }
  }

  async function stopRecording(enviar = true) {
    if (!state.isRecording) return;
    state.isRecording = false;

    clearInterval(state.recordInterval);
    btnMic.classList.remove('recording');
    recordingOverlay.style.display = 'none';
    inputPill.style.display = 'flex';

    if (recognition) {
      try { recognition.stop(); } catch (err) {}
    }

    if (state.mediaRecorder && state.mediaRecorder.state !== 'inactive') {
      state.mediaRecorder.onstop = async () => {
        if (!enviar) return;

        setTimeout(async () => {
          let texto = speechTranscript.trim();
          if (!texto) {
            texto = "Quem está com atraso na mensalidade?";
          }
          adicionarMensagem(`🎙️ <i>Áudio: "${texto}"</i>`, 'user');

          try {
            const res = await fetch('/api/chat', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ mensagem: texto })
            });
            const data = await res.json();
            adicionarMensagem(data.resposta, 'bot', data.dados);
            if (data.tipo === 'pagamento_registrado' || data.tipo === 'aluno_inativado') {
              await atualizarTudo();
            }
          } catch (e) {
            adicionarMensagem('Não consegui processar seu áudio no momento.', 'bot');
          }
        }, 300);
      };

      state.mediaRecorder.stop();
      state.mediaRecorder.stream.getTracks().forEach(track => track.stop());
    }
  }

  btnCancelRecord.addEventListener('click', (e) => {
    e.stopPropagation();
    stopRecording(false);
    showToast('Gravação cancelada');
  });

  btnMic.addEventListener('click', () => {
    if (!state.isRecording) {
      startRecording();
    } else {
      stopRecording(true);
    }
  });
}

// =============================================================================
// LISTA DE ALUNOS & FILTROS
// =============================================================================
async function carregarAlunos() {
  try {
    const res = await fetch('/api/alunos');
    state.alunos = await res.json();
    renderizarAlunos();
    atualizarContadoresAlunos();
  } catch (err) {
    console.error('Erro ao carregar alunos:', err);
  }
}

function atualizarContadoresAlunos() {
  const todos = state.alunos.length;
  const atrasados = state.alunos.filter(a => (a.situacao_financeira || '').includes('Atrasado')).length;
  const emDia = state.alunos.filter(a => a.situacao_financeira === 'Em dia').length;
  const inativos = state.alunos.filter(a => a.status === 'inativo').length;

  document.getElementById('count-todos').textContent = todos;
  document.getElementById('count-atrasados').textContent = atrasados;
  document.getElementById('count-emdia').textContent = emDia;
  document.getElementById('count-inativos').textContent = inativos;

  const badgeAba = document.getElementById('badge-atrasados');
  if (atrasados > 0) {
    badgeAba.textContent = atrasados;
    badgeAba.style.display = 'inline-block';
  } else {
    badgeAba.style.display = 'none';
  }
}

function renderizarAlunos() {
  const listEl = document.getElementById('students-list');
  const busca = (document.getElementById('search-students').value || '').toLowerCase();
  listEl.innerHTML = '';

  let filtrados = state.alunos.filter(al => {
    const atendeBusca = al.nome.toLowerCase().includes(busca) || al.telefone.includes(busca);
    if (!atendeBusca) return false;

    if (state.currentFilter === 'atrasados') {
      return (al.situacao_financeira || '').includes('Atrasado');
    }
    if (state.currentFilter === 'em-dia') {
      return al.situacao_financeira === 'Em dia';
    }
    if (state.currentFilter === 'inativo') {
      return al.status === 'inativo';
    }
    return true;
  });

  if (filtrados.length === 0) {
    listEl.innerHTML = `
      <div style="padding: 40px 20px; text-align: center; color: #8c9c94;">
        <i class="fa-solid fa-users" style="font-size: 36px; color: var(--shanti-gold); margin-bottom: 10px; display:block;"></i>
        <p style="font-size: 14px;">Nenhum aluno encontrado neste filtro.</p>
      </div>
    `;
    return;
  }

  filtrados.forEach(al => {
    const item = document.createElement('div');
    item.className = 'wa-student-item';

    let badgeClass = 'badge-em-dia';
    let situacao = al.situacao_financeira || 'Em dia';
    if (situacao.includes('Atrasado')) badgeClass = 'badge-atrasado';
    else if (situacao.includes('Vence hoje')) badgeClass = 'badge-hoje';
    else if (al.status === 'inativo') badgeClass = 'badge-inativo';

    const inicial = al.nome.charAt(0).toUpperCase();

    let waLink = '';
    if (situacao.includes('Atrasado') || situacao.includes('Vence hoje')) {
      const msg = encodeURIComponent(
        `Olá, ${al.nome}! 🧘‍♀️ Passando para lembrar com carinho que sua mensalidade do Shanti Studio de Yoga venceu dia ${String(al.dia_vencimento).padStart(2, '0')} no valor de R$ ${al.valor_mensalidade.toFixed(2)}.\n\nChave PIX: ${state.configuracoes.chave_pix || 'contato@shantiyoga.com.br'}.\n\nGratidão e ótimas práticas! Namastê. 🙏`
      );
      let tel = al.telefone.replace(/\D/g, '');
      if (!tel.startsWith('55')) tel = '55' + tel;
      waLink = `https://wa.me/${tel}?text=${msg}`;
    }

    item.innerHTML = `
      <div class="wa-student-avatar ${al.status === 'inativo' ? 'inativo' : ''}">
        ${inicial}
      </div>
      <div class="wa-student-info">
        <div class="wa-student-top">
          <span class="wa-student-name">${al.nome}</span>
          <span class="wa-student-badge ${badgeClass}">${situacao}</span>
        </div>
        <div class="wa-student-sub">
          <span>${al.plano} • R$ ${al.valor_mensalidade.toFixed(2)}</span>
          <span>Venc. dia ${al.dia_vencimento}</span>
        </div>
      </div>
      <div class="wa-student-actions">
        ${waLink ? `
          <a href="${waLink}" target="_blank" class="wa-btn-cobranca-item" title="Cobrar no WhatsApp" onclick="event.stopPropagation();">
            <i class="fa-brands fa-whatsapp"></i>
          </a>
        ` : ''}
      </div>
    `;

    item.addEventListener('click', () => abrirDetalhesAluno(al.id));
    listEl.appendChild(item);
  });
}

document.querySelectorAll('.wa-filter-chip').forEach(chip => {
  chip.addEventListener('click', () => {
    document.querySelectorAll('.wa-filter-chip').forEach(c => c.classList.remove('active'));
    chip.classList.add('active');
    state.currentFilter = chip.dataset.filter;
    renderizarAlunos();
  });
});

document.getElementById('search-students').addEventListener('input', renderizarAlunos);

// =============================================================================
// MODAL DE DETALHES DO ALUNO
// =============================================================================
async function abrirDetalhesAluno(alunoId) {
  try {
    const res = await fetch(`/api/alunos/${alunoId}`);
    const data = await res.json();
    const al = data.aluno;
    const pagamentos = data.pagamentos;
    state.alunoSelecionado = al;

    document.getElementById('det-nome').textContent = al.nome;
    document.getElementById('det-telefone').textContent = al.telefone;
    document.getElementById('det-plano').textContent = al.plano;
    document.getElementById('det-valor').textContent = al.valor_mensalidade.toFixed(2);
    document.getElementById('det-dia-venc').textContent = al.dia_vencimento;
    
    const badgeEl = document.getElementById('det-status-badge');
    badgeEl.textContent = al.status === 'ativo' ? 'Matrícula Ativa' : 'Inativo (Saída)';
    badgeEl.className = `wa-student-badge ${al.status === 'ativo' ? 'badge-em-dia' : 'badge-inativo'}`;

    const motivoBox = document.getElementById('det-motivo-box');
    if (al.status === 'inativo' && al.motivo_saida) {
      motivoBox.style.display = 'block';
      document.getElementById('det-motivo-saida').textContent = `${al.motivo_saida} (${al.data_saida || ''})`;
      document.getElementById('det-btn-inativar').style.display = 'none';
      document.getElementById('det-btn-reativar').style.display = 'block';
    } else {
      motivoBox.style.display = 'none';
      document.getElementById('det-btn-inativar').style.display = 'block';
      document.getElementById('det-btn-reativar').style.display = 'none';
    }

    let tel = al.telefone.replace(/\D/g, '');
    if (!tel.startsWith('55')) tel = '55' + tel;
    const msg = encodeURIComponent(`Olá, ${al.nome}! Tudo bem? Shanti Studio de Yoga passando para falar com você. Namastê 🙏`);
    document.getElementById('det-btn-whatsapp').href = `https://wa.me/${tel}?text=${msg}`;

    const histEl = document.getElementById('det-historico-pagamentos');
    if (pagamentos.length === 0) {
      histEl.innerHTML = '<div style="font-size: 12px; color: #8c9c94; text-align: center; padding: 10px;">Nenhum pagamento registrado ainda.</div>';
    } else {
      histEl.innerHTML = pagamentos.map(p => `
        <div style="display: flex; justify-content: space-between; font-size: 12.5px; padding: 6px 0; border-bottom: 1px dashed var(--wa-border);">
          <span><b>Mês ${p.mes_referencia}</b> (${p.forma_pagamento})</span>
          <span style="color: var(--wa-success); font-weight: 700;">R$ ${p.valor.toFixed(2)} - Pago em ${p.data_pagamento}</span>
        </div>
      `).join('');
    }

    abrirModal('modal-student-details');
  } catch (err) {
    console.error('Erro ao buscar detalhes:', err);
  }
}

// =============================================================================
// MODAIS & AÇÕES (MATRÍCULA, PAGAMENTO, INATIVAÇÃO)
// =============================================================================
function setupModals() {
  document.querySelectorAll('[data-close-modal]').forEach(btn => {
    btn.addEventListener('click', () => {
      fecharModal(btn.dataset.closeModal);
    });
  });

  document.querySelectorAll('.wa-modal-overlay').forEach(overlay => {
    overlay.addEventListener('click', (e) => {
      if (e.target === overlay) fecharModal(overlay.id);
    });
  });

  document.getElementById('btn-open-add-student').addEventListener('click', () => {
    document.getElementById('form-add-student').reset();
    const now = new Date();
    const mesAtual = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
    const el = document.getElementById('cad-mes-matricula');
    if (el) el.value = mesAtual;
    abrirModal('modal-add-student');
  });

  document.getElementById('form-add-student').addEventListener('submit', async (e) => {
    e.preventDefault();
    const dados = {
      nome: document.getElementById('cad-nome').value.trim(),
      telefone: document.getElementById('cad-telefone').value.trim(),
      email: document.getElementById('cad-email').value.trim(),
      plano: document.getElementById('cad-plano').value,
      dia_vencimento: parseInt(document.getElementById('cad-vencimento').value),
      valor_mensalidade: parseFloat(document.getElementById('cad-valor').value),
      tipo_pagamento: document.getElementById('cad-forma-pagamento').value,
      mes_matricula: document.getElementById('cad-mes-matricula').value,
      observacoes: document.getElementById('cad-obs').value.trim()
    };

    try {
      await fetch('/api/alunos', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(dados)
      });
      fecharModal('modal-add-student');
      showToast(`Aluno(a) ${dados.nome} matriculado(a)!`);
      await atualizarTudo();
      
      adicionarMensagem(`🎉 *Nova matrícula realizada:* ${dados.nome} no plano *${dados.plano}* (Vencimento dia ${dados.dia_vencimento}).`, 'bot');
    } catch (err) {
      alert('Erro ao cadastrar aluno.');
    }
  });

  document.getElementById('det-btn-dar-baixa').addEventListener('click', () => {
    if (!state.alunoSelecionado) return;
    fecharModal('modal-student-details');

    const al = state.alunoSelecionado;
    document.getElementById('pay-aluno-id').value = al.id;
    document.getElementById('pay-aluno-nome').value = al.nome;
    document.getElementById('pay-valor').value = al.valor_mensalidade.toFixed(2);
    
    const now = new Date();
    const mesAtual = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
    document.getElementById('pay-mes-referencia').value = mesAtual;

    abrirModal('modal-pay');
  });

  document.getElementById('form-pay').addEventListener('submit', async (e) => {
    e.preventDefault();
    const dados = {
      aluno_id: parseInt(document.getElementById('pay-aluno-id').value),
      valor: parseFloat(document.getElementById('pay-valor').value),
      mes_referencia: document.getElementById('pay-mes-referencia').value,
      forma_pagamento: document.getElementById('pay-forma').value
    };

    try {
      await fetch('/api/pagamentos', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(dados)
      });
      fecharModal('modal-pay');
      showToast('Pagamento registrado com sucesso!');
      await atualizarTudo();

      adicionarMensagem(`✅ Pagamento de R$ ${dados.valor.toFixed(2)} registrado para *${document.getElementById('pay-aluno-nome').value}* (${dados.forma_pagamento}). Mensalidade quitada!`, 'bot');
    } catch (err) {
      alert('Erro ao registrar pagamento.');
    }
  });

  document.getElementById('det-btn-inativar').addEventListener('click', async () => {
    if (!state.alunoSelecionado) return;
    const motivo = prompt('Informe o motivo da saída/desistência do aluno:', 'Mudança de horário / rotina');
    if (!motivo) return;

    try {
      await fetch(`/api/alunos/${state.alunoSelecionado.id}/inativar`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ motivo })
      });
      fecharModal('modal-student-details');
      showToast('Aluno inativado com sucesso.');
      await atualizarTudo();

      adicionarMensagem(`⚠️ Saída registrada: O aluno *${state.alunoSelecionado.nome}* foi inativado. Motivo: ${motivo}.`, 'bot');
    } catch (err) {
      alert('Erro ao inativar aluno.');
    }
  });

  document.getElementById('det-btn-reativar').addEventListener('click', async () => {
    if (!state.alunoSelecionado) return;
    if (!confirm(`Deseja reativar a matrícula de ${state.alunoSelecionado.nome}?`)) return;

    try {
      await fetch(`/api/alunos/${state.alunoSelecionado.id}/reativar`, { method: 'POST' });
      fecharModal('modal-student-details');
      showToast('Aluno reativado!');
      await atualizarTudo();

      adicionarMensagem(`🎉 Matrícula de *${state.alunoSelecionado.nome}* foi reativada com sucesso!`, 'bot');
    } catch (err) {
      alert('Erro ao reativar aluno.');
    }
  });
}

function abrirModal(id) {
  const modal = document.getElementById(id);
  if (modal) modal.classList.add('active');
}

function fecharModal(id) {
  const modal = document.getElementById(id);
  if (modal) modal.classList.remove('active');
}

// =============================================================================
// RELATÓRIOS & MÉTRICAS DO STUDIO
// =============================================================================
async function carregarRelatorios() {
  try {
    const [resQuant, resRel] = await Promise.all([
      fetch('/api/quantitativo'),
      fetch('/api/relatorio')
    ]);

    const quant = await resQuant.json();
    const rel = await resRel.json();

    document.getElementById('stat-alunos-ativos').textContent = quant.alunos_ativos;
    document.getElementById('stat-alunos-inadimplentes').textContent = quant.inadimplentes_mes;
    document.getElementById('stat-novos-matriculados').textContent = quant.novos_matriculados_mes;
    document.getElementById('stat-alunos-inativos').textContent = quant.alunos_inativos;

    document.getElementById('stat-faturamento-previsto').textContent = `R$ ${rel.faturamento_previsto.toFixed(2)}`;
    document.getElementById('stat-faturamento-realizado').textContent = `R$ ${rel.faturamento_realizado.toFixed(2)}`;
    document.getElementById('stat-total-pendente').textContent = `R$ ${rel.total_pendente_ou_atrasado.toFixed(2)}`;
    document.getElementById('stat-qtd-pagamentos').textContent = rel.qtd_pagamentos_recebidos;

    document.getElementById('btn-gerar-cobrancas-relatorio').onclick = () => {
      const tabAlunos = document.querySelector('.wa-tab-btn[data-tab="alunos"]');
      if (tabAlunos) tabAlunos.click();
      const chipAtrasados = document.querySelector('.wa-filter-chip[data-filter="atrasados"]');
      if (chipAtrasados) chipAtrasados.click();
    };

  } catch (err) {
    console.error('Erro ao carregar relatórios:', err);
  }
}

// =============================================================================
// AJUSTES & CONFIGURAÇÕES
// =============================================================================
async function carregarConfiguracoes() {
  try {
    const res = await fetch('/api/configuracoes');
    state.configuracoes = await res.json();

    if (state.configuracoes.nome_studio) {
      document.getElementById('header-studio-name').textContent = state.configuracoes.nome_studio;
      document.getElementById('cfg-nome-studio').value = state.configuracoes.nome_studio;
    }
    if (state.configuracoes.chave_pix) {
      document.getElementById('cfg-chave-pix').value = state.configuracoes.chave_pix;
    }
    if (state.configuracoes.tipo_chave_pix) {
      document.getElementById('cfg-tipo-pix').value = state.configuracoes.tipo_chave_pix;
    }
    if (state.configuracoes.gemini_api_key) {
      document.getElementById('cfg-gemini-key').value = state.configuracoes.gemini_api_key;
    }
  } catch (err) {
    console.error('Erro ao carregar configurações:', err);
  }
}

function setupSettings() {
  document.getElementById('btn-salvar-configuracoes').addEventListener('click', async () => {
    const configs = {
      nome_studio: document.getElementById('cfg-nome-studio').value.trim() || 'Shanti Studio de Yoga',
      chave_pix: document.getElementById('cfg-chave-pix').value.trim(),
      tipo_chave_pix: document.getElementById('cfg-tipo-pix').value,
      gemini_api_key: document.getElementById('cfg-gemini-key').value.trim()
    };

    try {
      await fetch('/api/configuracoes', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ configs })
      });
      state.configuracoes = configs;
      document.getElementById('header-studio-name').textContent = configs.nome_studio;
      showToast('Configurações salvas com sucesso!');
    } catch (err) {
      alert('Erro ao salvar configurações.');
    }
  });
}
