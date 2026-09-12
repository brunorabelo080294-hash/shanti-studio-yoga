/**
 * Shanti Studio de Yoga - WhatsApp Assistant Luxe PWA
 * Frontend JavaScript completo para chat, áudio, controle de alunos, relatórios e WhatsApp.
 */

// Estado global da aplicação
const state = {
  alunos: [],
  turmas: [],
  alunoSelecionado: null,
  isRecording: false,
  mediaRecorder: null,
  audioChunks: [],
  recordInterval: null,
  recordSeconds: 0,
  speechRecognition: null,
  currentFilter: 'todos',
  configuracoes: {},
  liveVoiceMode: false,
  isSpeaking: false
};

// =============================================================================
// INICIALIZAÇÃO
// =============================================================================
document.addEventListener('DOMContentLoaded', async () => {
  const dismissSplash = () => {
    const splash = document.getElementById('pwa-splash-screen');
    if (splash && !splash.classList.contains('hidden')) {
      splash.classList.add('hidden');
      setTimeout(() => { splash.style.display = 'none'; }, 400);
    }
  };

  const splashEl = document.getElementById('pwa-splash-screen');
  if (splashEl) splashEl.addEventListener('click', dismissSplash);

  // Fallback garantido independente de qualquer atraso ou erro
  setTimeout(dismissSplash, 1200);

  try {
    setupNavigation();
    setupChat();
    setupAudio();
    setupModals();
    setupSettings();
    
    // Pré-carregar vozes para síntese de fala
    if ('speechSynthesis' in window) {
      window.speechSynthesis.onvoiceschanged = () => {
        window.speechSynthesis.getVoices();
      };
    }

    // Horário da mensagem de boas-vindas
    const now = new Date();
    const timeStr = `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`;
    const welcomeTime = document.getElementById('welcome-time');
    if (welcomeTime) welcomeTime.textContent = timeStr;

    // Carregar dados
    await carregarConfiguracoes();
    await atualizarTudo();
  } catch (err) {
    console.error('Erro na inicialização do app:', err);
  } finally {
    setTimeout(dismissSplash, 300);
  }
});

async function atualizarTudo() {
  await carregarTurmas();
  await carregarAlunos();
  await carregarFinanceiro();
  await carregarEstudio();
}

async function carregarTurmas() {
  try {
    const res = await fetch('/api/turmas');
    state.turmas = await res.json();
    renderizarSeletorTurmas();
    renderizarTurmasOcupacao();
  } catch (err) {
    console.warn('Erro ao carregar turmas:', err);
  }
}

function renderizarSeletorTurmas() {
  const container = document.getElementById('cad-turmas-container');
  if (!container) return;
  if (!state.turmas || state.turmas.length === 0) {
    container.innerHTML = '<span style="font-size:12px; color:var(--wa-text-secondary);">Nenhuma turma ativa cadastrada.</span>';
    return;
  }
  container.innerHTML = state.turmas.map(t => {
    const cap = t.capacidade_vagas || 16;
    const total = t.total_matriculados || 0;
    const isLotada = t.lotada || (total >= cap);
    const isQuaseLotada = t.quase_lotada || (total === cap - 1);

    let vagasBadge = '';
    if (isLotada) {
      vagasBadge = `<span style="background:#fee2e2; color:#b91c1c; font-weight:700; padding:2px 8px; border-radius:6px; font-size:11px; display:inline-block; margin-top:2px; border:0.5px solid #fca5a5;">⚠️ LOTADA (${total}/${cap} alunos)</span>`;
    } else if (isQuaseLotada) {
      vagasBadge = `<span style="background:#fef3c7; color:#b45309; font-weight:700; padding:2px 8px; border-radius:6px; font-size:11px; display:inline-block; margin-top:2px; border:0.5px solid #fde68a;">⚡ Resta 1 vaga (${total}/${cap})</span>`;
    } else {
      vagasBadge = `<span style="color:var(--wa-success); font-weight:600; font-size:11.5px;">(${t.vagas_disponiveis} vagas livres de ${cap})</span>`;
    }

    return `
      <label style="display:flex; align-items:flex-start; gap:10px; cursor:pointer; font-size:12.5px; line-height:1.4; color:var(--wa-text-primary); padding:6px 4px; border-bottom:0.5px solid rgba(0,0,0,0.05);">
        <input type="checkbox" class="cad-turma-check" value="${t.id}" data-lotada="${isLotada ? '1' : '0'}" data-nome="${t.nome}" style="accent-color:var(--shanti-primary); cursor:pointer; margin-top:3px;">
        <div style="flex:1;">
          <b>${t.nome}</b> — ${t.dias_semana} às ${t.horario}
          <div>${vagasBadge}</div>
        </div>
      </label>
    `;
  }).join('');

  // Aviso caso o usuário marque uma turma que já atingiu os 16 alunos
  container.querySelectorAll('.cad-turma-check').forEach(chk => {
    chk.addEventListener('change', () => {
      if (chk.checked && chk.dataset.lotada === '1') {
        const confirmar = confirm(`⚠️ ATENÇÃO: A turma '${chk.dataset.nome}' já atingiu o limite máximo de 16 alunos (LOTADA)!\n\nDeseja realmente matricular este aluno nesta turma acima da capacidade permitida?`);
        if (!confirmar) {
          chk.checked = false;
        }
      }
    });
  });
}

function renderizarTurmasOcupacao() {
  const container = document.getElementById('list-turmas-ocupacao');
  const badgeTotal = document.getElementById('badge-turmas-total');
  if (!container) return;

  if (!state.turmas || state.turmas.length === 0) {
    container.innerHTML = '<div style="font-size:12px; color:var(--wa-text-secondary); text-align:center; padding:8px;">Nenhuma turma cadastrada.</div>';
    if (badgeTotal) badgeTotal.textContent = '0 Turmas';
    return;
  }

  const lotadas = state.turmas.filter(t => (t.total_matriculados || 0) >= (t.capacidade_vagas || 16));
  if (badgeTotal) {
    if (lotadas.length > 0) {
      badgeTotal.style.background = '#fee2e2';
      badgeTotal.style.color = '#b91c1c';
      badgeTotal.textContent = `⚠️ ${lotadas.length} Lotada${lotadas.length > 1 ? 's' : ''}`;
    } else {
      badgeTotal.style.background = '#e8f0eb';
      badgeTotal.style.color = 'var(--shanti-primary)';
      badgeTotal.textContent = `${state.turmas.length} Turmas`;
    }
  }

  container.innerHTML = state.turmas.map(t => {
    const cap = t.capacidade_vagas || 16;
    const total = t.total_matriculados || 0;
    const percent = Math.min(100, Math.round((total / cap) * 100));
    const isLotada = total >= cap;
    const isQuaseLotada = total === cap - 1;

    let barColor = 'var(--shanti-primary)';
    let statusBadge = `<span style="font-size:11px; font-weight:600; color:var(--wa-success);">${t.vagas_disponiveis} livres</span>`;

    if (isLotada) {
      barColor = '#dc2626'; // Vermelho de lotação máxima
      statusBadge = `<span style="background:#fee2e2; color:#b91c1c; font-weight:700; font-size:10.5px; padding:2px 7px; border-radius:6px; border:0.5px solid #fca5a5;">⚠️ LOTADA (16/16)</span>`;
    } else if (isQuaseLotada) {
      barColor = '#f59e0b'; // Laranja de última vaga
      statusBadge = `<span style="background:#fef3c7; color:#b45309; font-weight:700; font-size:10.5px; padding:2px 7px; border-radius:6px; border:0.5px solid #fde68a;">⚡ Resta 1 vaga</span>`;
    }

    return `
      <div style="background:var(--shanti-sand); padding:10px 12px; border-radius:10px; border:0.5px solid var(--wa-border);">
        <div style="display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:6px;">
          <div>
            <div style="font-weight:700; font-size:13px; color:var(--wa-text-primary);">${t.nome}</div>
            <div style="font-size:11.5px; color:var(--wa-text-secondary);"><i class="fa-regular fa-clock"></i> ${t.dias_semana} às ${t.horario}</div>
          </div>
          <div>${statusBadge}</div>
        </div>
        
        <!-- Barra de Progresso de Ocupação -->
        <div style="background:#e2e8f0; border-radius:999px; height:8px; width:100%; overflow:hidden; margin:8px 0 4px 0;">
          <div style="background:${barColor}; width:${percent}%; height:100%; border-radius:999px; transition:width 0.4s ease;"></div>
        </div>
        
        <div style="display:flex; justify-content:space-between; font-size:11px; color:var(--wa-text-secondary);">
          <span><b>${total}</b> de <b>${cap}</b> alunos matriculados</span>
          <span style="font-weight:600;">${percent}% ocupado</span>
        </div>
      </div>
    `;
  }).join('');
}

function showToast(msg) {
  const toast = document.getElementById('toast-msg');
  toast.textContent = msg;
  toast.style.display = 'block';
  setTimeout(() => {
    toast.style.display = 'none';
  }, 3000);
}

function formatarDataBR(dataStr) {
  if (!dataStr) return '';
  const partes = dataStr.split('T')[0].split('-');
  if (partes.length === 3) return `${partes[2]}/${partes[1]}/${partes[0]}`;
  return dataStr;
}

function formatarDataHoraBR(dataHoraStr) {
  if (!dataHoraStr) return '';
  const d = new Date(dataHoraStr);
  if (isNaN(d.getTime())) return dataHoraStr;
  const dia = String(d.getDate()).padStart(2, '0');
  const mes = String(d.getMonth() + 1).padStart(2, '0');
  const ano = d.getFullYear();
  const hora = String(d.getHours()).padStart(2, '0');
  const min = String(d.getMinutes()).padStart(2, '0');
  return `${dia}/${mes}/${ano} às ${hora}:${min}`;
}

// =============================================================================
// SÍNTESE DE VOZ (ASSISTENTE FALANTE 100% GRATUITO)
// =============================================================================
function limparTextoParaFala(texto) {
  if (!texto) return '';
  return texto
    .replace(/[*_#`~]/g, '') // remove formatação markdown
    .replace(/https?:\/\/\S+/g, '') // remove URLs
    .replace(/[\u{1F600}-\u{1F64F}\u{1F300}-\u{1F5FF}\u{1F680}-\u{1F6FF}\u{1F1E0}-\u{1F1FF}\u{2600}-\u{26FF}\u{2700}-\u{27BF}\u{1F900}-\u{1F9FF}\u{1FA70}-\u{1FAFF}]/gu, '') // remove emojis
    .replace(/\s+/g, ' ')
    .trim();
}

function falarTexto(texto, onEnd = null) {
  if (!('speechSynthesis' in window)) {
    if (onEnd) onEnd();
    return;
  }
  window.speechSynthesis.cancel();
  const textoLimpo = limparTextoParaFala(texto);
  if (!textoLimpo) {
    if (onEnd) onEnd();
    return;
  }

  const utterance = new SpeechSynthesisUtterance(textoLimpo);
  utterance.lang = 'pt-BR';
  utterance.rate = 1.05;
  utterance.pitch = 1.0;

  const voices = window.speechSynthesis.getVoices();
  const ptVoice = voices.find(v => (v.lang === 'pt-BR' || v.lang === 'pt_BR') && (v.name.includes('Google') || v.name.includes('Luciana') || v.name.includes('Maria') || v.name.includes('Natural') || v.name.includes('Francisca'))) 
               || voices.find(v => v.lang === 'pt-BR' || v.lang === 'pt_BR');
  if (ptVoice) utterance.voice = ptVoice;

  state.isSpeaking = true;

  utterance.onend = () => {
    state.isSpeaking = false;
    document.querySelectorAll('.wa-msg-speak-btn').forEach(btn => btn.classList.remove('speaking'));
    if (onEnd) onEnd();
  };

  utterance.onerror = (e) => {
    state.isSpeaking = false;
    document.querySelectorAll('.wa-msg-speak-btn').forEach(btn => btn.classList.remove('speaking'));
    console.warn('SpeechSynthesis error:', e);
    if (onEnd) onEnd();
  };

  window.speechSynthesis.speak(utterance);
}

function pararFala() {
  if ('speechSynthesis' in window) {
    window.speechSynthesis.cancel();
  }
  state.isSpeaking = false;
  document.querySelectorAll('.wa-msg-speak-btn').forEach(btn => btn.classList.remove('speaking'));
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
      state.lastActiveTab = tab.dataset.tab;
      tab.scrollIntoView({ behavior: 'smooth', inline: 'center', block: 'nearest' });

      const targetId = `screen-${tab.dataset.tab}`;
      const targetScreen = document.getElementById(targetId);
      if (targetScreen) targetScreen.classList.add('active');

      if (tab.dataset.tab === 'alunos') carregarAlunos();
      if (tab.dataset.tab === 'financeiro') carregarFinanceiro();
      if (tab.dataset.tab === 'estudio') carregarEstudio();
    });
  });

  // Botão de atualizar no header
  const btnHeaderAction = document.getElementById('btn-header-action') || document.getElementById('btn-header-notif');
  if (btnHeaderAction) {
    btnHeaderAction.addEventListener('click', async () => {
      showToast('Atualizando dados...');
      await atualizarTudo();
      showToast('Dados sincronizados!');
    });
  }

  // Botão de menu / engrenagem no header -> abre tela exclusiva de ajustes
  const btnHeaderMenu = document.getElementById('btn-header-menu');
  if (btnHeaderMenu) {
    btnHeaderMenu.addEventListener('click', () => {
      abrirTelaAjustes();
    });
  }

  // Botão Voltar da tela de Ajustes -> retorna à aba anterior
  const btnVoltarAjustes = document.getElementById('btn-voltar-ajustes');
  if (btnVoltarAjustes) {
    btnVoltarAjustes.addEventListener('click', () => {
      voltarDaTelaAjustes();
    });
  }
}

function abrirTelaAjustes() {
  const currentActiveTab = document.querySelector('.wa-tab-btn.active');
  if (currentActiveTab) {
    state.lastActiveTab = currentActiveTab.dataset.tab;
  }
  document.querySelectorAll('.wa-tab-btn').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.wa-screen').forEach(s => s.classList.remove('active'));
  const screenAjustes = document.getElementById('screen-ajustes');
  if (screenAjustes) screenAjustes.classList.add('active');
}

function voltarDaTelaAjustes() {
  const targetTabName = state.lastActiveTab || 'chat';
  const targetTab = document.querySelector(`.wa-tab-btn[data-tab="${targetTabName}"]`);
  if (targetTab) {
    targetTab.click();
  } else {
    const firstTab = document.querySelector('.wa-tab-btn');
    if (firstTab) firstTab.click();
  }
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

function adicionarMensagem(texto, remetente = 'bot', dadosExtras = null, elementId = null) {
  const container = document.getElementById('chat-messages');
  const rowEl = document.createElement('div');
  rowEl.className = `wa-message-row ${remetente}`;
  if (elementId) rowEl.id = elementId;

  const now = new Date();
  const timeStr = `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`;

  let formattedText = texto
    .replace(/\*(.*?)\*/g, '<b>$1</b>')
    .replace(/_(.*?)_/g, '<span>$1</span>');

  let htmlInner = '';
  
  // Se for mensagem da IA, exibir o avatar quadrado com borda dourada do Studio Shanti
  if (remetente === 'bot') {
    htmlInner += `<img src="/icons/icon-192.png?v=9" alt="Studio Shanti" class="wa-msg-avatar" style="border-radius: 8px; border: 1px solid var(--shanti-gold); background: #1C2B24;">`;
  }

  htmlInner += `
    <div class="wa-message ${remetente}">
      <div class="wa-message-content">${formattedText}</div>
  `;

  // Renderizar Cards de Ação Extras
  if (dadosExtras) {
    // 1. Recibo individual de pagamento
    if (dadosExtras.tipo === 'recibo' || dadosExtras.recibo || dadosExtras.texto_recibo) {
      const r = dadosExtras;
      htmlInner += `
        <div class="wa-action-card" style="border-left-color: var(--wa-success); margin-top: 10px;">
          <div class="wa-action-card-header">
            <span class="wa-action-card-name"><i class="fa-solid fa-receipt" style="color:var(--wa-success);"></i> Recibo de ${r.aluno || 'Mensalidade'}</span>
            <span class="wa-action-card-val">R$ ${(r.valor || 0).toFixed(2)}</span>
          </div>
          <div class="wa-action-card-sub" style="color: var(--shanti-primary); font-weight:600;">
            • Mês ${r.mes_referencia} (${r.forma_pagamento || 'PIX'})
          </div>
          ${r.link_whatsapp ? `
            <a href="${r.link_whatsapp}" target="_blank" class="wa-action-btn-whatsapp" style="background: linear-gradient(135deg, #10b981, #059669);">
              <i class="fa-brands fa-whatsapp"></i> Enviar Recibo no WhatsApp
            </a>
          ` : ''}
        </div>
      `;
    } 
    // 2. Lista de Alunos Ausentes
    else if (Array.isArray(dadosExtras) && dadosExtras.length > 0 && dadosExtras[0].dias_ausente !== undefined) {
      htmlInner += `<div style="margin-top: 10px; display: flex; flex-direction: column; gap: 8px;">`;
      dadosExtras.forEach(al => {
        htmlInner += `
          <div class="wa-action-card" style="border-left-color: #f59e0b;">
            <div class="wa-action-card-header">
              <span class="wa-action-card-name">${al.nome}</span>
              <span style="font-size:12px; color:#b45309; font-weight:700;">⚠️ ${al.dias_ausente} dias ausente</span>
            </div>
            <div class="wa-action-card-sub" style="color: var(--wa-text-secondary);">
              • Última presença: ${al.ultima_presenca ? formatarDataBR(al.ultima_presenca.split(' ')[0]) : 'Sem registro recente'}
            </div>
            ${al.link_whatsapp ? `
              <a href="${al.link_whatsapp}" target="_blank" class="wa-action-btn-whatsapp" style="background: linear-gradient(135deg, #f59e0b, #d97706);">
                <i class="fa-brands fa-whatsapp"></i> Convidar de Volta
              </a>
            ` : ''}
          </div>
        `;
      });
      htmlInner += `</div>`;
    }
    // 3. Lista de Aniversariantes do Mês
    else if (Array.isArray(dadosExtras) && dadosExtras.length > 0 && (dadosExtras[0].dia !== undefined || dadosExtras[0].data_nascimento !== undefined)) {
      htmlInner += `<div style="margin-top: 10px; display: flex; flex-direction: column; gap: 8px;">`;
      dadosExtras.forEach(al => {
        htmlInner += `
          <div class="wa-action-card" style="border-left-color: #ec4899;">
            <div class="wa-action-card-header">
              <span class="wa-action-card-name">🎂 ${al.nome}</span>
              <span style="font-size:12px; color:#db2777; font-weight:700;">Dia ${al.dia || (al.data_nascimento ? al.data_nascimento.split('-')[2] : '')}</span>
            </div>
            <div class="wa-action-card-sub" style="color: var(--wa-text-secondary);">
              • ${al.plano || 'Aluno(a) Shanti Yoga'}
            </div>
            ${al.link_whatsapp ? `
              <a href="${al.link_whatsapp}" target="_blank" class="wa-action-btn-whatsapp" style="background: linear-gradient(135deg, #ec4899, #db2777);">
                <i class="fa-brands fa-whatsapp"></i> Dar Parabéns
              </a>
            ` : ''}
          </div>
        `;
      });
      htmlInner += `</div>`;
    }
    // 4. Lista Padrão de Cobrança de Atrasados
    else if (Array.isArray(dadosExtras) && dadosExtras.length > 0) {
      htmlInner += `<div style="margin-top: 10px; display: flex; flex-direction: column; gap: 8px;">`;
      dadosExtras.forEach(al => {
        htmlInner += `
          <div class="wa-action-card">
            <div class="wa-action-card-header">
              <span class="wa-action-card-name">${al.nome}</span>
              <span class="wa-action-card-val">R$ ${(al.valor || 0).toFixed(2)}</span>
            </div>
            <div class="wa-action-card-sub">
              • ${al.situacao || 'Vencimento pendente'}
            </div>
            <a href="${al.link_whatsapp}" target="_blank" class="wa-action-btn-whatsapp">
              <i class="fa-brands fa-whatsapp"></i> Cobrar no WhatsApp
            </a>
          </div>
        `;
      });
      htmlInner += `</div>`;
    }
  }

  htmlInner += `
      <div class="wa-message-footer">
        ${remetente === 'bot' ? `
          <button class="wa-msg-speak-btn" title="Ouvir resposta em áudio">
            <i class="fa-solid fa-volume-high"></i> Ouvir
          </button>
        ` : ''}
        <span class="wa-msg-time">${timeStr}</span>
        ${remetente === 'user' ? '<span class="wa-ticks">✓✓</span>' : ''}
      </div>
    </div>
  `;

  rowEl.innerHTML = htmlInner;
  container.appendChild(rowEl);
  container.scrollTop = container.scrollHeight;

  // Configurar botão de áudio na mensagem
  const speakBtn = rowEl.querySelector('.wa-msg-speak-btn');
  if (speakBtn) {
    speakBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      if (speakBtn.classList.contains('speaking')) {
        pararFala();
      } else {
        document.querySelectorAll('.wa-msg-speak-btn').forEach(b => b.classList.remove('speaking'));
        speakBtn.classList.add('speaking');
        falarTexto(texto, () => {
          speakBtn.classList.remove('speaking');
        });
      }
    });
  }

  return rowEl;
}

function criarIndicadorDigitacao(msgInicial = 'Consultando o estúdio... 🧘‍♀️') {
  const container = document.getElementById('chat-messages');
  const typingRow = document.createElement('div');
  typingRow.className = 'wa-message-row bot wa-typing-row';
  typingRow.innerHTML = `
    <img src="/icons/icon-192.png?v=9" alt="Studio Shanti" class="wa-msg-avatar" style="border-radius: 8px; border: 1px solid var(--shanti-gold); background: #1C2B24;">
    <div class="wa-message bot">
      <div class="wa-message-content" style="color:#63736d;"><span class="typing-text">${msgInicial}</span></div>
    </div>
  `;
  container.appendChild(typingRow);
  container.scrollTop = container.scrollHeight;

  const textEl = typingRow.querySelector('.typing-text');
  let seconds = 0;
  const interval = setInterval(() => {
    seconds += 3;
    if (!typingRow.parentNode) {
      clearInterval(interval);
      return;
    }
    if (seconds >= 12) {
      textEl.innerHTML = '⏳ O servidor está acordando no Render... Quase pronto... 🧘‍♀️';
    } else if (seconds >= 6) {
      textEl.innerHTML = '✨ Processando com a IA Gemini... 🧘‍♀️';
    }
  }, 3000);

  return {
    remover: () => {
      clearInterval(interval);
      if (typingRow.parentNode) typingRow.remove();
    },
    atualizarTexto: (novoTexto) => {
      if (textEl) textEl.innerHTML = novoTexto;
    }
  };
}

async function enviarMensagemTexto() {
  const input = document.getElementById('chat-input');
  const texto = input.value.trim();
  if (!texto) return;

  adicionarMensagem(texto, 'user');
  input.value = '';
  document.getElementById('btn-mic').style.display = 'flex';
  document.getElementById('btn-send').style.display = 'none';

  const indicador = criarIndicadorDigitacao('Consultando o estúdio... 🧘‍♀️');

  try {
    const res = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mensagem: texto })
    });
    const data = await res.json();
    indicador.remover();

    adicionarMensagem(data.resposta, 'bot', data.dados);
    
    if (data.tipo === 'pagamento_registrado' || data.tipo === 'aluno_inativado' || data.tipo === 'despesa_registrada' || data.tipo === 'presenca_registrada') {
      await atualizarTudo();
    }
  } catch (err) {
    indicador.remover();
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
    try {
      recognition = new SpeechRecognition();
      recognition.lang = 'pt-BR';
      recognition.continuous = true;
      recognition.interimResults = true;

      recognition.onresult = (event) => {
        let full = '';
        for (let i = 0; i < event.results.length; ++i) {
          full += event.results[i][0].transcript;
        }
        if (full.trim()) {
          speechTranscript = full.trim();
          const hint = document.getElementById('recording-hint');
          if (hint) {
            hint.textContent = `"${speechTranscript}"`;
          }
        }
      };

      recognition.onerror = (e) => {
        console.log('Speech recognition err:', e);
      };
    } catch (errRec) {
      console.warn('Erro ao inicializar SpeechRecognition:', errRec);
    }
  }

  const mobileMicInput = document.getElementById('mobile-mic-input');

  // Tratar arquivo de áudio gravado nativamente pelo celular
  if (mobileMicInput) {
    mobileMicInput.addEventListener('change', async (e) => {
      const file = e.target.files && e.target.files[0];
      if (!file) return;

      const userMsgId = 'voice-msg-' + Date.now();
      adicionarMensagem('🎙️ <i>Mensagem de voz enviada...</i>', 'user', null, userMsgId);

      const indicador = criarIndicadorDigitacao('Ouvindo o seu áudio com a IA Gemini... 🧘‍♀️');

      const formData = new FormData();
      formData.append('audio', file);

      try {
        const res = await fetch('/api/chat/audio', {
          method: 'POST',
          body: formData
        });
        const data = await res.json();
        indicador.remover();

        if (data.transcricao && data.transcricao !== 'Voz não identificada') {
          const userMsg = document.getElementById(userMsgId);
          if (userMsg) {
            const contentEl = userMsg.querySelector('.wa-message-content');
            if (contentEl) {
              contentEl.innerHTML = `🎙️ <b>"${data.transcricao}"</b><div style="font-size:10px; color:#5c786f; margin-top:3px;">✨ Transcrito pela IA Gemini</div>`;
            }
          }
        }

        adicionarMensagem(data.resposta, 'bot', data.dados);
        if (data.tipo === 'pagamento_registrado' || data.tipo === 'aluno_inativado' || data.tipo === 'despesa_registrada' || data.tipo === 'presenca_registrada') {
          await atualizarTudo();
        }
      } catch (err) {
        indicador.remover();
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

      const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
        ? 'audio/webm;codecs=opus'
        : (MediaRecorder.isTypeSupported('audio/mp4') ? 'audio/mp4' : 'audio/webm');

      state.mediaRecorder = new MediaRecorder(stream, { mimeType });
      state.mediaRecorder.ondataavailable = (e) => {
        if (e.data && e.data.size > 0) state.audioChunks.push(e.data);
      };

      // Gravar em fatias de 100ms para garantir que o buffer de áudio nunca fique vazio
      state.mediaRecorder.start(100);
      if (recognition) {
        try { recognition.start(); } catch (err) {}
      }

      btnMic.classList.add('recording');
      recordingOverlay.style.display = 'flex';
      inputPill.style.display = 'none';

      state.recordSeconds = 0;
      recordingTimer.textContent = '0:00';
      const hint = document.getElementById('recording-hint');
      if (hint) hint.textContent = "Ouvindo sua voz... toque no microfone para enviar";

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

        // Criar o arquivo de áudio real gravado
        const mimeType = (state.mediaRecorder && state.mediaRecorder.mimeType) || 'audio/webm';
        const audioBlob = new Blob(state.audioChunks, { type: mimeType });

        const textoPrevia = speechTranscript.trim();
        if (audioBlob.size < 400 && !textoPrevia) {
          showToast('Áudio muito curto. Fale um pouco mais.');
          return;
        }

        const userMsgId = 'voice-msg-' + Date.now();
        adicionarMensagem(textoPrevia ? `🎙️ <i>"${textoPrevia}"</i>` : `🎙️ <i>Mensagem de voz enviada...</i>`, 'user', null, userMsgId);

        const indicador = criarIndicadorDigitacao('Ouvindo o seu áudio com a IA Gemini... 🧘‍♀️');

        const formData = new FormData();
        formData.append('audio', audioBlob, 'audio.webm');
        if (textoPrevia) {
          formData.append('texto_transcrito', textoPrevia);
        }

        try {
          const res = await fetch('/api/chat/audio', {
            method: 'POST',
            body: formData
          });
          const data = await res.json();
          indicador.remover();

          // Atualizar o balão de voz com o que a IA realmente ouviu e transcreveu!
          if (data.transcricao && data.transcricao !== 'Voz não identificada') {
            const userMsg = document.getElementById(userMsgId);
            if (userMsg) {
              const contentEl = userMsg.querySelector('.wa-message-content');
              if (contentEl) {
                contentEl.innerHTML = `🎙️ <b>"${data.transcricao}"</b><div style="font-size:10px; color:#5c786f; margin-top:3px;">✨ Transcrito pela IA Gemini</div>`;
              }
            }
          }

          adicionarMensagem(data.resposta, 'bot', data.dados);
          if (data.tipo === 'pagamento_registrado' || data.tipo === 'aluno_inativado' || data.tipo === 'despesa_registrada' || data.tipo === 'presenca_registrada') {
            await atualizarTudo();
          }
        } catch (e) {
          indicador.remover();
          adicionarMensagem('Não consegui processar seu áudio no momento. Tente falar novamente!', 'bot');
        }
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

  // Controle do microfone: Alternância simples (clique para gravar / clique para enviar)
  // E também suporte a pressionar e segurar para falar (estilo WhatsApp)
  let recordStartTime = 0;
  let isHolding = false;
  let holdTimer = null;

  btnMic.addEventListener('pointerdown', async (e) => {
    e.preventDefault();
    if (state.isRecording) {
      // Já está gravando: segundo toque encerra e envia imediatamente!
      await stopRecording(true);
      return;
    }

    recordStartTime = Date.now();
    isHolding = false;
    holdTimer = setTimeout(() => {
      isHolding = true;
    }, 450);

    await startRecording();
  });

  btnMic.addEventListener('pointerup', async (e) => {
    e.preventDefault();
    clearTimeout(holdTimer);
    if (!state.isRecording) return;

    // Se segurou por mais de 450ms (hold-to-talk), envia ao soltar
    if (isHolding || (Date.now() - recordStartTime >= 450)) {
      await stopRecording(true);
    } else {
      // Foi apenas um toque rápido: mantém gravando e aguarda o próximo toque para enviar
      const hint = document.getElementById('recording-hint');
      if (hint && !speechTranscript) {
        hint.textContent = "Gravando voz... Toque no microfone para enviar";
      }
    }
  });
  window.pararGravacaoAoVivo = stopRecording;
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
        `Olá, ${al.nome}! 🧘‍♀️ Passando para lembrar com carinho que sua mensalidade do Studio Shanti venceu dia ${String(al.dia_vencimento).padStart(2, '0')} no valor de R$ ${al.valor_mensalidade.toFixed(2)}.\n\nChave PIX: ${state.configuracoes.chave_pix || 'contato@shantiyoga.com.br'}.\n\nGratidão e ótimas práticas! Namastê. 🙏`
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
          <span>${al.plano}${al.plano && al.plano.includes('1x') && al.dia_semana_1x ? ` (${al.dia_semana_1x})` : ''} • R$ ${al.valor_mensalidade.toFixed(2)}</span>
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

    // Dia da semana para plano 1x
    const boxDia1x = document.getElementById('det-box-dia-1x');
    const lblDia1x = document.getElementById('det-dia-semana-1x');
    const isPlano1x = al.plano && al.plano.includes('1x');
    if (boxDia1x) {
      boxDia1x.style.display = isPlano1x ? 'block' : 'none';
      if (lblDia1x) lblDia1x.textContent = al.dia_semana_1x || 'Não definido ainda';
    }

    const btnAlterarDia1x = document.getElementById('det-btn-alterar-dia-1x');
    if (btnAlterarDia1x) {
      btnAlterarDia1x.onclick = async () => {
        const opcoes = ['Segunda-feira', 'Terça-feira', 'Quarta-feira', 'Quinta-feira', 'Sexta-feira', 'Sábado'];
        const novoDia = prompt(
          `Escolha o dia da semana para ${al.nome} (1x na semana):\n\nOpções: ${opcoes.join(', ')}`,
          al.dia_semana_1x || 'Segunda-feira'
        );
        if (!novoDia || !novoDia.trim()) return;
        try {
          const r = await fetch(`/api/alunos/${al.id}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ dia_semana_1x: novoDia.trim() })
          });
          if (r.ok) {
            al.dia_semana_1x = novoDia.trim();
            if (lblDia1x) lblDia1x.textContent = novoDia.trim();
            showToast('Dia da semana atualizado com sucesso!');
            await atualizarTudo();
          } else {
            alert('Erro ao atualizar dia da semana.');
          }
        } catch (e) {
          alert('Erro de comunicação com o servidor.');
        }
      };
    }

    document.getElementById('det-valor').textContent = al.valor_mensalidade.toFixed(2);
    document.getElementById('det-dia-venc').textContent = al.dia_vencimento;
    
    // Turmas vinculadas
    const detTurmas = document.getElementById('det-turmas');
    if (detTurmas) {
      if (al.turmas && al.turmas.length > 0) {
        detTurmas.innerHTML = al.turmas.map(t => `<span style="display:inline-block; background:#e8f0eb; color:var(--shanti-primary); padding:2px 8px; border-radius:6px; margin:2px 2px; font-size:12px; border:0.5px solid var(--wa-border);"><b>${t.nome}</b> (${t.horario})</span>`).join(' ');
      } else {
        detTurmas.textContent = 'Nenhuma turma vinculada';
      }
    }

    // Data de Nascimento
    const detNasc = document.getElementById('det-nascimento');
    if (detNasc) {
      detNasc.textContent = al.data_nascimento ? formatarDataBR(al.data_nascimento) : 'Não informado';
    }

    // Autorização de Imagem (Fase 2)
    const badgeImg = document.getElementById('det-autoriza-imagem-badge');
    const autorizou = (al.autoriza_imagem === 1 || al.autoriza_imagem === true || al.autoriza_imagem === '1');
    if (badgeImg) {
      badgeImg.textContent = autorizou ? 'SIM (Autorizado)' : 'NÃO';
      badgeImg.className = `wa-student-badge ${autorizou ? 'badge-em-dia' : 'badge-atrasado'}`;
    }

    const btnToggleImg = document.getElementById('det-btn-toggle-imagem');
    if (btnToggleImg) {
      btnToggleImg.onclick = async () => {
        const novoValor = autorizou ? 0 : 1;
        try {
          await fetch(`/api/alunos/${al.id}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ autoriza_imagem: novoValor })
          });
          showToast(`Autorização de imagem alterada para ${novoValor ? 'SIM' : 'NÃO'}!`);
          await abrirDetalhesAluno(al.id);
          await carregarAlunos();
        } catch (e) {
          showToast('Erro ao alterar autorização.');
        }
      };
    }

    const badgeEl = document.getElementById('det-status-badge');
    badgeEl.textContent = al.status === 'ativo' ? 'Matrícula Ativa' : 'Inativo (Saída)';
    badgeEl.className = `wa-student-badge ${al.status === 'ativo' ? 'badge-em-dia' : 'badge-inativo'}`;

    const motivoBox = document.getElementById('det-motivo-box');
    const btnExcluir = document.getElementById('det-btn-excluir');
    if (al.status === 'inativo') {
      if (al.motivo_saida) {
        motivoBox.style.display = 'block';
        document.getElementById('det-motivo-saida').textContent = `${al.motivo_saida} (${al.data_saida || ''})`;
      } else {
        motivoBox.style.display = 'none';
      }
      document.getElementById('det-btn-inativar').style.display = 'none';
      document.getElementById('det-btn-reativar').style.display = 'block';
      if (btnExcluir) {
        btnExcluir.style.display = 'block';
        btnExcluir.onclick = async () => {
          if (confirm(`Tem certeza que deseja excluir permanentemente o cadastro de "${al.nome}"? Esta ação removerá o histórico e não poderá ser desfeita.`)) {
            try {
              const res = await fetch(`/api/alunos/${al.id}`, { method: 'DELETE' });
              if (res.ok) {
                showToast(`Aluno(a) ${al.nome} excluído(a) com sucesso.`);
                fecharModal('modal-student-details');
                await atualizarTudo();
              } else {
                showToast('Erro ao excluir aluno.');
              }
            } catch (err) {
              showToast('Falha na comunicação com o servidor.');
            }
          }
        };
      }
    } else {
      motivoBox.style.display = 'none';
      document.getElementById('det-btn-inativar').style.display = 'block';
      document.getElementById('det-btn-reativar').style.display = 'none';
      if (btnExcluir) btnExcluir.style.display = 'none';
    }

    let tel = al.telefone.replace(/\D/g, '');
    if (!tel.startsWith('55')) tel = '55' + tel;
    const msg = encodeURIComponent(`Olá, ${al.nome}! Tudo bem? Studio Shanti passando para falar com você. Namastê 🙏`);
    document.getElementById('det-btn-whatsapp').href = `https://wa.me/${tel}?text=${msg}`;

    // Configurar botão de Marcar Presença
    const btnPresenca = document.getElementById('det-btn-presenca');
    if (btnPresenca) {
      btnPresenca.onclick = async () => {
        try {
          await fetch('/api/frequencias', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ aluno_id: al.id, modalidade: al.plano })
          });
          showToast(`Presença de ${al.nome} registrada! 🧘‍♀️`);
          await carregarPresencasAluno(al.id);
          await carregarEstudio();
        } catch (e) {
          showToast('Erro ao registrar presença');
        }
      };
    }

    // Histórico de Pagamentos
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

    // Histórico de Presenças
    await carregarPresencasAluno(al.id);

    abrirModal('modal-student-details');
  } catch (err) {
    console.error('Erro ao buscar detalhes:', err);
  }
}

async function carregarPresencasAluno(alunoId) {
  const histPresencas = document.getElementById('det-historico-presencas');
  if (!histPresencas) return;
  try {
    const res = await fetch(`/api/frequencias?aluno_id=${alunoId}&limit=10`);
    const frequencias = await res.json();
    if (!frequencias || frequencias.length === 0) {
      histPresencas.innerHTML = '<div style="font-size: 12px; color: #8c9c94; text-align: center; padding: 10px;">Nenhuma presença registrada ainda. Toque em "Marcar Presença" acima! 🧘‍♀️</div>';
    } else {
      histPresencas.innerHTML = frequencias.map(f => `
        <div style="display: flex; justify-content: space-between; font-size: 12.5px; padding: 6px 0; border-bottom: 1px dashed var(--wa-border);">
          <span><i class="fa-solid fa-check-circle" style="color:var(--wa-success);"></i> <b>${f.modalidade || 'Aula de Yoga'}</b></span>
          <span style="color: var(--shanti-primary); font-weight: 600;">${formatarDataHoraBR(f.data_presenca)}</span>
        </div>
      `).join('');
    }
  } catch (err) {
    console.warn('Erro ao carregar presenças:', err);
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

  const cadPlanoSelect = document.getElementById('cad-plano');
  const groupDia1x = document.getElementById('group-cad-dia-semana-1x');
  const cadDia1xSelect = document.getElementById('cad-dia-semana-1x');

  const toggleDiaSemana1x = () => {
    if (!cadPlanoSelect || !groupDia1x) return;
    const is1x = cadPlanoSelect.value.includes('1x');
    groupDia1x.style.display = is1x ? 'block' : 'none';
    if (!is1x && cadDia1xSelect) {
      cadDia1xSelect.value = '';
    }
  };

  if (cadPlanoSelect) {
    cadPlanoSelect.addEventListener('change', () => {
      const preco = cadPlanoSelect.value.includes('1x') 
        ? (state.configuracoes.valor_plano_1x || '120.00') 
        : (state.configuracoes.valor_plano_2x || '150.00');
      document.getElementById('cad-valor').value = parseFloat(preco).toFixed(2);
      toggleDiaSemana1x();
    });
  }

  document.getElementById('btn-open-add-student').addEventListener('click', () => {
    document.getElementById('form-add-student').reset();
    renderizarSeletorTurmas();
    
    // Configurar plano e valor inicial padrão (2x na semana)
    if (cadPlanoSelect) cadPlanoSelect.value = '2x na semana';
    toggleDiaSemana1x();
    const precoPadrao = state.configuracoes.valor_plano_2x || '150.00';
    document.getElementById('cad-valor').value = parseFloat(precoPadrao).toFixed(2);

    // Marcar Autorização de Imagem como SIM por padrão
    const radioSim = document.querySelector('input[name="cad-autoriza-imagem"][value="1"]');
    if (radioSim) radioSim.checked = true;

    const now = new Date();
    const mesAtual = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
    const el = document.getElementById('cad-mes-matricula');
    if (el) el.value = mesAtual;
    abrirModal('modal-add-student');
  });

  document.getElementById('form-add-student').addEventListener('submit', async (e) => {
    e.preventDefault();
    const turmaChecks = document.querySelectorAll('.cad-turma-check:checked');
    const turma_ids = Array.from(turmaChecks).map(c => parseInt(c.value));
    const radioImg = document.querySelector('input[name="cad-autoriza-imagem"]:checked');
    const autoriza_imagem = radioImg ? parseInt(radioImg.value) : 1;
    const plano = document.getElementById('cad-plano').value;
    const dia_semana_1x = plano.includes('1x') ? (document.getElementById('cad-dia-semana-1x')?.value || null) : null;

    if (plano.includes('1x') && !dia_semana_1x) {
      alert('Por favor, selecione qual dia da semana o aluno irá comparecer (plano 1x na semana).');
      document.getElementById('cad-dia-semana-1x')?.focus();
      return;
    }

    const dados = {
      nome: document.getElementById('cad-nome').value.trim(),
      telefone: document.getElementById('cad-telefone').value.trim(),
      email: document.getElementById('cad-email').value.trim(),
      data_nascimento: document.getElementById('cad-nascimento').value || null,
      plano: plano,
      dia_semana_1x: dia_semana_1x,
      dia_vencimento: parseInt(document.getElementById('cad-vencimento').value),
      valor_mensalidade: parseFloat(document.getElementById('cad-valor').value),
      tipo_pagamento: document.getElementById('cad-forma-pagamento').value,
      mes_matricula: document.getElementById('cad-mes-matricula').value,
      observacoes: document.getElementById('cad-obs').value.trim(),
      autoriza_imagem: autoriza_imagem,
      turma_ids: turma_ids
    };

    try {
      const res = await fetch('/api/alunos', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(dados)
      });
      const dataResp = await res.json();
      fecharModal('modal-add-student');
      showToast(`Aluno(a) ${dados.nome} matriculado(a)!`);
      await atualizarTudo();
      
      let msgBot = `🎉 *Nova matrícula realizada:* ${dados.nome} no plano *${dados.plano}* (Vencimento dia ${dados.dia_vencimento}).`;
      if (dataResp && dataResp.aviso_lotacao) {
        msgBot += `\n\n${dataResp.aviso_lotacao}`;
        alert(dataResp.aviso_lotacao);
      }
      adicionarMensagem(msgBot, 'bot');
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

  // Modal de Despesas (Cadastro)
  const btnAbrirDespesa = document.getElementById('btn-abrir-modal-despesa');
  if (btnAbrirDespesa) {
    btnAbrirDespesa.addEventListener('click', () => {
      const form = document.getElementById('form-add-despesa');
      if (form) form.reset();
      const today = new Date().toISOString().split('T')[0];
      const dataInput = document.getElementById('desp-data');
      if (dataInput) dataInput.value = today;
      const vencInput = document.getElementById('desp-vencimento');
      if (vencInput) vencInput.value = today;
      abrirModal('modal-add-despesa');
    });
  }

  const formDespesa = document.getElementById('form-add-despesa');
  if (formDespesa) {
    formDespesa.addEventListener('submit', async (e) => {
      e.preventDefault();
      const dados = {
        descricao: document.getElementById('desp-desc').value.trim(),
        valor: parseFloat(document.getElementById('desp-valor').value),
        categoria: document.getElementById('desp-cat').value,
        data_despesa: document.getElementById('desp-data').value || undefined,
        data_vencimento: document.getElementById('desp-vencimento')?.value || undefined,
        status: document.getElementById('desp-status')?.value || 'pago'
      };

      try {
        await fetch('/api/despesas', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(dados)
        });
        fecharModal('modal-add-despesa');
        showToast('Despesa registrada com sucesso!');
        await carregarFinanceiro();

        adicionarMensagem(`💸 *Despesa registrada:* ${dados.descricao} no valor de *R$ ${dados.valor.toFixed(2)}* (${dados.categoria}) - Vencimento: ${dados.data_vencimento ? formatarDataBR(dados.data_vencimento) : 'Hoje'}.`, 'bot');
      } catch (err) {
        alert('Erro ao registrar despesa.');
      }
    });
  }

  // Modal de Edição de Despesa
  const formEditDespesa = document.getElementById('form-edit-despesa');
  if (formEditDespesa) {
    formEditDespesa.addEventListener('submit', async (e) => {
      e.preventDefault();
      const id = document.getElementById('edit-desp-id').value;
      const dados = {
        descricao: document.getElementById('edit-desp-desc').value.trim(),
        valor: parseFloat(document.getElementById('edit-desp-valor').value),
        categoria: document.getElementById('edit-desp-cat').value,
        data_despesa: document.getElementById('edit-desp-data').value || undefined,
        data_vencimento: document.getElementById('edit-desp-vencimento').value || undefined,
        status: document.getElementById('edit-desp-status').value || 'pago'
      };

      try {
        const res = await fetch(`/api/despesas/${id}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(dados)
        });
        if (res.ok) {
          fecharModal('modal-edit-despesa');
          showToast('Despesa atualizada com sucesso!');
          await carregarFinanceiro();
        } else {
          alert('Erro ao atualizar despesa.');
        }
      } catch (err) {
        alert('Erro ao atualizar despesa.');
      }
    });
  }

  // Botão de Download do Relatório Oficial em PDF (Fase 3)
  const btnPdf = document.getElementById('btn-baixar-relatorio-pdf');
  if (btnPdf) {
    btnPdf.addEventListener('click', () => {
      const filtroMes = document.getElementById('filtro-financeiro-mes')?.value;
      let url = '/api/relatorio/pdf';
      if (filtroMes) {
        url += `?mes_ano=${filtroMes}`;
      }
      showToast('Gerando relatório financeiro oficial...');
      window.open(url, '_blank');
    });
  }

  // Filtro de Mês no Painel Financeiro
  const filtroMesEl = document.getElementById('filtro-financeiro-mes');
  if (filtroMesEl) {
    const now = new Date();
    const mesAtualStr = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
    filtroMesEl.value = mesAtualStr;
    filtroMesEl.addEventListener('change', () => {
      carregarFinanceiro();
    });
  }

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
// PAINEL FINANCEIRO (EXCLUSIVAMENTE FINANCEIRO)
// =============================================================================
async function carregarFinanceiro() {
  try {
    const inputMes = document.getElementById('filtro-financeiro-mes');
    let mesAno = inputMes ? inputMes.value : '';
    if (!mesAno) {
      const now = new Date();
      mesAno = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
      if (inputMes) inputMes.value = mesAno;
    }

    const [ano, mes] = mesAno.split('-');
    const mesesNomes = ['Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho', 'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro'];
    const nomeMes = mesesNomes[parseInt(mes, 10) - 1] || mes;
    const labelMes = document.getElementById('rep-mes-atual');
    if (labelMes) labelMes.textContent = `${nomeMes} / ${ano}`;

    const [resRel, resDesp, resAlertas] = await Promise.all([
      fetch(`/api/relatorio?mes_ano=${mesAno}`),
      fetch(`/api/despesas?mes_ano=${mesAno}`),
      fetch('/api/despesas/alertas')
    ]);

    const rel = await resRel.json();
    const despesas = await resDesp.json();
    const alertas = await resAlertas.json();

    // 1. Estatísticas do Balanço
    const elPrevisto = document.getElementById('stat-faturamento-previsto');
    if (elPrevisto) elPrevisto.textContent = `R$ ${rel.faturamento_previsto.toFixed(2)}`;
    const elRealizado = document.getElementById('stat-faturamento-realizado');
    if (elRealizado) elRealizado.textContent = `R$ ${rel.faturamento_realizado.toFixed(2)}`;
    const elDespesas = document.getElementById('stat-total-despesas');
    if (elDespesas) elDespesas.textContent = `R$ ${(rel.total_despesas || 0).toFixed(2)}`;
    const elLucro = document.getElementById('stat-lucro-real');
    if (elLucro) {
      const lucroVal = rel.lucro_liquido_real !== undefined ? rel.lucro_liquido_real : ((rel.faturamento_realizado || 0) - (rel.total_despesas || 0));
      elLucro.textContent = `R$ ${lucroVal.toFixed(2)}`;
      elLucro.style.color = lucroVal >= 0 ? 'var(--shanti-primary)' : 'var(--wa-danger)';
    }

    // 2. Banner de Alertas de Vencimento
    const bannerAlerta = document.getElementById('alerta-despesas-vencimento');
    if (bannerAlerta) {
      if (alertas.total_atrasadas > 0) {
        bannerAlerta.style.display = 'block';
        bannerAlerta.style.background = '#fee2e2';
        bannerAlerta.style.border = '1px solid #fca5a5';
        bannerAlerta.style.color = '#991b1b';
        bannerAlerta.innerHTML = `<i class="fa-solid fa-triangle-exclamation"></i> <b>${alertas.total_atrasadas} despesa(s) vencida(s) em aberto!</b> Total pendente: <b>R$ ${alertas.valor_total_atrasadas.toFixed(2)}</b>. Verifique abaixo para regularizar.`;
      } else if (alertas.total_vencendo_hoje > 0) {
        bannerAlerta.style.display = 'block';
        bannerAlerta.style.background = '#fef3c7';
        bannerAlerta.style.border = '1px solid #fde68a';
        bannerAlerta.style.color = '#92400e';
        bannerAlerta.innerHTML = `<i class="fa-solid fa-clock"></i> <b>${alertas.total_vencendo_hoje} conta(s) vencendo HOJE!</b> Total: <b>R$ ${alertas.valor_total_hoje.toFixed(2)}</b>.`;
      } else if (alertas.total_proximas > 0) {
        bannerAlerta.style.display = 'block';
        bannerAlerta.style.background = '#e0f2fe';
        bannerAlerta.style.border = '1px solid #bae6fd';
        bannerAlerta.style.color = '#075985';
        bannerAlerta.innerHTML = `<i class="fa-solid fa-circle-info"></i> <b>${alertas.total_proximas} despesa(s) vencem nos próximos 5 dias.</b> Total: R$ ${alertas.valor_total_proximas.toFixed(2)}.`;
      } else {
        bannerAlerta.style.display = 'none';
      }
    }

    // 3. Renderizar Lista Detalhada de Pagamentos Recebidos (Quem Pagou)
    const containerPagamentos = document.getElementById('lista-pagamentos-detalhada');
    const badgePagantes = document.getElementById('badge-total-pagantes');
    const pagamentos = rel.pagamentos_detalhados || [];

    if (badgePagantes) {
      badgePagantes.textContent = `${pagamentos.length} confirmado${pagamentos.length === 1 ? '' : 's'}`;
    }

    if (containerPagamentos) {
      if (!pagamentos || pagamentos.length === 0) {
        containerPagamentos.innerHTML = `
          <div style="font-size: 12px; color: var(--wa-text-secondary); text-align: center; padding: 14px; background: var(--shanti-sand); border-radius: 8px;">
            Nenhum pagamento registrado ou confirmado para ${nomeMes}/${ano} até o momento.
          </div>
        `;
      } else {
        containerPagamentos.innerHTML = pagamentos.map(p => {
          let planoFormatado = p.aluno_plano || 'Mensalidade Regular';
          if (planoFormatado.includes('1x') && p.dia_semana_1x) {
            planoFormatado += ` (${p.dia_semana_1x})`;
          }
          return `
            <div style="background:var(--shanti-sand); border:0.5px solid var(--wa-border); border-radius:8px; padding:10px 12px; display:flex; justify-content:space-between; align-items:center; gap:10px;">
              <div style="flex:1; min-width:0;">
                <div style="display:flex; align-items:center; gap:6px; flex-wrap:wrap; margin-bottom:3px;">
                  <span style="font-weight:700; font-size:13px; color:var(--wa-text-primary);">${p.aluno_nome}</span>
                  <span style="font-size:10.5px; background:rgba(43,76,60,0.08); color:var(--shanti-primary); padding:1px 6px; border-radius:4px; font-weight:600;">${planoFormatado}</span>
                  <span style="background:#e8f5e9; color:#2e7d32; font-weight:700; font-size:10.5px; padding:2px 7px; border-radius:6px; border:0.5px solid #a5d6a7;"><i class="fa-solid fa-check"></i> Pago</span>
                </div>
                <div style="font-size:11.5px; color:var(--wa-text-secondary);">
                  <span>Data: <b>${formatarDataBR(p.data_pagamento)}</b></span> • <span>Forma: <b>${p.forma_pagamento || 'PIX'}</b></span>
                </div>
              </div>
              <div style="text-align:right; display:flex; flex-direction:column; align-items:flex-end; gap:6px;">
                <span style="font-weight:800; font-size:13.5px; color:#15803d;">+ R$ ${p.valor.toFixed(2)}</span>
                <button class="btn-recibo-pagamento-financeiro" data-id="${p.id}" title="Ver Comprovante" style="background:#fff; border:0.5px solid var(--wa-border); border-radius:6px; padding:3px 8px; font-size:11px; color:var(--shanti-primary); cursor:pointer;">
                  <i class="fa-solid fa-receipt"></i> Recibo
                </button>
              </div>
            </div>
          `;
        }).join('');

        containerPagamentos.querySelectorAll('.btn-recibo-pagamento-financeiro').forEach(btn => {
          btn.addEventListener('click', async () => {
            const pagId = btn.dataset.id;
            try {
              const res = await fetch(`/api/pagamentos/${pagId}/recibo`);
              if (res.ok) {
                const dados = await res.json();
                if (dados.whatsapp_url) {
                  window.open(dados.whatsapp_url, '_blank');
                } else {
                  alert(dados.mensagem || 'Recibo gerado.');
                }
              } else {
                alert('Erro ao carregar recibo de pagamento.');
              }
            } catch (err) {
              console.error('Erro ao abrir recibo:', err);
            }
          });
        });
      }
    }

    // 4. Renderizar Lista Detalhada de Despesas
    const containerDespesas = document.getElementById('lista-despesas-detalhada');
    if (containerDespesas) {
      if (!despesas || despesas.length === 0) {
        containerDespesas.innerHTML = `
          <div style="font-size: 12px; color: var(--wa-text-secondary); text-align: center; padding: 14px; background: var(--shanti-sand); border-radius: 8px;">
            Nenhuma despesa registrada para ${nomeMes}/${ano}.<br>Clique em <b>+ Nova Despesa</b> para cadastrar.
          </div>
        `;
      } else {
        const hojeIso = new Date().toISOString().split('T')[0];
        containerDespesas.innerHTML = despesas.map(d => {
          const isPago = d.status === 'pago';
          const dtVenc = d.data_vencimento || d.data_despesa || '';
          const isAtrasado = !isPago && dtVenc && dtVenc < hojeIso;
          const isHoje = !isPago && dtVenc && dtVenc === hojeIso;

          let statusBadge = '';
          if (isPago) {
            statusBadge = `<span style="background:#e8f5e9; color:#2e7d32; font-weight:700; font-size:10.5px; padding:2px 7px; border-radius:6px; border:0.5px solid #a5d6a7;"><i class="fa-solid fa-check"></i> Paga</span>`;
          } else if (isAtrasado) {
            statusBadge = `<span style="background:#fee2e2; color:#b91c1c; font-weight:700; font-size:10.5px; padding:2px 7px; border-radius:6px; border:0.5px solid #fca5a5;"><i class="fa-solid fa-exclamation"></i> Vencida</span>`;
          } else if (isHoje) {
            statusBadge = `<span style="background:#fef3c7; color:#b45309; font-weight:700; font-size:10.5px; padding:2px 7px; border-radius:6px; border:0.5px solid #fde68a;"><i class="fa-solid fa-clock"></i> Vence Hoje</span>`;
          } else {
            statusBadge = `<span style="background:#f1f5f9; color:#475569; font-weight:600; font-size:10.5px; padding:2px 7px; border-radius:6px; border:0.5px solid #cbd5e1;">A Pagar</span>`;
          }

          return `
            <div style="background:var(--shanti-sand); border:0.5px solid var(--wa-border); border-radius:8px; padding:10px 12px; display:flex; justify-content:space-between; align-items:center; gap:10px;">
              <div style="flex:1; min-width:0;">
                <div style="display:flex; align-items:center; gap:6px; flex-wrap:wrap; margin-bottom:3px;">
                  <span style="font-weight:700; font-size:13px; color:var(--wa-text-primary);">${d.descricao}</span>
                  <span style="font-size:10.5px; background:rgba(43,76,60,0.08); color:var(--shanti-primary); padding:1px 6px; border-radius:4px; font-weight:600;">${d.categoria}</span>
                  ${statusBadge}
                </div>
                <div style="font-size:11.5px; color:var(--wa-text-secondary);">
                  <span>Vencimento: <b>${formatarDataBR(dtVenc)}</b></span>
                  ${d.data_despesa && d.data_despesa !== dtVenc ? ` • <span style="font-size:11px;">Emissão: ${formatarDataBR(d.data_despesa)}</span>` : ''}
                </div>
              </div>

              <div style="text-align:right; display:flex; flex-direction:column; align-items:flex-end; gap:6px;">
                <span style="font-weight:800; font-size:13.5px; color:#b91c1c;">- R$ ${d.valor.toFixed(2)}</span>
                <div style="display:flex; gap:6px;">
                  <button class="btn-editar-despesa" data-id="${d.id}" title="Editar Despesa" style="background:#fff; border:0.5px solid var(--wa-border); border-radius:6px; padding:4px 8px; font-size:11px; color:var(--shanti-primary); cursor:pointer;">
                    <i class="fa-solid fa-pen"></i>
                  </button>
                  <button class="btn-excluir-despesa" data-id="${d.id}" data-desc="${d.descricao}" title="Excluir Despesa" style="background:#fff; border:0.5px solid #fca5a5; border-radius:6px; padding:4px 8px; font-size:11px; color:#b91c1c; cursor:pointer;">
                    <i class="fa-solid fa-trash"></i>
                  </button>
                </div>
              </div>
            </div>
          `;
        }).join('');

        containerDespesas.querySelectorAll('.btn-editar-despesa').forEach(btn => {
          btn.addEventListener('click', () => {
            abrirModalEditarDespesa(parseInt(btn.dataset.id));
          });
        });

        containerDespesas.querySelectorAll('.btn-excluir-despesa').forEach(btn => {
          btn.addEventListener('click', () => {
            excluirDespesa(parseInt(btn.dataset.id), btn.dataset.desc);
          });
        });
      }
    }

    const btnCobrar = document.getElementById('btn-gerar-cobrancas-relatorio');
    if (btnCobrar) {
      btnCobrar.onclick = () => {
        const tabAlunos = document.querySelector('.wa-tab-btn[data-tab="alunos"]');
        if (tabAlunos) tabAlunos.click();
        const chipAtrasados = document.querySelector('.wa-filter-chip[data-filter="atrasados"]');
        if (chipAtrasados) chipAtrasados.click();
      };
    }

  } catch (err) {
    console.error('Erro ao carregar dados financeiros:', err);
  }
}

async function abrirModalEditarDespesa(id) {
  try {
    const res = await fetch(`/api/despesas/${id}`);
    if (!res.ok) {
      alert('Despesa não encontrada.');
      return;
    }
    const desp = await res.json();
    document.getElementById('edit-desp-id').value = desp.id;
    document.getElementById('edit-desp-desc').value = desp.descricao || '';
    document.getElementById('edit-desp-valor').value = desp.valor !== undefined ? desp.valor : '';
    document.getElementById('edit-desp-cat').value = desp.categoria || 'Geral';
    document.getElementById('edit-desp-data').value = desp.data_despesa || '';
    document.getElementById('edit-desp-vencimento').value = desp.data_vencimento || desp.data_despesa || '';
    document.getElementById('edit-desp-status').value = desp.status || 'pago';
    abrirModal('modal-edit-despesa');
  } catch (err) {
    console.error('Erro ao abrir edição de despesa:', err);
  }
}

async function excluirDespesa(id, descricao) {
  if (!confirm(`Tem certeza de que deseja apagar a despesa "${descricao}"?\n\nEsta ação removerá o registro do balanço financeiro.`)) {
    return;
  }
  try {
    const res = await fetch(`/api/despesas/${id}`, { method: 'DELETE' });
    if (res.ok) {
      showToast('Despesa apagada com sucesso!');
      await carregarFinanceiro();
    } else {
      alert('Erro ao excluir despesa.');
    }
  } catch (err) {
    console.error('Erro ao excluir despesa:', err);
    alert('Erro ao comunicar com o servidor.');
  }
}

// =============================================================================
// TELA DO ESTÚDIO (TURMAS, ALUNOS MATRICULADOS, ANIVERSÁRIOS & MÉTRICAS)
// =============================================================================
async function carregarEstudio() {
  try {
    const [resTurmas, resAniv, resAusentes, resQuant] = await Promise.all([
      fetch('/api/turmas/completo'),
      fetch('/api/aniversariantes'),
      fetch('/api/frequencias/ausentes?dias=10'),
      fetch('/api/quantitativo')
    ]);

    const turmas = await resTurmas.json();
    const aniversariantes = await resAniv.json();
    const ausentes = await resAusentes.json();
    const quant = await resQuant.json();

    // 1. Relação de Turmas e Alunos Matriculados
    const containerTurmas = document.getElementById('lista-turmas-alunos-estudio');
    const badgeTurmas = document.getElementById('badge-estudio-turmas');
    if (badgeTurmas) {
      const lotadas = turmas.filter(t => (t.total_matriculados || 0) >= (t.capacidade_vagas || 16));
      if (lotadas.length > 0) {
        badgeTurmas.style.background = '#fee2e2';
        badgeTurmas.style.color = '#b91c1c';
        badgeTurmas.textContent = `⚠️ ${lotadas.length} Turma(s) Lotada(s)`;
      } else {
        badgeTurmas.style.background = '#e8f0eb';
        badgeTurmas.style.color = 'var(--shanti-primary)';
        badgeTurmas.textContent = `${turmas.length} Turmas Ativas`;
      }
    }

    if (containerTurmas) {
      if (!turmas || turmas.length === 0) {
        containerTurmas.innerHTML = '<div style="font-size:12px; color:var(--wa-text-secondary); text-align:center; padding:12px;">Nenhuma turma cadastrada.</div>';
      } else {
        containerTurmas.innerHTML = turmas.map(t => {
          const cap = t.capacidade_vagas || 16;
          const total = t.total_matriculados || 0;
          const isLotada = total >= cap;
          const isQuaseLotada = total === cap - 1;
          const percent = Math.min(100, Math.round((total / cap) * 100));

          let barColor = 'var(--shanti-primary)';
          let statusBadge = `<span style="font-size:11px; font-weight:700; color:var(--wa-success);">${t.vagas_disponiveis} vagas livres</span>`;

          if (isLotada) {
            barColor = '#dc2626';
            statusBadge = `<span style="background:#fee2e2; color:#b91c1c; font-weight:700; font-size:10.5px; padding:2px 7px; border-radius:6px; border:0.5px solid #fca5a5;">⚠️ LOTADA (16/16)</span>`;
          } else if (isQuaseLotada) {
            barColor = '#f59e0b';
            statusBadge = `<span style="background:#fef3c7; color:#b45309; font-weight:700; font-size:10.5px; padding:2px 7px; border-radius:6px; border:0.5px solid #fde68a;">⚡ Resta 1 vaga</span>`;
          }

          let alunosHtml = '';
          if (!t.alunos || t.alunos.length === 0) {
            alunosHtml = `
              <div style="font-size:12px; color:var(--wa-text-secondary); font-style:italic; padding:6px 0;">
                Nenhum aluno matriculado nesta turma ainda.
              </div>
            `;
          } else {
            alunosHtml = t.alunos.map(al => {
              let tel = (al.telefone || '').replace(/\D/g, '');
              if (!tel.startsWith('55') && tel) tel = '55' + tel;
              const waLink = tel ? `https://wa.me/${tel}` : '#';

              let badgePlano = '';
              if (al.plano && al.plano.includes('1x')) {
                const diaEscolhido = al.dia_semana_1x ? al.dia_semana_1x : 'Dia a definir';
                badgePlano = `<span style="font-size:11px; background:#f0fdf4; color:#15803d; padding:2px 7px; border-radius:5px; font-weight:700; border:0.5px solid #86efac; display:inline-flex; align-items:center; gap:4px;" title="Comparece 1x na semana"><i class="fa-regular fa-calendar-check" style="color:#16a34a;"></i> 1x na semana (${diaEscolhido})</span>`;
              } else {
                badgePlano = `<span style="font-size:10.5px; background:#e8f0eb; color:var(--shanti-primary); padding:2px 6px; border-radius:4px; font-weight:600; border:0.5px solid #cbd5e1;">2x na semana</span>`;
              }

              let statusAluno = '';
              if (al.status === 'inativo') {
                statusAluno = `<span style="font-size:10px; background:#f1f5f9; color:#64748b; padding:1px 5px; border-radius:4px;">Inativo</span>`;
              } else if (al.inadimplente) {
                statusAluno = `<span style="font-size:10px; background:#fee2e2; color:#b91c1c; padding:1px 5px; border-radius:4px; font-weight:700;">Mensalidade Pendente</span>`;
              }

              return `
                <div style="display:flex; justify-content:space-between; align-items:center; padding:5px 0; border-bottom:0.5px dashed rgba(0,0,0,0.06); font-size:12.5px;">
                  <div style="display:flex; align-items:center; gap:6px; flex-wrap:wrap;">
                    <i class="fa-regular fa-user" style="color:var(--shanti-primary); font-size:11px;"></i>
                    <span style="font-weight:600; color:var(--wa-text-primary); cursor:pointer;" class="link-aluno-detalhes" data-aluno-id="${al.id}">${al.nome}</span>
                    ${badgePlano}
                    ${statusAluno}
                  </div>
                  ${tel ? `
                    <a href="${waLink}" target="_blank" title="Conversar no WhatsApp" style="color:#25d366; font-size:14px; padding:2px 6px;">
                      <i class="fa-brands fa-whatsapp"></i>
                    </a>
                  ` : ''}
                </div>
              `;
            }).join('');
          }

          return `
            <div style="background:var(--shanti-sand); padding:12px 14px; border-radius:10px; border:0.5px solid var(--wa-border);">
              <div style="display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:6px;">
                <div>
                  <div style="font-weight:700; font-size:14px; color:var(--wa-text-primary);">${t.nome}</div>
                  <div style="font-size:12px; color:var(--wa-text-secondary);"><i class="fa-regular fa-clock"></i> ${t.dias_semana} às ${t.horario}</div>
                </div>
                <div>${statusBadge}</div>
              </div>

              <div style="background:#e2e8f0; border-radius:999px; height:8px; width:100%; overflow:hidden; margin:8px 0 6px 0;">
                <div style="background:${barColor}; width:${percent}%; height:100%; border-radius:999px; transition:width 0.4s ease;"></div>
              </div>
              <div style="display:flex; justify-content:space-between; font-size:11px; color:var(--wa-text-secondary); margin-bottom:10px;">
                <span><b>${total}</b> de <b>${cap}</b> alunos matriculados</span>
                <span style="font-weight:600;">${percent}% ocupada</span>
              </div>

              <div style="margin-top:8px; padding-top:6px; border-top:1px solid rgba(0,0,0,0.06);">
                <div style="font-size:11.5px; font-weight:700; color:var(--shanti-primary); margin-bottom:4px; display:flex; align-items:center; gap:5px;">
                  <i class="fa-solid fa-users"></i> Alunos Matriculados (${total}):
                </div>
                <div>${alunosHtml}</div>
              </div>
            </div>
          `;
        }).join('');

        containerTurmas.querySelectorAll('.link-aluno-detalhes').forEach(link => {
          link.addEventListener('click', () => {
            const alunoId = parseInt(link.dataset.alunoId);
            abrirDetalhesAluno(alunoId);
          });
        });
      }
    }

    // 2. Aniversariantes do Mês
    const listAniv = document.getElementById('list-aniversariantes');
    const badgeAniv = document.getElementById('badge-aniversariantes');
    if (badgeAniv) badgeAniv.textContent = (aniversariantes && aniversariantes.length) || 0;
    if (listAniv) {
      if (!aniversariantes || aniversariantes.length === 0) {
        listAniv.innerHTML = '<div style="font-size: 12px; color: var(--wa-text-secondary); text-align: center; padding: 8px;">Nenhum aniversariante neste mês 🎂</div>';
      } else {
        listAniv.innerHTML = aniversariantes.map(a => {
          let tel = (a.telefone || '').replace(/\D/g, '');
          if (!tel.startsWith('55') && tel) tel = '55' + tel;
          const msgParabens = encodeURIComponent(`Olá, ${a.nome}! 🎉🎂 Passando para te desejar um Feliz Aniversário repleto de paz, luz e harmonia! Muita gratidão por fazer parte da família Studio Shanti. Namastê! 🙏✨`);
          const waLink = a.link_whatsapp || `https://wa.me/${tel}?text=${msgParabens}`;
          const ehHojeBadge = a.e_hoje ? `<span style="background:#fdf2f8; color:#db2777; border:1px solid #f472b6; font-size:10.5px; font-weight:800; padding:2px 7px; border-radius:10px; margin-left:6px;">🎉 É HOJE!</span>` : '';

          return `
            <div class="wa-report-item" style="${a.e_hoje ? 'background:#fff1f2; border:1px solid #fda4af;' : ''}">
              <div class="wa-report-item-info">
                <span class="wa-report-item-title">🎂 ${a.nome} ${ehHojeBadge}</span>
                <span class="wa-report-item-sub">Dia ${a.dia} (${a.data_nascimento ? formatarDataBR(a.data_nascimento) : ''}) • ${a.plano || 'Yoga Regular'}</span>
              </div>
              <a href="${waLink}" target="_blank" class="wa-btn-sm-whatsapp" style="background: linear-gradient(135deg, #ec4899, #db2777);">
                <i class="fa-brands fa-whatsapp"></i> Parabéns
              </a>
            </div>
          `;
        }).join('');
      }
    }

    // 3. Alunos Ausentes (>10 dias sem aula)
    const listAus = document.getElementById('list-ausentes');
    const badgeAus = document.getElementById('badge-ausentes');
    if (badgeAus) badgeAus.textContent = (ausentes && ausentes.length) || 0;
    if (listAus) {
      if (!ausentes || ausentes.length === 0) {
        listAus.innerHTML = '<div style="font-size: 12px; color: var(--wa-text-secondary); text-align: center; padding: 8px;">Todos os alunos ativos estão frequentando! 🧘‍♀️</div>';
      } else {
        listAus.innerHTML = ausentes.map(au => {
          let tel = au.telefone.replace(/\D/g, '');
          if (!tel.startsWith('55')) tel = '55' + tel;
          const msgVolta = encodeURIComponent(`Olá, ${au.nome}! 🧘‍♀️ Sentimos sua falta nas aulas do Studio Shanti! Está tudo bem com você? Esperamos te ver no tapetinho em breve. Namastê! 🙏`);
          const waLink = `https://wa.me/${tel}?text=${msgVolta}`;

          return `
            <div class="wa-report-item">
              <div class="wa-report-item-info">
                <span class="wa-report-item-title">${au.nome}</span>
                <span class="wa-report-item-sub" style="color: #b45309; font-weight:600;">⚠️ ${au.dias_ausente} dias sem praticar • ${au.plano}</span>
              </div>
              <a href="${waLink}" target="_blank" class="wa-btn-sm-whatsapp" style="background: linear-gradient(135deg, #f59e0b, #d97706);">
                <i class="fa-brands fa-whatsapp"></i> Convidar
              </a>
            </div>
          `;
        }).join('');
      }
    }

    // 4. Quantitativo Geral de Alunos
    const elAtivos = document.getElementById('stat-alunos-ativos');
    if (elAtivos) elAtivos.textContent = quant.alunos_ativos;
    const elInad = document.getElementById('stat-alunos-inadimplentes');
    if (elInad) elInad.textContent = quant.inadimplentes_mes;
    const elNovos = document.getElementById('stat-novos-matriculados');
    if (elNovos) elNovos.textContent = quant.novos_matriculados_mes;
    const elInativos = document.getElementById('stat-alunos-inativos');
    if (elInativos) elInativos.textContent = quant.alunos_inativos;

  } catch (err) {
    console.error('Erro ao carregar dados do estúdio:', err);
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
    if (state.configuracoes.valor_plano_1x) {
      const el1x = document.getElementById('cfg-valor-plano-1x');
      if (el1x) el1x.value = state.configuracoes.valor_plano_1x;
    }
    if (state.configuracoes.valor_plano_2x) {
      const el2x = document.getElementById('cfg-valor-plano-2x');
      if (el2x) el2x.value = state.configuracoes.valor_plano_2x;
    }

    // Inicializar escala do ícone salva
    if (state.configuracoes.icone_escala) {
      const pct = Math.round(parseFloat(state.configuracoes.icone_escala) * 100);
      const iconScaleInput = document.getElementById('cfg-icon-scale');
      const iconScaleVal = document.getElementById('cfg-icon-scale-val');
      if (iconScaleInput) iconScaleInput.value = pct;
      if (iconScaleVal) iconScaleVal.textContent = `${pct}%`;
      const pSq = document.getElementById('img-preview-square');
      const pRd = document.getElementById('img-preview-round');
      const pSp = document.getElementById('img-preview-splash');
      if (pSq) pSq.style.width = `${pct}%`;
      if (pRd) pRd.style.width = `${pct}%`;
      if (pSp) pSp.style.width = `${Math.round(pct * 0.85)}%`;
    }
  } catch (err) {
    console.error('Erro ao carregar configurações:', err);
  }
}

function setupSettings() {
  // 1. Salvar Configurações Gerais
  document.getElementById('btn-salvar-configuracoes').addEventListener('click', async () => {
    const configs = {
      nome_studio: document.getElementById('cfg-nome-studio').value.trim() || 'Studio Shanti',
      chave_pix: document.getElementById('cfg-chave-pix').value.trim(),
      tipo_chave_pix: document.getElementById('cfg-tipo-pix').value,
      gemini_api_key: document.getElementById('cfg-gemini-key').value.trim(),
      valor_plano_1x: document.getElementById('cfg-valor-plano-1x')?.value.trim() || '120.00',
      valor_plano_2x: document.getElementById('cfg-valor-plano-2x')?.value.trim() || '150.00'
    };

    try {
      await fetch('/api/configuracoes', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ configs })
      });
      state.configuracoes = { ...state.configuracoes, ...configs };
      document.getElementById('header-studio-name').textContent = configs.nome_studio;
      showToast('Configurações salvas com sucesso!');
    } catch (err) {
      alert('Erro ao salvar configurações.');
    }
  });

  // 2. Controles de Ícone e Splash Screen (Fase 1)
  const iconScaleInput = document.getElementById('cfg-icon-scale');
  const iconScaleVal = document.getElementById('cfg-icon-scale-val');
  const previewSquareImg = document.getElementById('img-preview-square');
  const previewRoundImg = document.getElementById('img-preview-round');
  const previewSplashImg = document.getElementById('img-preview-splash');
  const iconFileInput = document.getElementById('cfg-icon-file');
  const btnSalvarIcone = document.getElementById('btn-salvar-icone');

  const aplicarEscalaPreviews = (val) => {
    if (iconScaleVal) iconScaleVal.textContent = `${val}%`;
    if (previewSquareImg) previewSquareImg.style.width = `${val}%`;
    if (previewRoundImg) previewRoundImg.style.width = `${val}%`;
    if (previewSplashImg) previewSplashImg.style.width = `${Math.round(val * 0.85)}%`;
  };

  if (iconScaleInput) {
    iconScaleInput.addEventListener('input', (e) => {
      aplicarEscalaPreviews(e.target.value);
    });
  }

  if (iconFileInput) {
    iconFileInput.addEventListener('change', (e) => {
      const file = e.target.files && e.target.files[0];
      if (file) {
        const objectUrl = URL.createObjectURL(file);
        if (previewSquareImg) previewSquareImg.src = objectUrl;
        if (previewRoundImg) previewRoundImg.src = objectUrl;
        if (previewSplashImg) previewSplashImg.src = objectUrl;
      }
    });
  }

  if (btnSalvarIcone) {
    btnSalvarIcone.addEventListener('click', async () => {
      const scaleVal = iconScaleInput ? parseFloat(iconScaleInput.value) / 100 : 0.75;
      const file = iconFileInput && iconFileInput.files && iconFileInput.files[0];

      const formData = new FormData();
      formData.append('escala', scaleVal.toFixed(2));
      if (file) {
        formData.append('imagem', file);
      }

      btnSalvarIcone.disabled = true;
      const originalHtml = btnSalvarIcone.innerHTML;
      btnSalvarIcone.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Processando Ícones...';

      try {
        const res = await fetch('/api/configuracoes/icone', {
          method: 'POST',
          body: formData
        });
        const data = await res.json();
        if (res.ok) {
          showToast(data.mensagem || 'Ícones e Splash Screen atualizados com sucesso!');
          const v = data.versao || Date.now();

          // Atualizar imagens em tempo real no app
          const targets = [
            '#img-preview-square', '#img-preview-round', '#img-preview-splash',
            '#cfg-logo-preview', '.wa-avatar-img', '.pwa-splash-logo'
          ];
          targets.forEach(sel => {
            document.querySelectorAll(sel).forEach(el => {
              el.src = `/icons/icon-192.png?v=${v}`;
            });
          });

          // Atualizar favicon e apple-touch-icon
          const favicon = document.querySelector('link[rel="icon"]');
          if (favicon) favicon.href = `/favicon.png?v=${v}`;
          const appleIcon = document.querySelector('link[rel="apple-touch-icon"]');
          if (appleIcon) appleIcon.href = `/icons/icon-192.png?v=${v}`;
        } else {
          alert(data.detail || 'Erro ao processar ícone.');
        }
      } catch (err) {
        console.error('Erro ao salvar ícone:', err);
        alert('Erro ao comunicar com o servidor.');
      } finally {
        btnSalvarIcone.disabled = false;
        btnSalvarIcone.innerHTML = originalHtml;
      }
    });
  }
}
