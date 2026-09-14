/**
 * Shanti Studio de Yoga - WhatsApp Assistant Luxe PWA
 * Frontend JavaScript completo para chat, áudio, controle de alunos, relatórios e WhatsApp.
 */

// Estado global da aplicação
const state = {
  alunos: [],
  turmas: [],
  contratos: [],
  alunoSelecionado: null,
  isRecording: false,
  mediaRecorder: null,
  audioChunks: [],
  recordInterval: null,
  recordSeconds: 0,
  speechRecognition: null,
  currentFilter: 'todos',
  currentContractFilter: 'todos',
  configuracoes: {},
  liveVoiceMode: false,
  isSpeaking: false,
  currentUser: null,
  authToken: null,
  calendario: {
    ano: new Date().getFullYear(),
    mes: new Date().getMonth() + 1,
    diaSelecionado: new Date().toISOString().slice(0, 10),
    dadosMes: null,
    dadosDia: null,
    retencao: []
  }
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
    setupCalendario();
    setupPWAInstall();
    await setupAuth();
    
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

    // Se estiver autenticado, carregar os dados
    if (state.authToken) {
      await carregarConfiguracoes();
      await atualizarTudo();
    }

    // Sincronização automática em tempo real entre celulares (Bruno e Natália)
    window.addEventListener('focus', () => {
      if (state.authToken) atualizarTudo();
    });
    document.addEventListener('visibilitychange', () => {
      if (document.visibilityState === 'visible' && state.authToken) {
        atualizarTudo();
      }
    });
    // Polling contínuo em segundo plano a cada 30 segundos enquanto o app estiver aberto
    setInterval(() => {
      if (document.visibilityState === 'visible' && state.authToken) {
        atualizarTudo();
      }
    }, 30000);
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
  await carregarContratos();
  await carregarRetencaoAusentes();
  const screenCal = document.getElementById('screen-calendario');
  if (screenCal && screenCal.classList.contains('active')) {
    await carregarCalendario();
  }
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
      if (tab.dataset.tab === 'calendario') carregarCalendario();
      if (tab.dataset.tab === 'financeiro') carregarFinanceiro();
      if (tab.dataset.tab === 'estudio') carregarEstudio();
      if (tab.dataset.tab === 'contratos') carregarContratos();
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

  // Botão de Logout no Header
  const btnHeaderLogout = document.getElementById('btn-header-logout');
  if (btnHeaderLogout) {
    btnHeaderLogout.addEventListener('click', () => {
      confirmarLogout();
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
  carregarDiagnostico();
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

function navegarParaAba(nomeAba) {
  // Se estiver na tela de Ajustes, fecha e desativa primeiro
  const screenAjustes = document.getElementById('screen-ajustes');
  if (screenAjustes && screenAjustes.classList.contains('active')) {
    screenAjustes.classList.remove('active');
  }

  // Tenta clicar no botão da aba correspondente
  const tabBtn = document.querySelector(`.wa-tab-btn[data-tab="${nomeAba}"]`);
  if (tabBtn) {
    tabBtn.click();
    window.scrollTo({ top: 0, behavior: 'smooth' });
  } else {
    document.querySelectorAll('.wa-screen').forEach(s => s.classList.remove('active'));
    document.querySelectorAll('.wa-tab-btn').forEach(t => t.classList.remove('active'));
    const targetScreen = document.getElementById(`screen-${nomeAba}`);
    if (targetScreen) targetScreen.classList.add('active');
    if (nomeAba === 'financeiro') carregarFinanceiro();
    else if (nomeAba === 'calendario') carregarCalendario();
    else if (nomeAba === 'alunos') carregarAlunos();
    else if (nomeAba === 'estudio') carregarEstudio();
    else if (nomeAba === 'contratos') carregarContratos();
  }
}
window.navegarParaAba = navegarParaAba;

// =============================================================================
// SISTEMA DE AUTENTICAÇÃO & CONTROLE DE ACESSO (STUDIO SHANTI)
// =============================================================================

// Interceptar todas as requisições fetch para rotas /api/ e injetar token Bearer
(function interceptarFetchComAuth() {
  const _originalFetch = window.fetch;
  window.fetch = function(resource, init = {}) {
    if (typeof resource === 'string' && resource.startsWith('/api/') && state.authToken) {
      init.headers = init.headers || {};
      if (init.headers instanceof Headers) {
        if (!init.headers.has('Authorization')) {
          init.headers.set('Authorization', 'Bearer ' + state.authToken);
        }
      } else if (Array.isArray(init.headers)) {
        init.headers.push(['Authorization', 'Bearer ' + state.authToken]);
      } else {
        if (!init.headers['Authorization']) {
          init.headers['Authorization'] = 'Bearer ' + state.authToken;
        }
      }
    }
    return _originalFetch(resource, init);
  };
})();

async function setupAuth() {
  // 1. Verificar se há sessão salva no localStorage (lembrar de mim) ou sessionStorage
  const savedToken = localStorage.getItem('shanti_auth_token') || sessionStorage.getItem('shanti_auth_token');
  const savedUserStr = localStorage.getItem('shanti_auth_user') || sessionStorage.getItem('shanti_auth_user');

  if (savedToken && savedUserStr) {
    try {
      const user = JSON.parse(savedUserStr);
      state.authToken = savedToken;
      state.currentUser = user;
      atualizarUsuarioUI(user);
      ocultarTelaLogin();

      // Validação assíncrona em segundo plano
      fetch('/api/auth/verificar')
        .then(res => res.json())
        .then(data => {
          if (!data.autenticado) {
            console.warn('Sessão expirada ou inválida. Solicitando novo login.');
            fazerLogout('Sua sessão expirou. Por favor, entre novamente.');
          } else if (data.user) {
            state.currentUser = data.user;
            atualizarUsuarioUI(data.user);
          }
        })
        .catch(err => {
          console.warn('Verificação offline da sessão:', err);
        });
    } catch (e) {
      console.error('Erro ao restaurar sessão salva:', e);
      exibirTelaLogin();
    }
  } else {
    exibirTelaLogin();
  }

  // 2. Carregar perfis do backend para exibição interativa
  await carregarPerfisLogin();

  // 3. Configurar eventos da tela de login
  configurarEventosLogin();
}

function atualizarUsuarioUI(user) {
  if (!user) return;

  const headerStatus = document.getElementById('header-user-status');
  const isBruno = user.username && user.username.toLowerCase() === 'bruno';
  const avatarEmoji = isBruno ? '💻' : '🧘‍♀️';
  const cargoTexto = isBruno ? 'Desenvolvedor Master' : 'Gestão & Studio Shanti';

  if (headerStatus) {
    headerStatus.innerHTML = `<span class="wa-user-badge-header">${avatarEmoji} ${user.nome}</span>`;
  }

  // Atualizar card de segurança na tela de Ajustes
  const cfgNome = document.getElementById('cfg-user-nome');
  if (cfgNome) cfgNome.textContent = user.nome;

  const cfgTitulo = document.getElementById('cfg-user-titulo');
  if (cfgTitulo) cfgTitulo.textContent = cargoTexto;

  const cfgUsername = document.getElementById('cfg-user-username');
  if (cfgUsername) cfgUsername.textContent = `Usuário: ${user.username}`;

  const cfgAvatar = document.getElementById('cfg-user-avatar');
  if (cfgAvatar) cfgAvatar.textContent = avatarEmoji;

  const badgeRole = document.getElementById('badge-user-role');
  if (badgeRole) {
    badgeRole.textContent = user.role === 'dev' ? 'Dev Master' : 'Administradora';
  }
}

function exibirTelaLogin() {
  const loginScreen = document.getElementById('pwa-login-screen');
  if (loginScreen) {
    loginScreen.style.display = 'flex';
  }
  const appContainer = document.getElementById('app-container');
  if (appContainer) {
    appContainer.style.filter = 'blur(4px)';
    appContainer.style.pointerEvents = 'none';
  }
}

function ocultarTelaLogin() {
  const loginScreen = document.getElementById('pwa-login-screen');
  if (loginScreen) {
    loginScreen.style.display = 'none';
  }
  const appContainer = document.getElementById('app-container');
  if (appContainer) {
    appContainer.style.filter = 'none';
    appContainer.style.pointerEvents = 'auto';
  }
}

async function carregarPerfisLogin() {
  try {
    const res = await fetch('/api/auth/perfis');
    if (!res.ok) return;
    const perfis = await res.json();
    const container = document.getElementById('pwa-profile-selector');
    if (!container || !perfis || perfis.length === 0) return;

    container.innerHTML = perfis.map((p, idx) => {
      const isActive = idx === 0 ? 'active' : '';
      return `
        <button type="button" class="pwa-profile-btn ${isActive}" data-username="${p.username}" id="btn-perfil-${p.username}">
          <div class="pwa-profile-avatar">${p.avatar || '👤'}</div>
          <div class="pwa-profile-info">
            <span class="pwa-profile-name">${p.nome}</span>
            <span class="pwa-profile-desc">${p.titulo || 'Studio Shanti'}</span>
          </div>
          <div class="pwa-profile-check"><i class="fa-solid fa-check"></i></div>
        </button>
      `;
    }).join('');

    // Reanexar cliques aos botões de perfil
    anexarCliquesPerfis();
  } catch (err) {
    console.warn('Erro ao carregar perfis de login:', err);
  }
}

function anexarCliquesPerfis() {
  const profileBtns = document.querySelectorAll('.pwa-profile-btn');
  const inputUser = document.getElementById('login-username');
  const inputSenha = document.getElementById('login-senha');

  profileBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      profileBtns.forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      const uname = btn.getAttribute('data-username');
      if (inputUser) inputUser.value = uname;
      if (inputSenha) {
        inputSenha.value = '';
        inputSenha.focus();
      }
      const errBox = document.getElementById('login-error-box');
      if (errBox) errBox.style.display = 'none';
    });
  });
}

function configurarEventosLogin() {
  anexarCliquesPerfis();

  // Alternar visualização da senha
  const btnToggleEye = document.getElementById('btn-toggle-login-senha');
  const inputSenha = document.getElementById('login-senha');
  const iconEye = document.getElementById('icon-toggle-login-senha');

  if (btnToggleEye && inputSenha) {
    btnToggleEye.addEventListener('click', () => {
      if (inputSenha.type === 'password') {
        inputSenha.type = 'text';
        if (iconEye) {
          iconEye.classList.remove('fa-eye');
          iconEye.classList.add('fa-eye-slash');
        }
      } else {
        inputSenha.type = 'password';
        if (iconEye) {
          iconEye.classList.remove('fa-eye-slash');
          iconEye.classList.add('fa-eye');
        }
      }
    });
  }

  // Submissão do Formulário de Login
  const formLogin = document.getElementById('form-login-pwa');
  if (formLogin) {
    formLogin.addEventListener('submit', async (e) => {
      e.preventDefault();
      await processarLogin();
    });
  }

  // Botão de Logout no Header e na tela de Ajustes
  const btnHeaderLogout = document.getElementById('btn-header-logout');
  if (btnHeaderLogout) {
    btnHeaderLogout.addEventListener('click', () => {
      confirmarLogout();
    });
  }

  const btnLogoutAjustes = document.getElementById('btn-logout-ajustes');
  if (btnLogoutAjustes) {
    btnLogoutAjustes.addEventListener('click', () => {
      confirmarLogout();
    });
  }

  // Modal Alterar Senha
  const btnAbrirModalSenha = document.getElementById('btn-abrir-modal-senha');
  if (btnAbrirModalSenha) {
    btnAbrirModalSenha.addEventListener('click', () => {
      abrirModalAlterarSenha();
    });
  }

  const formAlterarSenha = document.getElementById('form-alterar-senha');
  if (formAlterarSenha) {
    formAlterarSenha.addEventListener('submit', async (e) => {
      e.preventDefault();
      await processarAlteracaoSenha();
    });
  }
}

async function processarLogin() {
  const username = document.getElementById('login-username')?.value || 'natalia';
  const senha = document.getElementById('login-senha')?.value || '';
  const lembrar = document.getElementById('login-lembrar')?.checked !== false;

  const btnSubmit = document.getElementById('btn-submit-login');
  const btnSpinner = document.getElementById('btn-login-spinner');
  const btnText = document.getElementById('btn-login-text');
  const btnArrow = document.getElementById('btn-login-arrow');
  const errBox = document.getElementById('login-error-box');
  const errText = document.getElementById('login-error-text');

  if (!senha) {
    if (errBox && errText) {
      errText.textContent = 'Por favor, digite sua senha de acesso.';
      errBox.style.display = 'flex';
    }
    return;
  }

  // Estado de carregando
  if (btnSubmit) btnSubmit.disabled = true;
  if (btnSpinner) btnSpinner.style.display = 'inline-block';
  if (btnArrow) btnArrow.style.display = 'none';
  if (btnText) btnText.textContent = 'Autenticando...';
  if (errBox) errBox.style.display = 'none';

  try {
    const res = await fetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, senha, lembrar })
    });

    const data = await res.json();

    if (!res.ok || !data.sucesso) {
      const msg = data.detail || 'Senha ou usuário incorretos. Tente novamente.';
      if (errBox && errText) {
        errText.textContent = msg;
        errBox.style.display = 'flex';
      }
      const inputSenha = document.getElementById('login-senha');
      if (inputSenha) {
        inputSenha.select();
        inputSenha.focus();
      }
      return;
    }

    // Sucesso no Login!
    state.authToken = data.token;
    state.currentUser = data.user;

    // Salvar na persistência de acordo com a escolha "Lembrar de mim"
    if (lembrar) {
      localStorage.setItem('shanti_auth_token', data.token);
      localStorage.setItem('shanti_auth_user', JSON.stringify(data.user));
    } else {
      sessionStorage.setItem('shanti_auth_token', data.token);
      sessionStorage.setItem('shanti_auth_user', JSON.stringify(data.user));
    }

    atualizarUsuarioUI(data.user);
    ocultarTelaLogin();

    // Mensagem de boas-vindas
    showToast(`Bem-vindo(a), ${data.user.nome}! 🙏`);

    // Carregar dados atualizados do Studio
    await carregarConfiguracoes();
    await atualizarTudo();

  } catch (err) {
    console.error('Erro na requisição de login:', err);
    if (errBox && errText) {
      errText.textContent = 'Erro de conexão com o servidor. Verifique sua internet.';
      errBox.style.display = 'flex';
    }
  } finally {
    if (btnSubmit) btnSubmit.disabled = false;
    if (btnSpinner) btnSpinner.style.display = 'none';
    if (btnArrow) btnArrow.style.display = 'inline-block';
    if (btnText) btnText.textContent = 'Entrar no Studio';
  }
}

function confirmarLogout() {
  const nome = state.currentUser ? state.currentUser.nome : 'Usuário';
  if (confirm(`Deseja realmente sair da conta de ${nome}? Você precisará da senha para entrar novamente.`)) {
    fazerLogout();
  }
}

function fazerLogout(mensagem) {
  localStorage.removeItem('shanti_auth_token');
  localStorage.removeItem('shanti_auth_user');
  sessionStorage.removeItem('shanti_auth_token');
  sessionStorage.removeItem('shanti_auth_user');

  state.authToken = null;
  state.currentUser = null;

  const headerStatus = document.getElementById('header-user-status');
  if (headerStatus) {
    headerStatus.textContent = 'Yoga Studio Management';
  }

  const inputSenha = document.getElementById('login-senha');
  if (inputSenha) inputSenha.value = '';

  const errBox = document.getElementById('login-error-box');
  if (errBox) errBox.style.display = 'none';

  exibirTelaLogin();

  if (mensagem) {
    showToast(mensagem);
  } else {
    showToast('Você saiu da sua conta.');
  }
}
window.fazerLogout = fazerLogout;

function abrirModalAlterarSenha() {
  const user = state.currentUser || { username: 'natalia', nome: 'Natalia Garufe' };
  const elUser = document.getElementById('modal-senha-username');
  if (elUser) elUser.textContent = `${user.nome} (${user.username})`;

  const inputAtual = document.getElementById('input-senha-atual');
  const inputNova = document.getElementById('input-nova-senha');
  const inputConf = document.getElementById('input-confirma-nova-senha');
  const errBox = document.getElementById('modal-senha-erro');

  if (inputAtual) inputAtual.value = '';
  if (inputNova) inputNova.value = '';
  if (inputConf) inputConf.value = '';
  if (errBox) errBox.style.display = 'none';

  const modal = document.getElementById('modal-alterar-senha');
  if (modal) modal.classList.add('active');
}

async function processarAlteracaoSenha() {
  const user = state.currentUser || { username: 'natalia' };
  const senhaAtual = document.getElementById('input-senha-atual')?.value || '';
  const novaSenha = document.getElementById('input-nova-senha')?.value || '';
  const confirmaNovaSenha = document.getElementById('input-confirma-nova-senha')?.value || '';
  const errBox = document.getElementById('modal-senha-erro');

  if (!senhaAtual) {
    if (errBox) { errBox.textContent = 'Informe a sua senha atual.'; errBox.style.display = 'block'; }
    return;
  }
  if (!novaSenha || novaSenha.length < 4) {
    if (errBox) { errBox.textContent = 'A nova senha deve ter no mínimo 4 dígitos.'; errBox.style.display = 'block'; }
    return;
  }
  if (novaSenha !== confirmaNovaSenha) {
    if (errBox) { errBox.textContent = 'A nova senha e a confirmação não coincidem.'; errBox.style.display = 'block'; }
    return;
  }

  const btnSalvar = document.getElementById('btn-salvar-nova-senha');
  if (btnSalvar) {
    btnSalvar.disabled = true;
    btnSalvar.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Gravando...';
  }

  try {
    const res = await fetch('/api/auth/alterar-senha', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        username: user.username,
        senha_atual: senhaAtual,
        nova_senha: novaSenha
      })
    });

    const data = await res.json();

    if (!res.ok || !data.sucesso) {
      if (errBox) {
        errBox.textContent = data.detail || 'Erro ao alterar senha. Verifique a senha atual digitada.';
        errBox.style.display = 'block';
      }
      return;
    }

    // Sucesso! Atualizar token
    if (data.token) {
      state.authToken = data.token;
      if (localStorage.getItem('shanti_auth_token')) {
        localStorage.setItem('shanti_auth_token', data.token);
      } else if (sessionStorage.getItem('shanti_auth_token')) {
        sessionStorage.setItem('shanti_auth_token', data.token);
      }
    }

    const modal = document.getElementById('modal-alterar-senha');
    if (modal) modal.classList.remove('active');

    showToast('Senha alterada com sucesso! ✨');
  } catch (err) {
    console.error('Erro ao alterar senha:', err);
    if (errBox) {
      errBox.textContent = 'Erro de comunicação com o servidor.';
      errBox.style.display = 'block';
    }
  } finally {
    if (btnSalvar) {
      btnSalvar.disabled = false;
      btnSalvar.innerHTML = '<i class="fa-solid fa-check"></i> Salvar Senha';
    }
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

  btnSend.addEventListener('click', () => enviarMensagemTexto());

  // Atalhos de Acesso Rápido na Tela Inicial (Fase 5)
  const shortcutChips = document.querySelectorAll('.wa-shortcut-chip');
  shortcutChips.forEach(chip => {
    chip.addEventListener('click', async () => {
      const query = chip.dataset.query;
      if (!query) return;

      chip.classList.add('clicked');
      setTimeout(() => chip.classList.remove('clicked'), 350);

      // Se o usuário estiver em outra aba, voltar para a aba Conversas
      const activeTab = document.querySelector('.wa-tab-btn.active');
      if (activeTab && activeTab.dataset.tab !== 'chat') {
        const chatTab = document.querySelector('.wa-tab-btn[data-tab="chat"]');
        if (chatTab) chatTab.click();
      }

      await enviarMensagemTexto(query);
    });
  });
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
  
  // Se for mensagem da IA, exibir o avatar quadrado com borda suave do Studio Shanti
  if (remetente === 'bot') {
    htmlInner += `<img src="/icons/lotus-brand.png?v=1" alt="Studio Shanti" class="wa-msg-avatar" style="border-radius: 8px; border: 1px solid var(--shanti-sand-border); background: #FFFFFF; padding: 2px;">`;
  }

  htmlInner += `
    <div class="wa-message ${remetente}">
      <div class="wa-message-content">${formattedText}</div>
  `;

  // Renderizar Cards de Ação Extras
  if (dadosExtras) {
    // 1. Recibo individual de pagamento
    if (!Array.isArray(dadosExtras) && (dadosExtras.tipo === 'recibo' || dadosExtras.recibo || dadosExtras.texto_recibo)) {
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
    // 1b. Lista de Pagamentos / Recibos do Mês (Fase 5)
    else if (Array.isArray(dadosExtras) && dadosExtras.length > 0 && (dadosExtras[0].texto_recibo !== undefined || dadosExtras[0].pagamento_id !== undefined)) {
      htmlInner += `<div style="margin-top: 10px; display: flex; flex-direction: column; gap: 8px;">`;
      dadosExtras.forEach(r => {
        htmlInner += `
          <div class="wa-action-card" style="border-left-color: var(--wa-success);">
            <div class="wa-action-card-header">
              <span class="wa-action-card-name"><i class="fa-solid fa-circle-check" style="color:var(--wa-success);"></i> ${r.aluno || r.aluno_nome}</span>
              <span class="wa-action-card-val" style="color:var(--wa-success);">R$ ${(r.valor || 0).toFixed(2)}</span>
            </div>
            <div class="wa-action-card-sub" style="color: var(--wa-text-secondary);">
              • ${r.plano || '2x na semana'}${r.dia_semana_1x ? ` (${r.dia_semana_1x})` : ''} • Mês ${r.mes_referencia} (${r.forma_pagamento || 'PIX'})
            </div>
            ${r.link_whatsapp ? `
              <a href="${r.link_whatsapp}" target="_blank" class="wa-action-btn-whatsapp" style="background: linear-gradient(135deg, #10b981, #059669);">
                <i class="fa-brands fa-whatsapp"></i> Reenviar Comprovante no WhatsApp
              </a>
            ` : ''}
          </div>
        `;
      });
      htmlInner += `</div>`;
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
    // 4. Lista de Despesas e Contas do Estúdio (Fase 3 & Atalho Despesas & Saldo)
    else if (Array.isArray(dadosExtras) && dadosExtras.length > 0 && (dadosExtras[0].descricao !== undefined || dadosExtras[0].categoria !== undefined || dadosExtras[0].vazio !== undefined)) {
      htmlInner += `<div style="margin-top: 10px; display: flex; flex-direction: column; gap: 8px;">`;
      const despesasReais = dadosExtras.filter(d => !d.vazio && d.descricao);
      if (despesasReais.length > 0) {
        despesasReais.forEach(d => {
          const isPaga = d.status === 'pago';
          const stLabel = isPaga ? '<span style="color:#10b981; font-weight:700;">✓ Paga</span>' : '<span style="color:#ef4444; font-weight:700;">⚠️ Vencimento Pendente</span>';
          const vencStr = d.data_vencimento || d.data || '';
          const dtFmt = vencStr ? formatarDataBR(vencStr.split(' ')[0]) : '';
          htmlInner += `
            <div class="wa-action-card" style="border-left-color: ${isPaga ? '#10b981' : '#ef4444'};">
              <div class="wa-action-card-header">
                <span class="wa-action-card-name">💸 ${d.descricao || 'Despesa'}</span>
                <span class="wa-action-card-val" style="color: ${isPaga ? '#10b981' : '#ef4444'};">R$ ${(d.valor || 0).toFixed(2)}</span>
              </div>
              <div class="wa-action-card-sub" style="color: var(--wa-text-secondary);">
                • Categoria: ${d.categoria || 'Geral'} • Vencimento: ${dtFmt} • ${stLabel}
              </div>
              <div style="display: flex; gap: 6px; margin-top: 8px;">
                ${!isPaga ? `
                  <button type="button" class="wa-action-btn-whatsapp" onclick="marcarDespesaPagaChat(${d.id})" style="background: linear-gradient(135deg, #10b981, #059669); flex: 1; border: none; cursor: pointer; border-radius: 20px;">
                    <i class="fa-solid fa-check"></i> Marcar Paga
                  </button>
                ` : ''}
                <button type="button" class="wa-action-btn-whatsapp" onclick="navegarParaAba('financeiro')" style="background: var(--shanti-card-bg); border: 1px solid var(--shanti-sand-border); color: var(--shanti-terracotta); flex: 1; cursor: pointer; border-radius: 20px; font-weight: 600;">
                  <i class="fa-solid fa-wallet"></i> Ver no Financeiro
                </button>
              </div>
            </div>
          `;
        });
      }
      // Botão geral para abrir a aba Financeiro
      htmlInner += `
        <button type="button" class="wa-action-btn-whatsapp" onclick="navegarParaAba('financeiro')" style="background: var(--shanti-terracotta); border: none; color: #ffffff; width: 100%; cursor: pointer; display: flex; align-items: center; justify-content: center; gap: 8px; padding: 10px 14px; border-radius: 20px; font-weight: 600; box-shadow: 0 2px 8px rgba(177, 106, 76, 0.25);">
          <i class="fa-solid fa-wallet"></i> Abrir Painel Financeiro
        </button>
      </div>`;
    }
    // 4b. Relatório / Balanço Financeiro Geral
    else if (!Array.isArray(dadosExtras) && (dadosExtras.faturamento_realizado !== undefined || dadosExtras.total_despesas !== undefined)) {
      htmlInner += `
        <div style="margin-top: 10px;">
          <button type="button" class="wa-action-btn-whatsapp" onclick="navegarParaAba('financeiro')" style="background: var(--shanti-terracotta); border: none; color: #ffffff; width: 100%; cursor: pointer; display: flex; align-items: center; justify-content: center; gap: 8px; padding: 10px 14px; border-radius: 20px; font-weight: 600; box-shadow: 0 2px 8px rgba(177, 106, 76, 0.25);">
            <i class="fa-solid fa-wallet"></i> Abrir Painel Financeiro Completo
          </button>
        </div>
      `;
    }
    // 5. Lista de Matrículas Pendentes de Aprovação / Pagamento ("Entrou, Pagou")
    else if (Array.isArray(dadosExtras) && dadosExtras.length > 0 && (dadosExtras[0].aprovacao_pagamento === 'pendente' || (dadosExtras[0].plano && dadosExtras[0].valor_mensalidade && !dadosExtras[0].dias_atraso))) {
      htmlInner += `<div style="margin-top: 10px; display: flex; flex-direction: column; gap: 8px;">`;
      dadosExtras.forEach(al => {
        const dtMat = al.data_matricula ? formatarDataBR(al.data_matricula.split(' ')[0]) : '';
        htmlInner += `
          <div class="wa-action-card" style="border-left-color: #f59e0b; background: #fffdfa;">
            <div class="wa-action-card-header">
              <span class="wa-action-card-name">🟡 ${al.nome}</span>
              <span class="wa-action-card-val" style="color: #b45309;">R$ ${(al.valor_mensalidade || 0).toFixed(2)}</span>
            </div>
            <div class="wa-action-card-sub" style="color: var(--wa-text-secondary);">
              • Plano: ${al.plano || 'Yoga'}${dtMat ? ' • Cadastrado em: ' + dtMat : ''} • Tel: ${al.telefone || '-'}
            </div>
            <div style="display: flex; flex-direction: column; gap: 6px; margin-top: 8px;">
              <button type="button" class="wa-action-btn-whatsapp" onclick="aprovarMatriculaChat(${al.id}, '${al.nome.replace(/'/g, "\\'")}')" style="background: linear-gradient(135deg, #16a34a, #15803d); font-weight:700; border: none; cursor: pointer; border-radius: 20px;">
                <i class="fa-solid fa-circle-check"></i> Aprovar Matrícula (Entrou, Pagou)
              </button>
              ${al.link_whatsapp ? `
                <a href="${al.link_whatsapp}" target="_blank" class="wa-action-btn-whatsapp" style="background: #25D366; border: none; color: #ffffff; font-weight: 600; border-radius: 20px;">
                  <i class="fa-brands fa-whatsapp"></i> Confirmar PIX no WhatsApp
                </a>
              ` : ''}
            </div>
          </div>
        `;
      });
      htmlInner += `</div>`;
    }
    // 6. Lista Padrão de Cobrança de Atrasados
    else if (Array.isArray(dadosExtras) && dadosExtras.length > 0 && dadosExtras[0].nome) {
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

window.aprovarMatriculaChat = async function(alunoId, alunoNome) {
  try {
    const res = await fetch(`/api/alunos/${alunoId}/aprovar-pagamento`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ forma_pagamento: 'PIX' })
    });
    const data = await res.json();
    if (data.sucesso) {
      showToast(`✓ Matrícula de ${alunoNome} aprovada com sucesso!`);
      await atualizarTudo();
      adicionarMensagem(`✅ *Matrícula e 1ª Mensalidade Aprovadas com Sucesso!*\n\n• Aluno: *${alunoNome}*\n• Valor: R$ ${(data.valor || 150).toFixed(2)} (PIX)\n• Status da Matrícula: Regularizada ('Entrou, Pagou')\n\nA primeira mensalidade foi lançada no financeiro e o aluno já está 100% ativo para as práticas! Namastê! 🙏`, 'bot');
    } else {
      showToast('Erro ao aprovar matrícula: ' + (data.detail || 'Tente novamente'));
    }
  } catch (err) {
    showToast('Erro de conexão ao aprovar matrícula.');
  }
};

window.marcarDespesaPagaChat = async function(despesaId) {
  try {
    const res = await fetch(`/api/despesas/${despesaId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status: 'pago' })
    });
    if (res.ok) {
      showToast('✓ Despesa marcada como paga!');
      await atualizarTudo();
      adicionarMensagem('✅ Despesa atualizada para *PAGA* no controle financeiro com sucesso!', 'bot');
    } else {
      showToast('Erro ao atualizar status da despesa.');
    }
  } catch (e) {
    showToast('Erro ao atualizar despesa.');
  }
};

function criarIndicadorDigitacao(msgInicial = 'Consultando o estúdio... 🧘‍♀️') {
  const container = document.getElementById('chat-messages');
  const typingRow = document.createElement('div');
  typingRow.className = 'wa-message-row bot wa-typing-row';
  typingRow.innerHTML = `
    <img src="/icons/lotus-brand.png?v=1" alt="Studio Shanti" class="wa-msg-avatar" style="border-radius: 8px; border: 1px solid var(--shanti-sand-border); background: #FFFFFF; padding: 2px;">
    <div class="wa-message bot">
      <div class="wa-message-content" style="color:var(--shanti-stone);"><span class="typing-text">${msgInicial}</span></div>
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
      textEl.innerHTML = '✨ Processando com a IA Groq (Llama / Qwen)... 🧘‍♀️';
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

async function enviarMensagemTexto(textoCustomizado = null) {
  const input = document.getElementById('chat-input');
  const texto = (typeof textoCustomizado === 'string' && textoCustomizado.trim()) 
    ? textoCustomizado.trim() 
    : input.value.trim();
  if (!texto) return;

  adicionarMensagem(texto, 'user');
  if (!textoCustomizado) {
    input.value = '';
    document.getElementById('btn-mic').style.display = 'flex';
    document.getElementById('btn-send').style.display = 'none';
  }

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

      const indicador = criarIndicadorDigitacao('Ouvindo o seu áudio com Groq Whisper... 🧘‍♀️');

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
              contentEl.innerHTML = `🎙️ <b>"${data.transcricao}"</b><div style="font-size:10px; color:#5c786f; margin-top:3px;">✨ Transcrito por Groq Whisper</div>`;
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
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true
        }
      });
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

        const indicador = criarIndicadorDigitacao('Ouvindo o seu áudio com Groq Whisper... 🧘‍♀️');

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
                contentEl.innerHTML = `🎙️ <b>"${data.transcricao}"</b><div style="font-size:10px; color:#5c786f; margin-top:3px;">✨ Transcrito por Groq Whisper</div>`;
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

    const isPendentePagamento = al.aprovacao_pagamento === 'pendente';
    if (isPendentePagamento) {
      item.style.borderColor = '#f59e0b';
      item.style.background = '#fffdf5';
    }

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
          ${isPendentePagamento ? `
            <span class="wa-student-badge" style="background: #fffbeb; color: #b45309; border: 1px solid #fcd34d;">
              <i class="fa-solid fa-clock"></i> Matrícula Pendente
            </span>
          ` : `
            <span class="wa-student-badge ${badgeClass}">${situacao}</span>
          `}
        </div>
        <div class="wa-student-sub">
          <span>${al.plano}${al.plano && al.plano.includes('1x') && al.dia_semana_1x ? ` (${al.dia_semana_1x})` : ''} • R$ ${al.valor_mensalidade.toFixed(2)}</span>
          <span>Venc. dia ${al.dia_vencimento}</span>
        </div>
      </div>
      <div class="wa-student-actions" style="display:flex; gap:6px; align-items:center;">
        ${isPendentePagamento ? `
          <button class="wa-btn-primary" style="padding: 5px 9px; font-size: 11px; background: #16a34a; border: none; box-shadow: none; white-space: nowrap;" onclick="event.stopPropagation(); aprovarPagamentoMatricula(${al.id}, '${al.nome.replace(/'/g, "\\'")}');" title="Confirmar pagamento da 1ª mensalidade e ativar aluno (Entrou, Pagou)">
            <i class="fa-solid fa-check"></i> Aprovar (Entrou, Pagou)
          </button>
        ` : ''}
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
    const detCpf = document.getElementById('det-cpf');
    if (detCpf) detCpf.textContent = al.cpf || 'Não informado';
    document.getElementById('det-plano').textContent = al.plano;

    // Aprovação de pagamento pendente (Entrou, Pagou)
    const boxAprov = document.getElementById('det-box-aprovacao-pendente');
    const btnAprov = document.getElementById('det-btn-aprovar-pagamento');
    if (boxAprov && btnAprov) {
      if (al.aprovacao_pagamento === 'pendente') {
        boxAprov.style.display = 'block';
        btnAprov.onclick = async () => {
          await aprovarPagamentoMatricula(al.id, al.nome);
          await abrirDetalhesAluno(al.id);
        };
      } else {
        boxAprov.style.display = 'none';
      }
    }

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

    // Bloco de Contrato Digital no Modal de Detalhes
    const detBadgeContrato = document.getElementById('det-contrato-status-badge');
    const detVigencia = document.getElementById('det-contrato-vigencia');
    const detArquivoStatus = document.getElementById('det-contrato-arquivo-status');
    const detBtnPdf = document.getElementById('det-btn-contrato-pdf');
    const detBtnWa = document.getElementById('det-btn-contrato-wa');
    const detBtnUpload = document.getElementById('det-btn-contrato-upload');
    const detBtnVer = document.getElementById('det-btn-contrato-ver');

    const stContrato = al.status_contrato || 'pendente';
    if (detBadgeContrato) {
      if (stContrato === 'em_dia') {
        detBadgeContrato.textContent = 'Em Dia';
        detBadgeContrato.className = 'wa-student-badge badge-contrato-em-dia';
      } else if (stContrato === 'a_vencer') {
        detBadgeContrato.textContent = 'A Vencer';
        detBadgeContrato.className = 'wa-student-badge badge-contrato-a-vencer';
      } else if (stContrato === 'vencido') {
        detBadgeContrato.textContent = 'Vencido';
        detBadgeContrato.className = 'wa-student-badge badge-contrato-vencido';
      } else {
        detBadgeContrato.textContent = 'Pendente de Assinatura';
        detBadgeContrato.className = 'wa-student-badge badge-contrato-pendente';
      }
    }

    if (detVigencia) {
      detVigencia.textContent = al.data_vigencia_contrato 
        ? `${formatarDataBR(al.data_vigencia_contrato)} (${al.dias_restantes_contrato != null ? al.dias_restantes_contrato + ' dias restantes' : '1 ano'})`
        : 'Pendente de assinatura e envio';
    }

    if (detArquivoStatus) {
      detArquivoStatus.innerHTML = al.contrato_assinado_arquivo 
        ? '<span style="color:#15803d; font-weight:600;"><i class="fa-solid fa-check-circle"></i> Anexado (mútuo)</span>' 
        : '<span style="color:#b45309;">Nenhum arquivo enviado</span>';
    }

    if (detBtnPdf) {
      detBtnPdf.href = `/api/alunos/${al.id}/contrato/pdf`;
    }

    if (detBtnWa) {
      const msgContrato = encodeURIComponent(
        `Olá, ${al.nome}! 🧘‍♀️ Segue a minuta do seu Contrato de Prestação de Serviços de Yoga no Studio Shanti.\n\n` +
        `Link para visualizar: ${window.location.origin}/api/alunos/${al.id}/contrato/pdf\n\n` +
        `Assim que finalizarmos a assinatura mútua, guardamos a via oficial arquivada no estúdio. Namastê! 🙏`
      );
      detBtnWa.href = `https://wa.me/${tel}?text=${msgContrato}`;
    }

    if (detBtnUpload) {
      detBtnUpload.onclick = () => {
        abrirModalUploadContrato(al.id, al.nome, al.plano);
      };
    }

    if (detBtnVer) {
      if (al.contrato_assinado_arquivo) {
        detBtnVer.style.display = 'inline-flex';
        detBtnVer.href = `/api/alunos/${al.id}/contrato/arquivo`;
      } else {
        detBtnVer.style.display = 'none';
      }
    }

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

    // Resetar campo de CPF
    const cpfEl = document.getElementById('cad-cpf');
    if (cpfEl) cpfEl.value = '';

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
      cpf: (document.getElementById('cad-cpf')?.value || '').trim() || null,
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

      // Resetar para À Vista
      const radioAvista = document.getElementById('radio-tipo-avista');
      if (radioAvista) {
        radioAvista.checked = true;
        const event = new Event('change');
        radioAvista.dispatchEvent(event);
      }

      abrirModal('modal-add-despesa');
    });
  }

  setupDespesasParceladas();

  const formDespesa = document.getElementById('form-add-despesa');
  if (formDespesa) {
    formDespesa.addEventListener('submit', async (e) => {
      e.preventDefault();
      const radioParcelado = document.getElementById('radio-tipo-parcelado');
      const isParcelado = Boolean(radioParcelado && radioParcelado.checked);

      const dados = {
        descricao: document.getElementById('desp-desc').value.trim(),
        valor: parseFloat(document.getElementById('desp-valor').value),
        categoria: document.getElementById('desp-cat').value,
        data: document.getElementById('desp-data').value || undefined,
        data_vencimento: document.getElementById('desp-vencimento')?.value || undefined,
        status: isParcelado ? 'pendente' : (document.getElementById('desp-status')?.value || 'pago'),
        parcelado: isParcelado,
        total_parcelas: isParcelado ? parseInt(document.getElementById('desp-num-parcelas')?.value || '2') : 1,
        tipo_calculo_parcela: isParcelado ? (document.getElementById('desp-tipo-calculo')?.value || 'total') : 'total',
        primeira_parcela_paga: isParcelado ? Boolean(document.getElementById('desp-primeira-paga')?.checked) : false
      };

      try {
        const res = await fetch('/api/despesas', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(dados)
        });
        if (!res.ok) throw new Error('Falha ao salvar despesa');
        
        fecharModal('modal-add-despesa');
        
        if (isParcelado) {
          showToast(`✨ Compra parcelada em ${dados.total_parcelas}x registrada com sucesso!`);
          adicionarMensagem(`💳 *Despesa parcelada registrada:* ${dados.descricao} parcelada em *${dados.total_parcelas} meses* (${dados.categoria}) com vencimentos mensais programados.`, 'bot');
        } else {
          showToast('Despesa registrada com sucesso!');
          adicionarMensagem(`💸 *Despesa registrada:* ${dados.descricao} no valor de *R$ ${dados.valor.toFixed(2)}* (${dados.categoria}) - Vencimento: ${dados.data_vencimento ? formatarDataBR(dados.data_vencimento) : 'Hoje'}.`, 'bot');
        }

        await carregarFinanceiro();
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

  function setupDespesasParceladas() {
    const radioAvista = document.getElementById('radio-tipo-avista');
    const radioParcelado = document.getElementById('radio-tipo-parcelado');
    const boxParcelamento = document.getElementById('box-despesa-parcelamento');
    const boxStatusAvista = document.getElementById('box-desp-status-avista');
    const lblAvista = document.getElementById('lbl-tipo-avista');
    const lblParcelado = document.getElementById('lbl-tipo-parcelado');
    const lblVencimento = document.getElementById('lbl-desp-vencimento');

    const atualizarVisibilidadeTipo = () => {
      const isParcelado = radioParcelado && radioParcelado.checked;
      if (isParcelado) {
        if (boxParcelamento) boxParcelamento.style.display = 'block';
        if (boxStatusAvista) boxStatusAvista.style.display = 'none';
        if (lblParcelado) {
          lblParcelado.style.border = '1.5px solid var(--shanti-forest)';
          lblParcelado.style.background = 'var(--shanti-sage-light)';
          lblParcelado.style.color = 'var(--shanti-forest)';
        }
        if (lblAvista) {
          lblAvista.style.border = '1px solid var(--shanti-sand-border)';
          lblAvista.style.background = 'var(--shanti-sand-light)';
          lblAvista.style.color = 'var(--shanti-charcoal)';
        }
        if (lblVencimento) lblVencimento.textContent = 'Vencimento da 1ª Parcela *';
      } else {
        if (boxParcelamento) boxParcelamento.style.display = 'none';
        if (boxStatusAvista) boxStatusAvista.style.display = 'block';
        if (lblAvista) {
          lblAvista.style.border = '1.5px solid var(--shanti-forest)';
          lblAvista.style.background = 'var(--shanti-sage-light)';
          lblAvista.style.color = 'var(--shanti-forest)';
        }
        if (lblParcelado) {
          lblParcelado.style.border = '1px solid var(--shanti-sand-border)';
          lblParcelado.style.background = 'var(--shanti-sand-light)';
          lblParcelado.style.color = 'var(--shanti-charcoal)';
        }
        if (lblVencimento) lblVencimento.textContent = 'Data de Vencimento *';
      }
      atualizarPreviaParcelas();
    };

    if (radioAvista) radioAvista.addEventListener('change', atualizarVisibilidadeTipo);
    if (radioParcelado) radioParcelado.addEventListener('change', atualizarVisibilidadeTipo);

    const idsCalculo = ['desp-valor', 'desp-num-parcelas', 'desp-tipo-calculo', 'desp-primeira-paga', 'desp-vencimento'];
    idsCalculo.forEach(id => {
      const el = document.getElementById(id);
      if (el) {
        el.addEventListener('input', atualizarPreviaParcelas);
        el.addEventListener('change', atualizarPreviaParcelas);
      }
    });
  }

  function atualizarPreviaParcelas() {
    const elTexto = document.getElementById('texto-previa-parcelas');
    if (!elTexto) return;

    const radioParcelado = document.getElementById('radio-tipo-parcelado');
    if (!radioParcelado || !radioParcelado.checked) return;

    const valorInput = parseFloat(document.getElementById('desp-valor')?.value) || 0;
    const numParcelas = parseInt(document.getElementById('desp-num-parcelas')?.value || '2');
    const tipoCalculo = document.getElementById('desp-tipo-calculo')?.value || 'total';
    const primeiraPaga = Boolean(document.getElementById('desp-primeira-paga')?.checked);
    const vencimento1 = document.getElementById('desp-vencimento')?.value;

    if (valorInput <= 0) {
      elTexto.innerHTML = 'Preencha o valor para calcular as parcelas.';
      return;
    }

    let valorParcela = 0;
    let valorTotal = 0;
    if (tipoCalculo === 'parcela') {
      valorParcela = valorInput;
      valorTotal = valorInput * numParcelas;
    } else {
      valorTotal = valorInput;
      valorParcela = valorTotal / numParcelas;
    }

    let periodoTexto = '';
    if (vencimento1) {
      const meses = ['Jan', 'Fev', 'Mar', 'Abr', 'Mai', 'Jun', 'Jul', 'Ago', 'Set', 'Out', 'Nov', 'Dez'];
      const partes = vencimento1.split('-');
      if (partes.length === 3) {
        const y0 = parseInt(partes[0]);
        const m0 = parseInt(partes[1]) - 1;

        const mesInicio = `${meses[m0]}/${y0}`;
        const totalMesesFim = (y0 * 12 + m0) + (numParcelas - 1);
        const yFim = Math.floor(totalMesesFim / 12);
        const mFim = totalMesesFim % 12;
        const mesFim = `${meses[mFim]}/${yFim}`;

        periodoTexto = ` • Vencimentos: <b>${mesInicio}</b> até <b>${mesFim}</b>`;
      }
    }

    const status1Texto = primeiraPaga ? ' • <span style="color:#15803d; font-weight:600;"><i class="fa-solid fa-check"></i> 1ª Parcela Paga no ato</span>' : '';

    elTexto.innerHTML = `💳 <b>${numParcelas}x de R$ ${valorParcela.toFixed(2)}</b> (Total: R$ ${valorTotal.toFixed(2)})${periodoTexto}${status1Texto}`;
  }

  // Modal de Upload de Contrato Assinado (Fase 4)
  const formUploadContrato = document.getElementById('form-upload-contrato');
  if (formUploadContrato) {
    formUploadContrato.addEventListener('submit', async (e) => {
      e.preventDefault();
      const alunoId = document.getElementById('upload-contrato-aluno-id').value;
      const fileInput = document.getElementById('upload-contrato-arquivo');
      if (!fileInput || !fileInput.files || fileInput.files.length === 0) {
        alert('Por favor, selecione o arquivo do contrato assinado.');
        return;
      }
      const formData = new FormData();
      formData.append('file', fileInput.files[0]);

      const btnSubmit = document.getElementById('btn-submit-upload-contrato');
      const origHtml = btnSubmit ? btnSubmit.innerHTML : '';
      if (btnSubmit) {
        btnSubmit.disabled = true;
        btnSubmit.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Enviando...';
      }

      try {
        const res = await fetch(`/api/alunos/${alunoId}/contrato/upload`, {
          method: 'POST',
          body: formData
        });
        const result = await res.json();
        if (res.ok) {
          showToast('Contrato assinado anexado com sucesso! Vigência de 1 ano ativada.');
          fecharModal('modal-upload-contrato');
          await atualizarTudo();
          if (state.alunoSelecionado && state.alunoSelecionado.id === parseInt(alunoId)) {
            await abrirDetalhesAluno(alunoId);
          }
        } else {
          alert(result.detail || 'Erro ao enviar contrato assinado.');
        }
      } catch (err) {
        alert('Falha na comunicação com o servidor ao enviar contrato.');
      } finally {
        if (btnSubmit) {
          btnSubmit.disabled = false;
          btnSubmit.innerHTML = origHtml;
        }
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
  if (modal) {
    modal.classList.add('active');
    modal.style.display = 'flex';
  }
}

function fecharModal(id) {
  const modal = document.getElementById(id);
  if (modal) {
    modal.classList.remove('active');
    modal.style.display = 'none';
  }
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
        bannerAlerta.style.background = 'var(--shanti-terracotta-light)';
        bannerAlerta.style.border = '1px solid var(--shanti-terracotta-border)';
        bannerAlerta.style.color = 'var(--shanti-terracotta)';
        bannerAlerta.innerHTML = `<i class="fa-solid fa-triangle-exclamation"></i> <b>${alertas.total_atrasadas} despesa(s) vencida(s) em aberto!</b> Total pendente: <b>R$ ${alertas.valor_total_atrasadas.toFixed(2)}</b>. Verifique abaixo para regularizar.`;
      } else if (alertas.total_vencendo_hoje > 0) {
        bannerAlerta.style.display = 'block';
        bannerAlerta.style.background = '#FDF3E7';
        bannerAlerta.style.border = '1px solid #F6D6B2';
        bannerAlerta.style.color = '#B45309';
        bannerAlerta.innerHTML = `<i class="fa-solid fa-clock"></i> <b>${alertas.total_vencendo_hoje} conta(s) vencendo HOJE!</b> Total: <b>R$ ${alertas.valor_total_hoje.toFixed(2)}</b>.`;
      } else if (alertas.total_proximas > 0) {
        bannerAlerta.style.display = 'block';
        bannerAlerta.style.background = 'var(--shanti-sand-light)';
        bannerAlerta.style.border = '1px solid var(--shanti-sand-border)';
        bannerAlerta.style.color = 'var(--shanti-charcoal)';
        bannerAlerta.innerHTML = `<i class="fa-solid fa-circle-info" style="color:var(--shanti-sage);"></i> <b>${alertas.total_proximas} despesa(s) vencem nos próximos 5 dias.</b> Total: R$ ${alertas.valor_total_proximas.toFixed(2)}.`;
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
          <div style="font-size: 12px; color: var(--shanti-stone); text-align: center; padding: 16px; background: var(--shanti-sand-light); border: 1px dashed var(--shanti-sand-border); border-radius: 12px;">
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
            <div style="background:var(--shanti-sand-light); border:1px solid var(--shanti-sand-border); border-radius:12px; padding:12px 14px; display:flex; justify-content:space-between; align-items:center; gap:10px; transition:all 0.2s ease;">
              <div style="flex:1; min-width:0;">
                <div style="display:flex; align-items:center; gap:6px; flex-wrap:wrap; margin-bottom:4px;">
                  <span style="font-weight:600; font-size:13.5px; color:var(--shanti-charcoal);">${p.aluno_nome}</span>
                  <span style="font-size:10.5px; background:rgba(63,78,58,0.08); color:var(--shanti-forest); padding:2px 7px; border-radius:10px; font-weight:500;">${planoFormatado}</span>
                  <span style="background:var(--shanti-sage-light); color:#3F4E3A; font-weight:600; font-size:10.5px; padding:2px 8px; border-radius:10px; border:1px solid var(--shanti-sage-border);"><i class="fa-solid fa-check"></i> Pago</span>
                </div>
                <div style="font-size:11.5px; color:var(--shanti-stone);">
                  <span>Data: <b>${formatarDataBR(p.data_pagamento)}</b></span> • <span>Forma: <b>${p.forma_pagamento || 'PIX'}</b></span>
                </div>
              </div>
              <div style="text-align:right; display:flex; flex-direction:column; align-items:flex-end; gap:6px;">
                <span style="font-weight:700; font-size:14px; color:#3F4E3A;">+ R$ ${p.valor.toFixed(2)}</span>
                <button class="btn-recibo-pagamento-financeiro" data-id="${p.id}" title="Ver Comprovante" style="background:#FFFFFF; border:1px solid var(--shanti-sand-border); border-radius:14px; padding:3px 10px; font-size:11px; font-weight:500; color:var(--shanti-forest); cursor:pointer; box-shadow:var(--shadow-sm);">
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
          <div style="font-size: 12px; color: var(--shanti-stone); text-align: center; padding: 16px; background: var(--shanti-sand-light); border: 1px dashed var(--shanti-sand-border); border-radius: 12px;">
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
            statusBadge = `<span style="background:var(--shanti-sage-light); color:#3F4E3A; font-weight:600; font-size:10.5px; padding:2px 8px; border-radius:10px; border:1px solid var(--shanti-sage-border);"><i class="fa-solid fa-check"></i> Paga</span>`;
          } else if (isAtrasado) {
            statusBadge = `<span style="background:var(--shanti-terracotta-light); color:var(--shanti-terracotta); font-weight:600; font-size:10.5px; padding:2px 8px; border-radius:10px; border:1px solid var(--shanti-terracotta-border);"><i class="fa-solid fa-exclamation"></i> Vencida</span>`;
          } else if (isHoje) {
            statusBadge = `<span style="background:#FDF3E7; color:#B45309; font-weight:600; font-size:10.5px; padding:2px 8px; border-radius:10px; border:1px solid #F6D6B2;"><i class="fa-solid fa-clock"></i> Vence Hoje</span>`;
          } else {
            statusBadge = `<span style="background:var(--shanti-sand-light); color:var(--shanti-stone); font-weight:500; font-size:10.5px; padding:2px 8px; border-radius:10px; border:1px solid var(--shanti-sand-border);">A Pagar</span>`;
          }

          const ehParcelado = Boolean(d.total_parcelas && d.total_parcelas > 1);
          const parcelaBadge = ehParcelado ? `
            <span class="badge-parcela" title="Despesa parcelada em ${d.total_parcelas}x">
              <i class="fa-solid fa-credit-card"></i> ${d.parcela_atual || 1}/${d.total_parcelas}
            </span>
          ` : '';

          return `
            <div style="background:var(--shanti-sand-light); border:1px solid var(--shanti-sand-border); border-radius:12px; padding:12px 14px; display:flex; justify-content:space-between; align-items:center; gap:10px; transition:all 0.2s ease;">
              <div style="flex:1; min-width:0;">
                <div style="display:flex; align-items:center; gap:6px; flex-wrap:wrap; margin-bottom:4px;">
                  <span style="font-weight:600; font-size:13.5px; color:var(--shanti-charcoal);">${d.descricao}</span>
                  <span style="font-size:10.5px; background:rgba(63,78,58,0.08); color:var(--shanti-forest); padding:2px 7px; border-radius:10px; font-weight:500;">${d.categoria}</span>
                  ${parcelaBadge}
                  ${statusBadge}
                </div>
                <div style="font-size:11.5px; color:var(--shanti-stone);">
                  <span>Vencimento: <b>${formatarDataBR(dtVenc)}</b></span>
                  ${d.data_despesa && d.data_despesa !== dtVenc ? ` • <span style="font-size:11px;">Emissão: ${formatarDataBR(d.data_despesa)}</span>` : ''}
                </div>
              </div>

              <div style="text-align:right; display:flex; flex-direction:column; align-items:flex-end; gap:6px;">
                <span style="font-weight:700; font-size:14px; color:var(--shanti-terracotta);">- R$ ${d.valor.toFixed(2)}</span>
                <div style="display:flex; gap:6px;">
                  <button class="btn-editar-despesa" data-id="${d.id}" title="Editar Despesa" style="background:#FFFFFF; border:1px solid var(--shanti-sand-border); border-radius:10px; padding:4px 9px; font-size:11px; color:var(--shanti-forest); cursor:pointer; box-shadow:var(--shadow-sm);">
                    <i class="fa-solid fa-pen"></i>
                  </button>
                  <button class="btn-excluir-despesa" data-id="${d.id}" data-desc="${d.descricao}" data-grupo="${d.grupo_parcelamento_id || ''}" data-parcela="${ehParcelado ? `${d.parcela_atual}/${d.total_parcelas}` : ''}" title="Excluir Despesa" style="background:#FFFFFF; border:1px solid var(--shanti-terracotta-border); border-radius:10px; padding:4px 9px; font-size:11px; color:var(--shanti-terracotta); cursor:pointer; box-shadow:var(--shadow-sm);">
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
            excluirDespesa(parseInt(btn.dataset.id), btn.dataset.desc, btn.dataset.grupo, btn.dataset.parcela);
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

async function excluirDespesa(id, descricao, grupoId, parcelaInfo) {
  let excluirGrupo = false;

  if (grupoId && parcelaInfo) {
    const querExcluirTudo = confirm(
      `A despesa "${descricao}" faz parte de uma compra parcelada (${parcelaInfo}).\n\n` +
      `Deseja excluir TODAS as parcelas deste parcelamento?\n\n` +
      `• Clique em [OK] para excluir TODAS as parcelas de uma vez.\n` +
      `• Clique em [Cancelar] se desejar excluir apenas esta parcela avulsa.`
    );
    if (querExcluirTudo) {
      excluirGrupo = true;
    } else {
      const confirmaApenasEsta = confirm(`Confirma a exclusão APENAS desta parcela avulsa (${parcelaInfo})?`);
      if (!confirmaApenasEsta) return;
      excluirGrupo = false;
    }
  } else {
    if (!confirm(`Tem certeza de que deseja apagar a despesa "${descricao}"?\n\nEsta ação removerá o registro do balanço financeiro.`)) {
      return;
    }
  }

  try {
    const res = await fetch(`/api/despesas/${id}?excluir_grupo=${excluirGrupo}`, { method: 'DELETE' });
    if (res.ok) {
      showToast(excluirGrupo ? 'Parcelamento completo excluído com sucesso!' : 'Despesa excluída com sucesso!');
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
        badgeTurmas.style.background = 'var(--shanti-terracotta-light)';
        badgeTurmas.style.border = '1px solid var(--shanti-terracotta-border)';
        badgeTurmas.style.color = 'var(--shanti-terracotta)';
        badgeTurmas.innerHTML = `<i class="fa-solid fa-triangle-exclamation"></i> ${lotadas.length} Turma(s) Lotada(s)`;
      } else {
        badgeTurmas.style.background = 'var(--shanti-sage-light)';
        badgeTurmas.style.border = '1px solid var(--shanti-sage-border)';
        badgeTurmas.style.color = '#3F4E3A';
        badgeTurmas.innerHTML = `<i class="fa-solid fa-circle-check"></i> ${turmas.length} Turmas Ativas`;
      }
    }

    if (containerTurmas) {
      if (!turmas || turmas.length === 0) {
        containerTurmas.innerHTML = '<div style="font-size:12px; color:var(--shanti-stone); text-align:center; padding:16px; background:var(--shanti-sand-light); border:1px dashed var(--shanti-sand-border); border-radius:12px;">Nenhuma turma cadastrada.</div>';
      } else {
        containerTurmas.innerHTML = turmas.map(t => {
          const cap = t.capacidade_vagas || 16;
          const total = t.total_matriculados || 0;
          const isLotada = total >= cap;
          const isQuaseLotada = total === cap - 1;
          const percent = Math.min(100, Math.round((total / cap) * 100));

          let barColor = 'var(--shanti-forest)';
          let statusBadge = `<span style="font-size:11px; font-weight:600; color:#3F4E3A; background:var(--shanti-sage-light); border:1px solid var(--shanti-sage-border); padding:2px 8px; border-radius:10px;">${t.vagas_disponiveis} vagas livres</span>`;

          if (isLotada) {
            barColor = 'var(--shanti-terracotta)';
            statusBadge = `<span style="background:var(--shanti-terracotta-light); color:var(--shanti-terracotta); font-weight:600; font-size:10.5px; padding:2px 8px; border-radius:10px; border:1px solid var(--shanti-terracotta-border);"><i class="fa-solid fa-triangle-exclamation"></i> Lotada (${total}/${cap})</span>`;
          } else if (isQuaseLotada) {
            barColor = '#C98A4B';
            statusBadge = `<span style="background:#FDF3E7; color:#B45309; font-weight:600; font-size:10.5px; padding:2px 8px; border-radius:10px; border:1px solid #F6D6B2;"><i class="fa-solid fa-bolt"></i> Resta 1 vaga</span>`;
          }

          let alunosHtml = '';
          if (!t.alunos || t.alunos.length === 0) {
            alunosHtml = `
              <div style="font-size:12px; color:var(--shanti-stone); font-style:italic; padding:6px 0;">
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
                badgePlano = `<span style="font-size:10.5px; background:var(--shanti-sage-light); color:#3F4E3A; padding:2px 7px; border-radius:8px; font-weight:600; border:1px solid var(--shanti-sage-border); display:inline-flex; align-items:center; gap:4px;" title="Comparece 1x na semana"><i class="fa-regular fa-calendar-check" style="color:var(--shanti-sage);"></i> 1x na semana (${diaEscolhido})</span>`;
              } else {
                badgePlano = `<span style="font-size:10.5px; background:var(--shanti-sand-light); color:var(--shanti-charcoal); padding:2px 7px; border-radius:8px; font-weight:500; border:1px solid var(--shanti-sand-border);">2x na semana</span>`;
              }

              let statusAluno = '';
              if (al.status === 'inativo') {
                statusAluno = `<span style="font-size:10px; background:var(--shanti-sand-light); color:var(--shanti-stone); padding:1px 6px; border-radius:6px; border:1px solid var(--shanti-sand-border);">Inativo</span>`;
              } else if (al.inadimplente) {
                statusAluno = `<span style="font-size:10px; background:var(--shanti-terracotta-light); color:var(--shanti-terracotta); padding:1px 6px; border-radius:6px; font-weight:600; border:1px solid var(--shanti-terracotta-border);">Mensalidade Pendente</span>`;
              }

              return `
                <div style="display:flex; justify-content:space-between; align-items:center; padding:6px 0; border-bottom:1px dashed var(--shanti-sand-border); font-size:12.5px;">
                  <div style="display:flex; align-items:center; gap:6px; flex-wrap:wrap;">
                    <i class="fa-regular fa-user" style="color:var(--shanti-forest); font-size:11px;"></i>
                    <span style="font-weight:600; color:var(--shanti-charcoal); cursor:pointer;" class="link-aluno-detalhes" data-aluno-id="${al.id}">${al.nome}</span>
                    ${badgePlano}
                    ${statusAluno}
                  </div>
                  ${tel ? `
                    <a href="${waLink}" target="_blank" title="Conversar no WhatsApp" style="color:var(--shanti-whatsapp-green); font-size:15px; padding:2px 6px; display:inline-flex; align-items:center;">
                      <i class="fa-brands fa-whatsapp"></i>
                    </a>
                  ` : ''}
                </div>
              `;
            }).join('');
          }

          return `
            <div style="background:var(--shanti-sand-light); padding:14px 16px; border-radius:14px; border:1px solid var(--shanti-sand-border); box-shadow:var(--shadow-sm); transition:all 0.2s ease;">
              <div style="display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:8px;">
                <div>
                  <div style="font-weight:700; font-size:14.5px; color:var(--shanti-charcoal); font-family:var(--font-brand);">${t.nome}</div>
                  <div style="font-size:12px; color:var(--shanti-stone); margin-top:2px;"><i class="fa-regular fa-clock"></i> ${t.dias_semana} às ${t.horario}</div>
                </div>
                <div>${statusBadge}</div>
              </div>

              <div style="background:#E8E0D5; border-radius:999px; height:7px; width:100%; overflow:hidden; margin:10px 0 6px 0;">
                <div style="background:${barColor}; width:${percent}%; height:100%; border-radius:999px; transition:width 0.4s ease;"></div>
              </div>
              <div style="display:flex; justify-content:space-between; font-size:11px; color:var(--shanti-stone); margin-bottom:12px;">
                <span><b>${total}</b> de <b>${cap}</b> alunos matriculados</span>
                <span style="font-weight:600;">${percent}% ocupada</span>
              </div>

              <div style="margin-top:10px; padding-top:8px; border-top:1px solid var(--shanti-sand-border);">
                <div style="font-size:11.5px; font-weight:600; color:var(--shanti-forest); margin-bottom:6px; display:flex; align-items:center; gap:5px;">
                  <i class="fa-solid fa-users" style="font-size:11px;"></i> Alunos Matriculados (${total}):
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
        listAniv.innerHTML = '<div style="font-size: 12px; color: var(--shanti-stone); text-align: center; padding: 12px; background: var(--shanti-sand-light); border: 1px dashed var(--shanti-sand-border); border-radius: 10px;">Nenhum aniversariante neste mês.</div>';
      } else {
        listAniv.innerHTML = aniversariantes.map(a => {
          let tel = (a.telefone || '').replace(/\D/g, '');
          if (!tel.startsWith('55') && tel) tel = '55' + tel;
          const msgParabens = encodeURIComponent(`Olá, ${a.nome}! 🎉🎂 Passando para te desejar um Feliz Aniversário repleto de paz, luz e harmonia! Muita gratidão por fazer parte da família Studio Shanti. Namastê! 🙏✨`);
          const waLink = a.link_whatsapp || `https://wa.me/${tel}?text=${msgParabens}`;
          const ehHojeBadge = a.e_hoje ? `<span style="background:var(--shanti-terracotta-light); color:var(--shanti-terracotta); border:1px solid var(--shanti-terracotta-border); font-size:10px; font-weight:700; padding:2px 7px; border-radius:10px; margin-left:6px;"><i class="fa-solid fa-cake-candles"></i> É HOJE!</span>` : '';

          return `
            <div class="wa-report-item" style="${a.e_hoje ? 'background:var(--shanti-terracotta-light); border:1px solid var(--shanti-terracotta-border);' : ''}">
              <div class="wa-report-item-info">
                <span class="wa-report-item-title"><i class="fa-solid fa-cake-candles" style="color:var(--shanti-terracotta); font-size:12px;"></i> ${a.nome} ${ehHojeBadge}</span>
                <span class="wa-report-item-sub">Dia ${a.dia} (${a.data_nascimento ? formatarDataBR(a.data_nascimento) : ''}) • ${a.plano || 'Yoga Regular'}</span>
              </div>
              <a href="${waLink}" target="_blank" class="wa-btn-sm-whatsapp">
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
        listAus.innerHTML = '<div style="font-size: 12px; color: var(--shanti-stone); text-align: center; padding: 12px; background: var(--shanti-sand-light); border: 1px dashed var(--shanti-sand-border); border-radius: 10px;">Todos os alunos ativos estão frequentando!</div>';
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
                <span class="wa-report-item-sub" style="color: #B45309; font-weight:600;"><i class="fa-solid fa-clock-rotate-left" style="font-size:11px;"></i> ${au.dias_ausente} dias sem praticar • ${au.plano}</span>
              </div>
              <a href="${waLink}" target="_blank" class="wa-btn-sm-whatsapp">
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
    if (state.configuracoes.groq_api_key) {
      const elGroq = document.getElementById('cfg-groq-key');
      if (elGroq) elGroq.value = state.configuracoes.groq_api_key;
    }
    if (state.configuracoes.gemini_api_key) {
      const elGemini = document.getElementById('cfg-gemini-key');
      if (elGemini) elGemini.value = state.configuracoes.gemini_api_key;
    }
    if (state.configuracoes.valor_plano_1x) {
      const el1x = document.getElementById('cfg-valor-plano-1x');
      if (el1x) el1x.value = state.configuracoes.valor_plano_1x;
    }
    if (state.configuracoes.valor_plano_2x) {
      const el2x = document.getElementById('cfg-valor-plano-2x');
      if (el2x) el2x.value = state.configuracoes.valor_plano_2x;
    }
    if (state.configuracoes.autentique_api_token) {
      const elToken = document.getElementById('cfg-autentique-token');
      if (elToken) elToken.value = state.configuracoes.autentique_api_token;
    }
    if (state.configuracoes.autentique_sandbox !== undefined) {
      const elSb = document.getElementById('cfg-autentique-sandbox');
      if (elSb) elSb.checked = (state.configuracoes.autentique_sandbox === 'true' || state.configuracoes.autentique_sandbox === true);
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
  // Controles do Autentique (Assinatura Digital)
  const btnToggleToken = document.getElementById('btn-toggle-autentique-token');
  if (btnToggleToken) {
    btnToggleToken.addEventListener('click', () => {
      const input = document.getElementById('cfg-autentique-token');
      if (!input) return;
      if (input.type === 'password') {
        input.type = 'text';
        btnToggleToken.innerHTML = '<i class="fa-solid fa-eye-slash"></i>';
      } else {
        input.type = 'password';
        btnToggleToken.innerHTML = '<i class="fa-solid fa-eye"></i>';
      }
    });
  }

  const btnCopyWebhook = document.getElementById('btn-copiar-webhook-url');
  if (btnCopyWebhook) {
    btnCopyWebhook.addEventListener('click', () => {
      const input = document.getElementById('cfg-autentique-webhook-url');
      if (input) {
        navigator.clipboard.writeText(input.value);
        showToast('URL do Webhook copiada!');
      }
    });
  }

  const btnTestarAutentique = document.getElementById('btn-testar-autentique');
  if (btnTestarAutentique) {
    btnTestarAutentique.addEventListener('click', async () => {
      await testarConexaoAutentique();
    });
  }

  const btnSalvarAutentique = document.getElementById('btn-salvar-autentique');
  if (btnSalvarAutentique) {
    btnSalvarAutentique.addEventListener('click', async () => {
      await salvarConfigAutentique();
    });
  }

  // Listeners dos Modais do Autentique
  const formEnvioAutentique = document.getElementById('form-enviar-autentique');
  if (formEnvioAutentique) {
    formEnvioAutentique.addEventListener('submit', confirmarEnvioAutentique);
  }

  const btnCopiarLinkNatalia = document.getElementById('btn-copiar-link-natalia');
  if (btnCopiarLinkNatalia) {
    btnCopiarLinkNatalia.addEventListener('click', () => {
      const input = document.getElementById('links-autentique-natalia-url');
      if (input && input.value) {
        navigator.clipboard.writeText(input.value);
        showToast('Link da Natália copiado!');
      }
    });
  }

  const btnCopiarLinkAluno = document.getElementById('btn-copiar-link-aluno');
  if (btnCopiarLinkAluno) {
    btnCopiarLinkAluno.addEventListener('click', () => {
      const input = document.getElementById('links-autentique-aluno-url');
      if (input && input.value) {
        navigator.clipboard.writeText(input.value);
        showToast('Link de assinatura do aluno copiado!');
      }
    });
  }

  const btnCopiarLinkPdf = document.getElementById('btn-copiar-link-pdf-assinado');
  if (btnCopiarLinkPdf) {
    btnCopiarLinkPdf.addEventListener('click', () => {
      const input = document.getElementById('links-autentique-pdf-assinado-url');
      if (input && input.value) {
        navigator.clipboard.writeText(input.value);
        showToast('Link do contrato assinado copiado!');
      }
    });
  }

  const btnSincronizarAutentique = document.getElementById('btn-sincronizar-autentique');
  if (btnSincronizarAutentique) {
    btnSincronizarAutentique.addEventListener('click', async () => {
      const alunoId = document.getElementById('links-autentique-aluno-id')?.value;
      if (alunoId) await verificarStatusAutentique(alunoId, true);
    });
  }

  const btnReenviarAutentique = document.getElementById('btn-reenviar-autentique');
  if (btnReenviarAutentique) {
    btnReenviarAutentique.addEventListener('click', async () => {
      const alunoId = document.getElementById('links-autentique-aluno-id')?.value;
      if (!alunoId) return;
      if (!confirm('Deseja gerar um novo envio deste contrato no Autentique (com código exclusivamente via WhatsApp)?')) return;
      
      btnReenviarAutentique.disabled = true;
      btnReenviarAutentique.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Enviando...';
      try {
        const res = await fetch(`/api/alunos/${alunoId}/contrato/autentique/enviar`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ sandbox: true })
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Erro ao gerar novo envio.');
        showToast('Novo contrato gerado no Autentique via WhatsApp!');
        await carregarContratos();
        const aluno = (state.contratos || []).find(c => c.id == alunoId) || {};
        abrirModalLinksAutentique(alunoId, aluno.nome || 'Aluno', data.document_id, data.link_aluno, aluno.telefone, data.link_natalia);
      } catch (err) {
        alert(err.message);
      } finally {
        btnReenviarAutentique.disabled = false;
        btnReenviarAutentique.innerHTML = '<i class="fa-solid fa-arrows-rotate"></i> Gerar Novo Envio';
      }
    });
  }

  // Controle de Visualização da Chave Groq
  const btnToggleGroq = document.getElementById('btn-toggle-groq-key');
  if (btnToggleGroq) {
    btnToggleGroq.addEventListener('click', () => {
      const input = document.getElementById('cfg-groq-key');
      if (!input) return;
      if (input.type === 'password') {
        input.type = 'text';
        btnToggleGroq.innerHTML = '<i class="fa-solid fa-eye-slash"></i>';
      } else {
        input.type = 'password';
        btnToggleGroq.innerHTML = '<i class="fa-solid fa-eye"></i>';
      }
    });
  }

  // 1. Salvar Configurações Gerais
  document.getElementById('btn-salvar-configuracoes').addEventListener('click', async () => {
    const configs = {
      nome_studio: document.getElementById('cfg-nome-studio').value.trim() || 'Studio Shanti',
      chave_pix: document.getElementById('cfg-chave-pix').value.trim(),
      tipo_chave_pix: document.getElementById('cfg-tipo-pix').value,
      groq_api_key: document.getElementById('cfg-groq-key')?.value.trim() || '',
      ai_provider: 'groq',
      gemini_api_key: document.getElementById('cfg-gemini-key')?.value.trim() || '',
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

  // 3. Botão de Rodar Diagnóstico Manual do Sistema
  const btnRodarDiag = document.getElementById('btn-rodar-diagnostico');
  if (btnRodarDiag) {
    btnRodarDiag.addEventListener('click', () => {
      executarDiagnosticoManual();
    });
  }
}

// =============================================================================
// DIAGNÓSTICO DO SISTEMA & OBSERVABILIDADE (RENDER VS. GEMINI)
// =============================================================================

async function carregarDiagnostico() {
  const containerLogs = document.getElementById('lista-logs-diagnostico');
  const elUptime = document.getElementById('diag-servidor-uptime');
  const elCold = document.getElementById('diag-servidor-coldstart');
  const badgeServidor = document.getElementById('badge-diag-servidor');
  const elKeepalive = document.getElementById('diag-keepalive-status');

  try {
    const res = await fetch('/api/diagnostico/resumo');
    if (!res.ok) return;
    const data = await res.json();

    // 1. Atualizar Bloco Servidor
    if (data.servidor) {
      if (elUptime) elUptime.textContent = data.servidor.uptime_formatado || '0s';
      if (elCold) {
        if (data.servidor.cold_start) {
          elCold.textContent = 'Sim (acordou há <3 min)';
          elCold.style.color = '#b45309';
          if (badgeServidor) {
            badgeServidor.textContent = 'Acordando';
            badgeServidor.style.background = '#fef3c7';
            badgeServidor.style.color = '#b45309';
          }
        } else {
          elCold.textContent = 'Não (servidor ativo/quente)';
          elCold.style.color = '#2e7d32';
          if (badgeServidor) {
            badgeServidor.textContent = 'Online (Quente)';
            badgeServidor.style.background = '#e8f5e9';
            badgeServidor.style.color = '#2e7d32';
          }
        }
      }
    }

    // 2. Atualizar Keep-alive
    if (elKeepalive && data.keepalive) {
      if (data.keepalive.ativo) {
        elKeepalive.innerHTML = `<i class="fa-solid fa-circle-check"></i> Ativo (${data.keepalive.mensagem})`;
        elKeepalive.style.color = '#2e7d32';
      } else {
        elKeepalive.innerHTML = `<i class="fa-solid fa-triangle-exclamation"></i> Inativo (${data.keepalive.mensagem})`;
        elKeepalive.style.color = '#b91c1c';
      }
    }

    // 3. Renderizar Lista de Logs
    if (containerLogs) {
      const logs = data.logs || [];
      if (logs.length === 0) {
        containerLogs.innerHTML = `
          <div style="text-align: center; padding: 14px; font-size: 11.5px; color: var(--wa-text-secondary);">
            Nenhum evento registrado ainda. As mensagens do chat, atalhos e pings aparecerão aqui em tempo real.
          </div>
        `;
        return;
      }

      containerLogs.innerHTML = logs.slice(0, 10).map(l => {
        let badgeTipo = '';
        if (l.tipo_evento === 'atalho') {
          badgeTipo = `<span style="background: rgba(43,76,60,0.1); color: var(--shanti-primary); font-size: 10px; font-weight: 700; padding: 1px 6px; border-radius: 4px;">⚡ Atalho</span>`;
        } else if (l.tipo_evento === 'chat') {
          badgeTipo = `<span style="background: #ede9fe; color: #6d28d9; font-size: 10px; font-weight: 700; padding: 1px 6px; border-radius: 4px;">💬 Chat</span>`;
        } else if (l.tipo_evento === 'audio') {
          badgeTipo = `<span style="background: #e0f2fe; color: #0369a1; font-size: 10px; font-weight: 700; padding: 1px 6px; border-radius: 4px;">🎙️ Áudio</span>`;
        } else if (l.tipo_evento === 'ping_keepalive') {
          badgeTipo = `<span style="background: #f1f5f9; color: #475569; font-size: 10px; font-weight: 600; padding: 1px 6px; border-radius: 4px;">📡 Ping</span>`;
        } else {
          badgeTipo = `<span style="background: #fef3c7; color: #b45309; font-size: 10px; font-weight: 700; padding: 1px 6px; border-radius: 4px;">🔍 Teste</span>`;
        }

        const hora = (l.timestamp || '').split(' ')[1] || (l.timestamp || '');
        const tempoRender = l.tempo_servidor_ms !== undefined ? `${l.tempo_servidor_ms}ms` : '--';
        const tempoIa = l.tempo_ia_ms !== undefined ? (l.tempo_ia_ms > 0 ? `${l.tempo_ia_ms}ms` : (l.status_ia === 'local' ? 'Local' : '0ms')) : '--';

        return `
          <div style="background: var(--shanti-sand); border: 0.5px solid var(--wa-border); border-radius: 6px; padding: 8px 10px; display: flex; justify-content: space-between; align-items: center; gap: 8px; font-size: 11px;">
            <div style="flex: 1; min-width: 0;">
              <div style="display: flex; align-items: center; gap: 6px; margin-bottom: 2px;">
                ${badgeTipo}
                <span style="color: var(--wa-text-secondary); font-size: 10px;">${hora}</span>
                ${l.servidor_cold_start ? '<span style="font-size: 9.5px; background: #fef3c7; color: #b45309; padding: 0 4px; border-radius: 3px; font-weight: 600;">Cold Start</span>' : ''}
              </div>
              <div style="color: var(--wa-text-primary); font-size: 11px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">
                ${l.mensagem_erro ? `<b style="color: #b91c1c;">Erro:</b> ${l.mensagem_erro}` : (l.detalhes || 'Operação concluída com sucesso')}
              </div>
            </div>
            <div style="text-align: right; white-space: nowrap; font-size: 10.5px;">
              <div>Render: <b>${tempoRender}</b></div>
              <div style="color: var(--shanti-primary);">IA: <b>${tempoIa}</b></div>
            </div>
          </div>
        `;
      }).join('');
    }

  } catch (err) {
    console.warn('Erro ao carregar diagnóstico:', err);
  }
}

async function executarDiagnosticoManual() {
  const btn = document.getElementById('btn-rodar-diagnostico');
  const elIaLatencia = document.getElementById('diag-ia-latencia');
  const elIaModelo = document.getElementById('diag-ia-modelo');
  const elIaMensagem = document.getElementById('diag-ia-mensagem');
  const badgeIa = document.getElementById('badge-diag-ia');
  const badgeGeral = document.getElementById('badge-diag-geral');

  if (!btn) return;
  const originalHtml = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> <span>Testando Servidor e IA Groq...</span>';

  try {
    // 1. Executar testes isolados em paralelo
    const [resServidor, resIa] = await Promise.all([
      fetch('/status-servidor').then(r => r.json()).catch(e => ({ status: 'erro', detail: e.message })),
      fetch('/status-ia').then(r => r.json()).catch(e => ({ status_ia: 'erro', mensagem: e.message, latencia_ms: 0 }))
    ]);

    // 2. Atualizar bloco da IA
    if (resIa) {
      if (elIaLatencia) elIaLatencia.textContent = `${resIa.latencia_ms || 0} ms`;
      if (elIaModelo) elIaModelo.textContent = resIa.modelo || 'Auto';
      if (elIaMensagem) elIaMensagem.textContent = resIa.mensagem || 'Teste concluído.';

      if (badgeIa) {
        if (resIa.status_ia === 'ok') {
          badgeIa.textContent = 'Operando';
          badgeIa.style.background = '#e8f5e9';
          badgeIa.style.color = '#2e7d32';
        } else if (resIa.status_ia === 'lento') {
          badgeIa.textContent = 'Lenta (>3s)';
          badgeIa.style.background = '#fef3c7';
          badgeIa.style.color = '#b45309';
        } else if (resIa.status_ia === 'chave_ausente') {
          badgeIa.textContent = 'Motor Local';
          badgeIa.style.background = '#e0f2fe';
          badgeIa.style.color = '#0369a1';
        } else {
          badgeIa.textContent = 'Erro IA';
          badgeIa.style.background = '#fee2e2';
          badgeIa.style.color = '#b91c1c';
        }
      }
    }

    // 3. Atualizar badge geral do sistema
    if (badgeGeral) {
      if (resServidor.status === 'online' && (resIa.status_ia === 'ok' || resIa.status_ia === 'chave_ausente')) {
        badgeGeral.textContent = '● Tudo Operacional';
        badgeGeral.style.background = '#e8f5e9';
        badgeGeral.style.color = '#2e7d32';
        badgeGeral.style.border = '0.5px solid #a5d6a7';
      } else if (resServidor.cold_start) {
        badgeGeral.textContent = '● Servidor Acordando';
        badgeGeral.style.background = '#fef3c7';
        badgeGeral.style.color = '#b45309';
        badgeGeral.style.border = '0.5px solid #fde68a';
      } else {
        badgeGeral.textContent = '● Atenção';
        badgeGeral.style.background = '#fee2e2';
        badgeGeral.style.color = '#b91c1c';
        badgeGeral.style.border = '0.5px solid #fca5a5';
      }
    }

    // 4. Recarregar tabela de logs e status geral
    await carregarDiagnostico();
    showToast('Diagnóstico do sistema concluído!');

  } catch (err) {
    console.error('Erro ao executar diagnóstico:', err);
    alert('Erro ao executar diagnóstico.');
  } finally {
    btn.disabled = false;
    btn.innerHTML = originalHtml;
  }
}

// =============================================================================
// INSTALAÇÃO DO PWA (WEBAPK NATIVO SEM SÍMBOLO DO CHROME NO ANDROID)
// =============================================================================
let deferredPwaPrompt = null;

function setupPWAInstall() {
  const isStandalone = window.matchMedia('(display-mode: standalone)').matches || window.navigator.standalone === true;

  window.addEventListener('beforeinstallprompt', (e) => {
    e.preventDefault();
    deferredPwaPrompt = e;
    
    if (!isStandalone) {
      const banner = document.getElementById('pwa-install-banner');
      if (banner) banner.style.display = 'flex';
      const headerBtn = document.getElementById('btn-header-install');
      if (headerBtn) headerBtn.style.display = 'inline-flex';
    }
  });

  window.addEventListener('appinstalled', () => {
    deferredPwaPrompt = null;
    const banner = document.getElementById('pwa-install-banner');
    if (banner) banner.style.display = 'none';
    const headerBtn = document.getElementById('btn-header-install');
    if (headerBtn) headerBtn.style.display = 'none';
    const badgeStatus = document.getElementById('badge-pwa-status');
    if (badgeStatus) {
      badgeStatus.textContent = 'Instalado (WebAPK)';
      badgeStatus.style.background = 'var(--shanti-sage-light)';
    }
    showToast('✨ Studio Shanti instalado com sucesso!');
  });

  const acionarInstalacao = async () => {
    if (deferredPwaPrompt) {
      deferredPwaPrompt.prompt();
      const choice = await deferredPwaPrompt.userChoice;
      if (choice && choice.outcome === 'accepted') {
        showToast('Instalando Studio Shanti nativo...');
        const banner = document.getElementById('pwa-install-banner');
        if (banner) banner.style.display = 'none';
        const headerBtn = document.getElementById('btn-header-install');
        if (headerBtn) headerBtn.style.display = 'none';
      }
      deferredPwaPrompt = null;
    } else {
      if (isStandalone) {
        showToast('O aplicativo já está instalado no seu celular!');
      } else {
        alert(
          'Para instalar o aplicativo nativo oficial sem o símbolo do Chrome:\n\n' +
          '1. Toque nos 3 pontinhos do Google Chrome (no canto superior direito).\n' +
          '2. Selecione "Instalar aplicativo" (ou "Adicionar à tela inicial").\n' +
          '3. Toque em "Instalar" na janela de confirmação.\n\n' +
          'O Android gerará o aplicativo oficial sem a marca d\'água do navegador!'
        );
      }
    }
  };

  const btnHeader = document.getElementById('btn-header-install');
  if (btnHeader) btnHeader.addEventListener('click', acionarInstalacao);

  const btnBannerNow = document.getElementById('btn-pwa-install-now');
  if (btnBannerNow) btnBannerNow.addEventListener('click', acionarInstalacao);

  const btnBannerDismiss = document.getElementById('btn-pwa-install-dismiss');
  if (btnBannerDismiss) {
    btnBannerDismiss.addEventListener('click', () => {
      const banner = document.getElementById('pwa-install-banner');
      if (banner) banner.style.display = 'none';
    });
  }

  const btnAjustes = document.getElementById('btn-instalar-app-ajustes');
  if (btnAjustes) btnAjustes.addEventListener('click', acionarInstalacao);
}

// =============================================================================
// FUNÇÕES DE INTEGRAÇÃO COM AUTENTIQUE (ASSINATURAS DIGITAIS)
// =============================================================================


async function testarConexaoAutentique() {
  const resBox = document.getElementById('resultado-teste-autentique');
  const badgeStatus = document.getElementById('badge-autentique-status');
  if (resBox) {
    resBox.style.display = 'block';
    resBox.style.background = '#f8fafc';
    resBox.style.color = '#475569';
    resBox.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Testando comunicação com a API Autentique...';
  }
  
  try {
    const res = await fetch('/api/configuracoes/autentique/testar');
    const data = await res.json();
    
    if (data.sucesso) {
      if (resBox) {
        resBox.style.background = '#f0fdf4';
        resBox.style.border = '1px solid #bbf7d0';
        resBox.style.color = '#15803d';
        resBox.innerHTML = `
          <div style="font-weight:700; margin-bottom: 2px;"><i class="fa-solid fa-circle-check"></i> Conexão Estabelecida!</div>
          <div>${data.mensagem}</div>
          <div style="margin-top:4px; font-size:11px;">Modo Atual: <b>${data.sandbox ? 'Sandbox (Testes Gratuitos)' : 'Produção'}</b></div>
        `;
      }
      if (badgeStatus) {
        badgeStatus.style.background = '#f0fdf4';
        badgeStatus.style.color = '#15803d';
        badgeStatus.style.borderColor = '#bbf7d0';
        badgeStatus.textContent = 'Conectado';
      }
      showToast('Conexão com Autentique validada!');
    } else {
      if (resBox) {
        resBox.style.background = '#fffbeb';
        resBox.style.border = '1px solid #fde68a';
        resBox.style.color = '#b45309';
        resBox.innerHTML = `
          <div style="font-weight:700; margin-bottom: 2px;"><i class="fa-solid fa-triangle-exclamation"></i> Atenção</div>
          <div>${data.mensagem}</div>
        `;
      }
      if (badgeStatus) {
        badgeStatus.style.background = '#fffbeb';
        badgeStatus.style.color = '#b45309';
        badgeStatus.style.borderColor = '#fde68a';
        badgeStatus.textContent = 'Pendente';
      }
    }
  } catch (err) {
    if (resBox) {
      resBox.style.background = '#fef2f2';
      resBox.style.border = '1px solid #fecaca';
      resBox.style.color = '#b91c1c';
      resBox.innerHTML = `<i class="fa-solid fa-circle-xmark"></i> Erro ao testar conexão: ${err.message}`;
    }
  }
}

async function salvarConfigAutentique() {
  const token = document.getElementById('cfg-autentique-token')?.value || '';
  const sandbox = document.getElementById('cfg-autentique-sandbox')?.checked ?? true;
  
  try {
    const res = await fetch('/api/configuracoes/autentique/salvar', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ token, sandbox })
    });
    const data = await res.json();
    showToast('Configurações do Autentique salvas!');
    await testarConexaoAutentique();
  } catch (err) {
    alert(`Erro ao salvar configurações do Autentique: ${err.message}`);
  }
}

function abrirModalEnviarAutentique(alunoId, alunoNome, alunoPlano, alunoTelefone, alunoEmail) {
  document.getElementById('autentique-envio-aluno-id').value = alunoId;
  document.getElementById('autentique-envio-aluno-nome').textContent = alunoNome;
  const contatoAluno = alunoTelefone ? `${alunoTelefone} (Telefone)` : (alunoEmail ? `${alunoEmail} (E-mail)` : 'Contato não informado');
  document.getElementById('autentique-envio-aluno-wa').textContent = contatoAluno;
  
  const sbCheck = document.getElementById('autentique-envio-sandbox');
  if (sbCheck) {
    sbCheck.checked = (state.configuracoes?.autentique_sandbox !== 'false');
  }

  // Verificar se o token da API já está configurado
  const avisoToken = document.getElementById('aviso-token-autentique-modal');
  const tokenAtual = (state.configuracoes?.autentique_api_token || '').trim();
  const tokenValido = tokenAtual.length > 10 && !tokenAtual.includes('mock') && !tokenAtual.includes('placeholder');
  if (avisoToken) {
    avisoToken.style.display = tokenValido ? 'none' : 'block';
  }

  const linkIrAjustes = document.getElementById('link-ir-ajustes-autentique');
  if (linkIrAjustes && !linkIrAjustes._hasListener) {
    linkIrAjustes._hasListener = true;
    linkIrAjustes.addEventListener('click', (e) => {
      e.preventDefault();
      fecharModal('modal-enviar-autentique');
      abrirTela('screen-ajustes');
      setTimeout(() => {
        document.getElementById('card-autentique-config')?.scrollIntoView({ behavior: 'smooth' });
        document.getElementById('cfg-autentique-token')?.focus();
      }, 300);
    });
  }
  
  abrirModal('modal-enviar-autentique');
}

async function confirmarEnvioAutentique(e) {
  e.preventDefault();
  const alunoId = document.getElementById('autentique-envio-aluno-id').value;
  const sandbox = document.getElementById('autentique-envio-sandbox').checked;
  const btnSubmit = document.getElementById('btn-submit-enviar-autentique');
  
  btnSubmit.disabled = true;
  btnSubmit.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Enviando...';
  
  try {
    const res = await fetch(`/api/alunos/${alunoId}/contrato/autentique/enviar`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ sandbox })
    });
    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.detail || 'Erro ao enviar documento ao Autentique.');
    }
    
    fecharModal('modal-enviar-autentique');
    showToast('Contrato enviado com sucesso para assinatura no Autentique!');
    await carregarContratos();
    
    if (data.link_aluno || data.link_natalia) {
      const aluno = (state.contratos || []).find(c => c.id == alunoId) || {};
      abrirModalLinksAutentique(alunoId, aluno.nome || 'Aluno', data.document_id, data.link_aluno, aluno.telefone, data.link_natalia);
    }
  } catch (err) {
    const msg = err.message || '';
    if (msg.includes('Token') || msg.includes('401') || msg.includes('não configurado')) {
      alert(
        '⚠️ Token da API Autentique não configurado ou inválido (HTTP 401).\n\n' +
        'Para disparar contratos eletrônicos pelo celular com validade jurídica, ' +
        'acesse a tela de Ajustes (engrenagem no topo) e insira o Token gratuito da sua conta gerado em painel.autentique.com.br.\n\n' +
        'Redirecionando você para a tela de Ajustes...'
      );
      fecharModal('modal-enviar-autentique');
      abrirTela('screen-ajustes');
      setTimeout(() => {
        document.getElementById('card-autentique-config')?.scrollIntoView({ behavior: 'smooth' });
        document.getElementById('cfg-autentique-token')?.focus();
      }, 300);
    } else {
      alert(`Falha no envio ao Autentique: ${msg}`);
    }
  } finally {
    btnSubmit.disabled = false;
    btnSubmit.innerHTML = '<i class="fa-solid fa-paper-plane"></i> Enviar p/ Autentique';
  }
}

function abrirModalLinksAutentique(alunoId, alunoNome, docId, linkAluno, telefone, linkNatalia) {
  document.getElementById('links-autentique-aluno-id').value = alunoId;
  document.getElementById('links-autentique-aluno-nome').textContent = alunoNome;
  document.getElementById('links-autentique-doc-id').textContent = `Doc ID: ${docId || 'Não informado'}`;
  
  // Etapa 1: Natália (Contratada)
  const btnAbrirNatalia = document.getElementById('btn-abrir-link-natalia');
  if (btnAbrirNatalia) {
    if (linkNatalia) {
      btnAbrirNatalia.href = linkNatalia;
      btnAbrirNatalia.style.pointerEvents = 'auto';
      btnAbrirNatalia.style.opacity = '1';
    } else {
      btnAbrirNatalia.href = '#';
    }
  }

  // Etapa 2: Aluno (Contratante)
  const inputAluno = document.getElementById('links-autentique-aluno-url');
  if (inputAluno) inputAluno.value = linkAluno || '';
  
  let telAluno = (telefone || '').replace(/\D/g, '');
  if (telAluno && !telAluno.startsWith('55')) telAluno = '55' + telAluno;
  
  const btnWaAluno = document.getElementById('btn-wa-link-aluno');
  if (btnWaAluno) {
    const msgAluno = encodeURIComponent(
      `Olá, ${alunoNome}! 🧘‍♀️ Segue o link seguro para assinatura digital do seu Contrato com o Studio Shanti (já assinado pela professora Natália):\n\n` +
      `👉 ${linkAluno || ''}\n\n` +
      `Basta tocar no link e assinar direto na tela do seu celular! Namastê. 🙏`
    );
    btnWaAluno.href = `https://wa.me/${telAluno}?text=${msgAluno}`;
  }

  // URL do PDF Assinado
  const urlAssinadoPadrao = docId ? `https://api.autentique.com.br/documentos/${docId}/assinado.pdf` : '';
  const inputPdfAssinado = document.getElementById('links-autentique-pdf-assinado-url');
  if (inputPdfAssinado) inputPdfAssinado.value = urlAssinadoPadrao;

  const btnAbrirPdf = document.getElementById('btn-abrir-pdf-assinado');
  if (btnAbrirPdf) btnAbrirPdf.href = urlAssinadoPadrao || '#';

  const btnWaPdf = document.getElementById('btn-wa-pdf-assinado');
  if (btnWaPdf && urlAssinadoPadrao) {
    const msgFinal = encodeURIComponent(
      `📜 *CONTRATO DE MATRÍCULA ASSINADO - Studio Shanti* 🧘‍♀️✨\n\n` +
      `Olá, *${alunoNome}*!\n\n` +
      `O seu Contrato de Prestação de Serviços com o Studio Shanti foi *concluído e assinado digitalmente por ambas as partes* (Professora Natália e Aluno)!\n\n` +
      `📄 *Acesse e baixe a sua via oficial assinada (PDF):*\n` +
      `👉 ${urlAssinadoPadrao}\n\n` +
      `Este documento possui certificação digital e plena validade jurídica. Guarde-o com você para seu arquivo pessoal!\n\n` +
      `Seja muito bem-vindo(a) e tenha ótimas práticas! Namastê. 🙏🌿`
    );
    btnWaPdf.href = `https://wa.me/${telAluno}?text=${msgFinal}`;
  }
  
  // Estado inicial visual
  const etapaBadge = document.getElementById('links-autentique-etapa-badge');
  if (etapaBadge) {
    etapaBadge.className = 'wa-badge';
    etapaBadge.style.background = '#fffbeb';
    etapaBadge.style.color = '#b45309';
    etapaBadge.style.border = '1px solid #fde68a';
    etapaBadge.textContent = '1ª Etapa: Natália';
  }

  const box = document.getElementById('links-autentique-status-box');
  if (box) {
    box.style.background = '#f8fcf9';
    box.style.borderColor = '#dcfce7';
    box.style.color = 'var(--shanti-charcoal)';
    box.innerHTML = '<i class="fa-solid fa-spinner fa-spin" style="color:var(--shanti-sage);"></i> Consultando status atualizado...';
  }

  abrirModal('modal-links-autentique');

  // Consulta em tempo real para sincronizar status atual do documento
  verificarStatusAutentique(alunoId, false);
}

async function verificarStatusAutentique(alunoId, showToastAlert = true) {
  const btnSinc = document.getElementById('btn-sincronizar-autentique');
  if (btnSinc) {
    btnSinc.disabled = true;
    btnSinc.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Consultando...';
  }
  
  try {
    const res = await fetch(`/api/alunos/${alunoId}/contrato/autentique/status`);
    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.detail || 'Erro ao consultar status no Autentique.');
    }
    
    // Atualizar links da Natália e do Aluno se vierem na resposta
    const btnAbrirNat = document.getElementById('btn-abrir-link-natalia');
    if (data.link_natalia && btnAbrirNat) {
      btnAbrirNat.href = data.link_natalia;
    }
    if (data.link_aluno) {
      const inputAluno = document.getElementById('links-autentique-aluno-url');
      if (inputAluno) inputAluno.value = data.link_aluno;
    }

    const badgeNatalia = document.getElementById('status-natalia-badge');
    const badgeAluno = document.getElementById('status-aluno-badge');
    const avisoBloqueado = document.getElementById('aviso-aluno-bloqueado');
    const areaEnvioAluno = document.getElementById('area-envio-aluno');
    const areaFinalizado = document.getElementById('area-contrato-finalizado');
    const etapaBadge = document.getElementById('links-autentique-etapa-badge');
    const box = document.getElementById('links-autentique-status-box');

    const nataliaAssinou = Boolean(data.natalia_assinou);
    const alunoAssinou = Boolean(data.aluno_assinou);
    const finalizado = Boolean(data.finalizado) || (nataliaAssinou && alunoAssinou);
    const urlAssinado = data.url_assinado || (data.document_id ? `https://api.autentique.com.br/documentos/${data.document_id}/assinado.pdf` : '');

    const alunoObj = (state.contratos || []).find(c => c.id == alunoId) || {};
    const alunoNome = alunoObj.nome || document.getElementById('links-autentique-aluno-nome')?.textContent || 'Aluno';
    let telAluno = (alunoObj.telefone || '').replace(/\D/g, '');
    if (telAluno && !telAluno.startsWith('55')) telAluno = '55' + telAluno;

    // 1. Atualizar card da Natália
    const areaAcaoNatPendente = document.getElementById('area-acao-natalia-pendente');
    const areaAcaoNatAssinado = document.getElementById('area-acao-natalia-assinado');
    if (nataliaAssinou) {
      if (badgeNatalia) {
        badgeNatalia.style.background = '#dcfce7';
        badgeNatalia.style.color = '#15803d';
        badgeNatalia.innerHTML = '<i class="fa-solid fa-check"></i> Assinado';
      }
      if (areaAcaoNatPendente) areaAcaoNatPendente.style.display = 'none';
      if (areaAcaoNatAssinado) areaAcaoNatAssinado.style.display = 'flex';
    } else {
      if (badgeNatalia) {
        badgeNatalia.style.background = '#fffbeb';
        badgeNatalia.style.color = '#b45309';
        badgeNatalia.innerHTML = '⏳ Pendente';
      }
      if (areaAcaoNatPendente) areaAcaoNatPendente.style.display = 'block';
      if (areaAcaoNatAssinado) areaAcaoNatAssinado.style.display = 'none';
      if (btnAbrirNat && data.link_natalia) {
        btnAbrirNat.href = data.link_natalia;
      }
    }

    // 2. Atualizar card do Aluno
    if (!nataliaAssinou) {
      if (avisoBloqueado) avisoBloqueado.style.display = 'block';
      if (areaEnvioAluno) areaEnvioAluno.style.display = 'none';
      if (areaFinalizado) areaFinalizado.style.display = 'none';
      if (badgeAluno) {
        badgeAluno.style.background = '#f3f4f6';
        badgeAluno.style.color = '#6b7280';
        badgeAluno.innerHTML = 'Aguardando Natália';
      }
    } else if (finalizado) {
      if (avisoBloqueado) avisoBloqueado.style.display = 'none';
      if (areaEnvioAluno) areaEnvioAluno.style.display = 'none';
      if (areaFinalizado) areaFinalizado.style.display = 'block';
      if (badgeAluno) {
        badgeAluno.style.background = '#dcfce7';
        badgeAluno.style.color = '#15803d';
        badgeAluno.innerHTML = '<i class="fa-solid fa-check"></i> Assinado';
      }

      // Preencher URL do PDF Assinado
      const inputPdfAssinado = document.getElementById('links-autentique-pdf-assinado-url');
      if (inputPdfAssinado && urlAssinado) inputPdfAssinado.value = urlAssinado;

      const btnAbrirPdf = document.getElementById('btn-abrir-pdf-assinado');
      if (btnAbrirPdf && urlAssinado) btnAbrirPdf.href = urlAssinado;

      const btnWaPdf = document.getElementById('btn-wa-pdf-assinado');
      if (btnWaPdf && urlAssinado) {
        const msgFinal = encodeURIComponent(
          `📜 *CONTRATO DE MATRÍCULA ASSINADO - Studio Shanti* 🧘‍♀️✨\n\n` +
          `Olá, *${alunoNome}*!\n\n` +
          `O seu Contrato de Prestação de Serviços com o Studio Shanti foi *concluído e assinado digitalmente por ambas as partes* (Professora Natália e Aluno)!\n\n` +
          `📄 *Acesse e baixe a sua via oficial assinada (PDF):*\n` +
          `👉 ${urlAssinado}\n\n` +
          `Este documento possui certificação digital e plena validade jurídica. Guarde-o com você para seu arquivo pessoal!\n\n` +
          `Seja muito bem-vindo(a) e tenha ótimas práticas! Namastê. 🙏🌿`
        );
        btnWaPdf.href = `https://wa.me/${telAluno}?text=${msgFinal}`;
      }
    } else {
      // Natália assinou, aluno pendente de assinar
      if (avisoBloqueado) avisoBloqueado.style.display = 'none';
      if (areaEnvioAluno) areaEnvioAluno.style.display = 'block';
      if (areaFinalizado) areaFinalizado.style.display = 'none';
      if (badgeAluno) {
        badgeAluno.style.background = '#eff6ff';
        badgeAluno.style.color = '#1e40af';
        badgeAluno.innerHTML = '⏳ Pronto p/ Envio';
      }

      const inputAluno = document.getElementById('links-autentique-aluno-url');
      if (inputAluno && data.link_aluno) inputAluno.value = data.link_aluno;

      const btnWaAluno = document.getElementById('btn-wa-link-aluno');
      if (btnWaAluno) {
        const linkAlunoReal = data.link_aluno || inputAluno?.value || '';
        const msgAssinatura = encodeURIComponent(
          `Olá, ${alunoNome}! 🧘‍♀️ Segue o link seguro para assinatura digital do seu Contrato com o Studio Shanti (já assinado pela professora Natália):\n\n` +
          `👉 ${linkAlunoReal}\n\n` +
          `Basta tocar no link e assinar direto na tela do seu celular! Assim que concluir, o sistema confirmará automaticamente. Namastê. 🙏`
        );
        btnWaAluno.href = `https://wa.me/${telAluno}?text=${msgAssinatura}`;
      }
    }

    // 3. Atualizar Status Box e Etapa Badge
    if (finalizado) {
      if (etapaBadge) {
        etapaBadge.style.background = '#dcfce7';
        etapaBadge.style.color = '#15803d';
        etapaBadge.style.border = '1px solid #86efac';
        etapaBadge.innerHTML = '✓ Concluído';
      }
      if (box) {
        box.style.background = '#f0fdf4';
        box.style.borderColor = '#bbf7d0';
        box.style.color = '#15803d';
        box.innerHTML = '<i class="fa-solid fa-circle-check"></i> <b>Contrato 100% Assinado!</b> Ambas as partes assinaram com sucesso. Documento validado com 1 ano de vigência.';
      }
      if (showToastAlert) showToast('Contrato assinado e atualizado para "Em Dia"!');
      await carregarContratos();
    } else if (!nataliaAssinou) {
      if (etapaBadge) {
        etapaBadge.style.background = '#fffbeb';
        etapaBadge.style.color = '#b45309';
        etapaBadge.style.border = '1px solid #fde68a';
        etapaBadge.innerHTML = '1ª Etapa: Natália';
      }
      if (box) {
        box.style.background = '#fffbeb';
        box.style.borderColor = '#fde68a';
        box.style.color = '#92400e';
        box.innerHTML = '<i class="fa-solid fa-hourglass-start"></i> <b>Etapa 1 de 2:</b> Aguardando assinatura da Natália para liberar envio ao aluno.';
      }
      if (showToastAlert) showToast('Aguardando assinatura da Professora Natália.');
    } else {
      if (etapaBadge) {
        etapaBadge.style.background = '#eff6ff';
        etapaBadge.style.color = '#1e40af';
        etapaBadge.style.border = '1px solid #bfdbfe';
        etapaBadge.innerHTML = '2ª Etapa: Aluno';
      }
      if (box) {
        box.style.background = '#eff6ff';
        box.style.borderColor = '#bfdbfe';
        box.style.color = '#1e40af';
        box.innerHTML = '<i class="fa-solid fa-paper-plane"></i> <b>Etapa 2 de 2:</b> Natália já assinou! Envie o link acima ao aluno pelo WhatsApp.';
      }
      if (showToastAlert) showToast('Natália já assinou! Envio ao aluno liberado.');
    }
  } catch (err) {
    if (showToastAlert) alert(`Erro ao sincronizar: ${err.message}`);
  } finally {
    if (btnSinc) {
      btnSinc.disabled = false;
      btnSinc.innerHTML = '<i class="fa-solid fa-rotate"></i> Sincronizar Status';
    }
  }
}

// ABA CONTRATOS: GESTÃO DE CONTRATOS DIGITAIS, UPLOADS & RENOVAÇÕES (FASE 4)
// =============================================================================

async function carregarContratos() {
  try {
    const res = await fetch('/api/contratos');
    state.contratos = await res.json();

    const resAlertas = await fetch('/api/contratos/alertas');
    const alertas = await resAlertas.json();

    // Atualizar Contadores
    const statEmDia = document.getElementById('stat-contratos-em-dia');
    const statAVencer = document.getElementById('stat-contratos-a-vencer');
    const statPendentes = document.getElementById('stat-contratos-pendentes');
    const statVencidos = document.getElementById('stat-contratos-vencidos');

    if (statEmDia) statEmDia.textContent = alertas.em_dia || 0;
    if (statAVencer) statAVencer.textContent = alertas.a_vencer || 0;
    if (statPendentes) statPendentes.textContent = alertas.pendentes || 0;
    if (statVencidos) statVencidos.textContent = alertas.vencidos || 0;

    // Badge na Aba Contratos
    const badgeAba = document.getElementById('badge-contratos-alert');
    if (badgeAba) {
      if (alertas.a_vencer > 0) {
        badgeAba.textContent = alertas.a_vencer;
        badgeAba.style.display = 'inline-block';
      } else {
        badgeAba.style.display = 'none';
      }
    }

    // Banner de Alerta (30 dias)
    const banner = document.getElementById('banner-alerta-contratos');
    const bannerTitulo = document.getElementById('banner-alerta-titulo');
    const bannerDesc = document.getElementById('banner-alerta-desc');
    if (banner) {
      if (alertas.a_vencer > 0) {
        banner.style.display = 'block';
        if (bannerTitulo) bannerTitulo.textContent = `Atenção: ${alertas.a_vencer} contrato(s) com menos de 30 dias para vencer!`;
        if (bannerDesc) {
          const nomes = alertas.alunos_a_vencer.map(a => a.nome).join(', ');
          bannerDesc.textContent = `Aluno(s) em período de renovação anual: ${nomes}. Entre em contato para renovar o contrato.`;
        }
      } else if (alertas.vencidos > 0) {
        banner.style.display = 'block';
        if (bannerTitulo) bannerTitulo.textContent = `Atenção: ${alertas.vencidos} contrato(s) vencido(s)!`;
        if (bannerDesc) bannerDesc.textContent = 'Existem contratos cuja vigência anual encerrou. É necessário emitir e assinar um novo termo de renovação.';
      } else {
        banner.style.display = 'none';
      }
    }

    renderizarContratos();
  } catch (err) {
    console.error('Erro ao carregar contratos:', err);
  }
}

function filtrarContratos(tipo) {
  state.currentContractFilter = tipo;
  document.querySelectorAll('#screen-contratos .wa-filter-chip').forEach(chip => {
    chip.classList.remove('active');
  });
  const activeChip = document.getElementById(`chip-contrato-${tipo}`);
  if (activeChip) activeChip.classList.add('active');
  renderizarContratos();
}

function filtrarContratosTexto(query) {
  renderizarContratos();
}

function renderizarContratos() {
  const container = document.getElementById('lista-contratos-container');
  if (!container) return;

  const busca = (document.getElementById('input-busca-contrato')?.value || '').toLowerCase();
  const filtro = state.currentContractFilter || 'todos';

  let lista = (state.contratos || []).filter(c => {
    const matchBusca = (c.nome || '').toLowerCase().includes(busca) || (c.cpf || '').includes(busca) || (c.telefone || '').includes(busca);
    if (!matchBusca) return false;

    if (filtro === 'em_dia') return c.status_contrato === 'em_dia';
    if (filtro === 'a_vencer') return c.status_contrato === 'a_vencer';
    if (filtro === 'pendente') return c.status_contrato === 'pendente';
    if (filtro === 'vencido') return c.status_contrato === 'vencido';
    return true;
  });

  if (lista.length === 0) {
    container.innerHTML = `
      <div style="padding: 40px 20px; text-align: center; color: var(--shanti-stone); background: #ffffff; border-radius: 16px; border: 1px dashed var(--shanti-sand-border);">
        <i class="fa-solid fa-file-circle-question" style="font-size: 36px; color: var(--shanti-sand); margin-bottom: 10px; display:block;"></i>
        <p style="font-size: 14px; font-weight: 600; margin-bottom: 4px; color: var(--shanti-charcoal);">Nenhum contrato encontrado</p>
        <p style="font-size: 12.5px; margin: 0; color: var(--shanti-stone);">Altere o filtro selecionado ou faça uma nova busca por nome ou CPF.</p>
      </div>
    `;
    return;
  }

  container.innerHTML = lista.map(c => {
    let badgeClass = 'badge-contrato-pendente';
    let badgeTexto = 'Pendente de Assinatura';
    let badgeIcon = 'fa-solid fa-hourglass-half';

    const temArquivo = Boolean(c.contrato_assinado_arquivo);
    const temAutentique = Boolean(c.autentique_doc_id);
    const estaEmDia = c.status_contrato === 'em_dia' || temArquivo;

    if (c.status_contrato === 'em_dia') {
      badgeClass = 'badge-contrato-em-dia';
      badgeTexto = 'Em Dia';
      badgeIcon = 'fa-solid fa-circle-check';
    } else if (c.status_contrato === 'a_vencer') {
      badgeClass = 'badge-contrato-a-vencer';
      badgeTexto = `Vence em ${c.dias_restantes} dias`;
      badgeIcon = 'fa-solid fa-triangle-exclamation';
    } else if (c.status_contrato === 'vencido') {
      badgeClass = 'badge-contrato-vencido';
      badgeTexto = 'Contrato Vencido';
      badgeIcon = 'fa-solid fa-circle-exclamation';
    } else if (temAutentique) {
      badgeClass = 'badge-contrato-a-vencer';
      if (c.autentique_status === 'aguardando_natalia') {
        badgeTexto = 'Autentique: 1ª Etapa (Natália)';
        badgeIcon = 'fa-solid fa-pen-nib';
      } else if (c.autentique_status === 'aguardando_aluno') {
        badgeTexto = 'Autentique: 2ª Etapa (Aluno)';
        badgeIcon = 'fa-solid fa-paper-plane';
      } else if (c.autentique_status === 'assinado' || c.autentique_status === 'concluido') {
        badgeTexto = 'Autentique: Concluído';
        badgeIcon = 'fa-solid fa-circle-check';
      } else {
        badgeTexto = 'Autentique: Aguardando';
        badgeIcon = 'fa-solid fa-clock-rotate-left';
      }
    }

    let vigenciaTexto = 'Aguardando documento assinado por ambas as partes';
    if (c.data_vigencia_contrato) {
      const diasRest = c.dias_restantes != null ? `(${c.dias_restantes} dias restantes)` : '';
      vigenciaTexto = `Vigência até ${formatarDataBR(c.data_vigencia_contrato)} ${diasRest}`;
    } else if (temAutentique) {
      if (c.autentique_status === 'aguardando_natalia') {
        vigenciaTexto = 'Autentique: Aguardando assinatura da Natália (Etapa 1)';
      } else if (c.autentique_status === 'aguardando_aluno') {
        vigenciaTexto = 'Autentique: Natália assinou! Pronto para envio ao aluno (Etapa 2)';
      } else {
        vigenciaTexto = 'Enviado para assinatura digital no Autentique (WhatsApp)';
      }
    }

    let tel = (c.telefone || '').replace(/\D/g, '');
    if (tel && !tel.startsWith('55')) tel = '55' + tel;

    let msgWa;
    let btnWaTexto = 'WhatsApp';
    let btnWaIcon = 'fa-brands fa-whatsapp';

    if (estaEmDia) {
      const linkPdfAssinado = c.autentique_doc_id
        ? `https://api.autentique.com.br/documentos/${c.autentique_doc_id}/assinado.pdf`
        : `${window.location.origin}/api/alunos/${c.id}/contrato/arquivo`;
      msgWa = encodeURIComponent(
        `📜 *CONTRATO DE MATRÍCULA ASSINADO - Studio Shanti* 🧘‍♀️✨\n\n` +
        `Olá, *${c.nome}*!\n\n` +
        `O seu Contrato de Prestação de Serviços com o Studio Shanti foi *concluído e assinado digitalmente por ambas as partes* (Professora Natália e Aluno)!\n\n` +
        `📄 *Acesse e baixe a sua via oficial assinada (PDF):*\n` +
        `👉 ${linkPdfAssinado}\n\n` +
        `Este documento possui certificação digital e plena validade jurídica. Guarde-o com você para seu arquivo pessoal!\n\n` +
        `Seja muito bem-vindo(a) e tenha ótimas práticas! Namastê. 🙏🌿`
      );
      btnWaTexto = 'Enviar Via Assinada';
    } else {
      msgWa = encodeURIComponent(
        `Olá, ${c.nome}! 🧘‍♀️ Aqui é do Studio Shanti de Yoga.\n\n` +
        `Estamos enviando a minuta do seu Contrato de Prestação de Serviços de Yoga (${c.plano}).\n\n` +
        `Você pode conferir a minuta no link:\n` +
        `${window.location.origin}/api/alunos/${c.id}/contrato/pdf\n\n` +
        `Assim que estiver assinado por você e pela professora Natália, arquivamos a via mútua no estúdio.\n\nNamastê! 🙏`
      );
      btnWaTexto = 'WhatsApp (Minuta)';
    }
    const linkWa = `https://wa.me/${tel}?text=${msgWa}`;

    return `
      <div class="wa-card" style="margin-bottom: 0; border: 1px solid var(--shanti-sand-border); border-radius: 16px; box-shadow: var(--shadow-sm); padding: 16px;">
        <div style="display: flex; justify-content: space-between; align-items: flex-start; gap: 10px; margin-bottom: 10px;">
          <div>
            <div style="font-size: 15px; font-weight: 700; color: var(--shanti-charcoal); display: flex; align-items: center; gap: 6px; font-family: var(--font-brand);">
              ${c.nome}
              ${c.aprovacao_pagamento === 'pendente' ? `
                <span class="wa-student-badge" style="background:#FDF3E7; color:#B45309; border:1px solid #F6D6B2; font-size:10.5px;">Matrícula Pendente</span>
              ` : ''}
            </div>
            <div style="font-size: 12px; color: var(--shanti-stone); margin-top: 2px;">
              CPF: <b>${c.cpf || 'Não informado'}</b> • WhatsApp: <b>${c.telefone}</b>
            </div>
          </div>
          <span class="wa-student-badge ${badgeClass}" style="font-size: 11px; white-space: nowrap;">
            <i class="${badgeIcon}"></i> ${badgeTexto}
          </span>
        </div>

        <div style="background: var(--shanti-sand-light); border: 1px solid var(--shanti-sand-border); border-radius: 12px; padding: 10px 14px; font-size: 12px; color: var(--shanti-charcoal); margin-bottom: 12px; line-height: 1.5;">
          <div><b>Plano:</b> ${c.plano} • <b>Turma:</b> ${c.turmas && c.turmas.length ? c.turmas.map(t => t.nome).join(', ') : 'Nenhuma turma'}</div>
          <div><b>Status Vigência:</b> <span style="color: var(--shanti-forest); font-weight: 600;">${vigenciaTexto}</span></div>
          <div><b>Arquivo Assinado:</b> ${temArquivo ? '<span style="color:#3F4E3A; font-weight:600;"><i class="fa-solid fa-check-circle"></i> Anexado (mútuo)</span>' : '<span style="color:var(--shanti-terracotta);">Nenhum arquivo enviado</span>'}</div>
          ${c.autentique_doc_id ? `
            <div style="margin-top: 2px;">
              <b>Assinatura Digital:</b> 
              ${c.autentique_status === 'assinado'
                ? '<span style="color:#3F4E3A; font-weight:600;"><i class="fa-solid fa-shield-check"></i> Assinado via Autentique</span>'
                : c.autentique_status === 'aguardando_natalia'
                ? '<span style="color:#b45309; font-weight:600;"><i class="fa-solid fa-hourglass-start"></i> Autentique (Etapa 1: Natália pendente)</span>'
                : c.autentique_status === 'aguardando_aluno'
                ? '<span style="color:#1e40af; font-weight:600;"><i class="fa-solid fa-paper-plane"></i> Autentique (Etapa 2: Liberado p/ Aluno)</span>'
                : `<span style="color:var(--shanti-forest); font-weight:600;"><i class="fa-solid fa-clock-rotate-left"></i> Autentique (${c.autentique_status || 'Aguardando'})</span>`
              }
            </div>
          ` : ''}
        </div>

        <div style="display: flex; gap: 6px; flex-wrap: wrap;">
          ${!estaEmDia && !temAutentique ? `
            <button type="button" class="wa-btn-primary" style="flex: 1; min-width: 130px; padding: 7px 12px; font-size: 12px; background: var(--shanti-forest); color: #FFFFFF; border: none; border-radius: 20px; font-weight: 600; box-shadow: var(--shadow-sm);" onclick="abrirModalEnviarAutentique(${c.id}, '${c.nome.replace(/'/g, "\\'")}', '${(c.plano || '').replace(/'/g, "\\'")}', '${c.telefone || ''}', '${c.email || ''}')">
              <i class="fa-solid fa-paper-plane"></i> Enviar p/ Autentique
            </button>
          ` : ''}

          ${temAutentique ? `
            <button type="button" class="wa-btn-primary" style="flex: 1; min-width: 110px; padding: 7px 12px; font-size: 12px; background: ${estaEmDia ? 'var(--shanti-forest)' : 'var(--shanti-sage)'}; color: #FFFFFF; border: none; border-radius: 20px; font-weight: 600;" onclick="abrirModalLinksAutentique(${c.id}, '${c.nome.replace(/'/g, "\\'")}', '${c.autentique_doc_id}', '${c.autentique_link || ''}', '${c.telefone || ''}', '${c.autentique_link_natalia || ''}')">
              <i class="fa-solid ${estaEmDia ? 'fa-file-circle-check' : 'fa-link'}"></i> ${estaEmDia ? 'Autentique' : 'Links / WA'}
            </button>
            <button type="button" class="wa-btn-primary" style="flex: 1; min-width: 95px; padding: 7px 12px; font-size: 12px; background: #FFFFFF; color: var(--shanti-forest); border: 1px solid var(--shanti-sand-border); border-radius: 20px; font-weight: 600;" onclick="verificarStatusAutentique(${c.id}, true)" title="Consultar status no Autentique">
              <i class="fa-solid fa-rotate"></i> Sincronizar
            </button>
          ` : ''}

          ${!estaEmDia ? `
            <a href="/api/alunos/${c.id}/contrato/pdf" target="_blank" class="wa-btn-primary" style="flex: 1; min-width: 80px; padding: 7px 12px; font-size: 12px; background: var(--shanti-sand-light); color: var(--shanti-charcoal); border: 1px solid var(--shanti-sand-border); border-radius: 20px; font-weight: 600; text-decoration: none; display: inline-flex; align-items: center; justify-content: center; gap: 5px;">
              <i class="fa-solid fa-file-pdf" style="color: var(--shanti-terracotta);"></i> Minuta
            </a>
          ` : ''}

          <a href="${linkWa}" target="_blank" class="wa-btn-primary" style="flex: 1; min-width: 125px; padding: 7px 12px; font-size: 12px; background: var(--shanti-whatsapp-green); color: #FFFFFF; border: none; border-radius: 20px; font-weight: 600; text-decoration: none; display: inline-flex; align-items: center; justify-content: center; gap: 5px; box-shadow: 0 2px 8px rgba(37, 211, 102, 0.25);">
            <i class="${btnWaIcon}"></i> ${btnWaTexto}
          </a>

          <button type="button" class="wa-btn-primary" style="flex: 1; min-width: 110px; padding: 7px 12px; font-size: 12px; background: var(--shanti-terracotta); color: #FFFFFF; border: none; border-radius: 20px; font-weight: 600; box-shadow: var(--shadow-sm);" onclick="abrirModalUploadContrato(${c.id}, '${c.nome.replace(/'/g, "\\'")}', '${(c.plano || '').replace(/'/g, "\\'")}')">
            <i class="fa-solid fa-cloud-arrow-up"></i> ${temArquivo ? 'Substituir' : 'Upload Manual'}
          </button>

          ${temArquivo ? `
            <a href="/api/alunos/${c.id}/contrato/arquivo" target="_blank" class="wa-btn-primary" style="padding: 7px 12px; font-size: 12px; background: #FFFFFF; color: var(--shanti-forest); border: 1px solid var(--shanti-sand-border); border-radius: 20px; font-weight: 600; text-decoration: none; display: inline-flex; align-items: center; justify-content: center; gap: 5px;" title="Visualizar documento assinado">
              <i class="fa-solid fa-eye"></i> Ver
            </a>
            <button type="button" class="wa-btn-primary" style="padding: 7px 12px; font-size: 12px; background: #FFFFFF; color: var(--shanti-terracotta); border: 1px solid var(--shanti-terracotta-border); border-radius: 20px;" onclick="removerContratoAssinado(${c.id}, '${c.nome.replace(/'/g, "\\'")}')" title="Excluir arquivo de contrato">
              <i class="fa-solid fa-trash-can"></i>
            </button>
          ` : ''}
        </div>
      </div>
    `;
  }).join('');
}

function abrirModalUploadContrato(alunoId, alunoNome, alunoPlano) {
  document.getElementById('upload-contrato-aluno-id').value = alunoId;
  document.getElementById('upload-contrato-aluno-nome').textContent = alunoNome;
  document.getElementById('upload-contrato-aluno-info').textContent = alunoPlano || 'Plano de Yoga';
  const fileInput = document.getElementById('upload-contrato-arquivo');
  if (fileInput) fileInput.value = '';
  abrirModal('modal-upload-contrato');
}

async function removerContratoAssinado(alunoId, alunoNome) {
  if (!confirm(`Deseja remover o arquivo de contrato assinado de "${alunoNome}"? O status voltará a ser "Pendente".`)) {
    return;
  }
  try {
    const res = await fetch(`/api/alunos/${alunoId}/contrato/arquivo`, { method: 'DELETE' });
    if (res.ok) {
      showToast('Arquivo de contrato removido.');
      await atualizarTudo();
      if (state.alunoSelecionado && state.alunoSelecionado.id === parseInt(alunoId)) {
        await abrirDetalhesAluno(alunoId);
      }
    } else {
      showToast('Erro ao remover contrato.');
    }
  } catch (err) {
    showToast('Falha na comunicação com o servidor.');
  }
}

async function aprovarPagamentoMatricula(alunoId, alunoNome) {
  if (!confirm(`Confirmar o recebimento da 1ª mensalidade de "${alunoNome}"?\n\nIsto irá ativar a matrícula e lançar automaticamente a mensalidade como PAGA no sistema financeiro ("Entrou, Pagou").`)) {
    return;
  }

  try {
    const res = await fetch(`/api/alunos/${alunoId}/aprovar-pagamento`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ forma_pagamento: 'PIX' })
    });
    const data = await res.json();
    if (res.ok) {
      showToast(data.mensagem || 'Matrícula aprovada e mensalidade lançada com sucesso!');
      await atualizarTudo();
      if (state.alunoSelecionado && state.alunoSelecionado.id === parseInt(alunoId)) {
        await abrirDetalhesAluno(alunoId);
      }
    } else {
      alert(data.detail || 'Erro ao aprovar pagamento.');
    }
  } catch (err) {
    alert('Erro ao comunicar com o servidor.');
  }
}

// =============================================================================
// MÓDULO CALENDÁRIO, CHAMADA & RETENÇÃO (FASE CALENDÁRIO)
// =============================================================================

function setupCalendario() {
  const btnPrev = document.getElementById('btn-cal-prev');
  const btnNext = document.getElementById('btn-cal-next');
  const btnToday = document.getElementById('btn-cal-today');

  if (btnPrev) {
    btnPrev.addEventListener('click', () => mudarMesCalendario(-1));
  }
  if (btnNext) {
    btnNext.addEventListener('click', () => mudarMesCalendario(1));
  }
  if (btnToday) {
    btnToday.addEventListener('click', () => irParaHoje());
  }

  // Abertura do Seletor Direto de Mês e Ano
  const btnAbrirSeletor = document.getElementById('btn-abrir-seletor-mes-ano');
  if (btnAbrirSeletor) {
    btnAbrirSeletor.addEventListener('click', () => abrirSeletorMesAno());
  }

  const btnPickerPrevYear = document.getElementById('btn-picker-prev-year');
  if (btnPickerPrevYear) {
    btnPickerPrevYear.addEventListener('click', () => {
      pickerAno--;
      renderizarSeletorMesAno();
    });
  }

  const btnPickerNextYear = document.getElementById('btn-picker-next-year');
  if (btnPickerNextYear) {
    btnPickerNextYear.addEventListener('click', () => {
      pickerAno++;
      renderizarSeletorMesAno();
    });
  }

  const selectPickerYear = document.getElementById('picker-select-year');
  if (selectPickerYear) {
    selectPickerYear.addEventListener('change', (e) => {
      pickerAno = parseInt(e.target.value);
      renderizarSeletorMesAno();
    });
  }

  const btnPickerToday = document.getElementById('btn-picker-go-today');
  if (btnPickerToday) {
    btnPickerToday.addEventListener('click', () => {
      fecharModal('modal-cal-picker');
      irParaHoje();
    });
  }

  const btnConfirmarPausa = document.getElementById('btn-confirmar-pausa-alerta');
  if (btnConfirmarPausa) {
    btnConfirmarPausa.addEventListener('click', () => salvarPausaAlerta());
  }
}

let pickerAno = new Date().getFullYear();

function abrirSeletorMesAno() {
  pickerAno = state.calendario.ano;
  renderizarSeletorMesAno();
  abrirModal('modal-cal-picker');
}

function renderizarSeletorMesAno() {
  const selectYear = document.getElementById('picker-select-year');
  if (selectYear) {
    let optHtml = '';
    const anoAtual = new Date().getFullYear();
    for (let y = anoAtual - 6; y <= anoAtual + 6; y++) {
      optHtml += `<option value="${y}" ${y === pickerAno ? 'selected' : ''}>${y}</option>`;
    }
    selectYear.innerHTML = optHtml;
    selectYear.value = pickerAno;
  }

  const grid = document.getElementById('picker-months-grid');
  if (!grid) return;

  const mesesNomes = [
    'Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho',
    'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro'
  ];
  const hoje = new Date();
  const anoHoje = hoje.getFullYear();
  const mesHoje = hoje.getMonth() + 1;

  let gridHtml = '';
  mesesNomes.forEach((nome, idx) => {
    const numMes = idx + 1;
    const ehAtivo = (pickerAno === state.calendario.ano && numMes === state.calendario.mes);
    const ehAtual = (pickerAno === anoHoje && numMes === mesHoje);

    let classes = ['picker-month-btn'];
    if (ehAtivo) classes.push('selected');
    if (ehAtual) classes.push('current');

    gridHtml += `
      <button type="button" class="${classes.join(' ')}" onclick="selecionarMesAnoDireto(${pickerAno}, ${numMes})" title="${nome} de ${pickerAno}">
        ${nome.slice(0, 3)}
      </button>
    `;
  });

  grid.innerHTML = gridHtml;
}

function selecionarMesAnoDireto(ano, mes) {
  state.calendario.ano = ano;
  state.calendario.mes = mes;
  fecharModal('modal-cal-picker');
  carregarCalendario();
}

async function carregarCalendario() {
  try {
    const ano = state.calendario.ano;
    const mes = state.calendario.mes;

    const res = await fetch(`/api/calendario/mes?ano=${ano}&mes=${mes}`);
    const dados = await res.json();
    state.calendario.dadosMes = dados;

    const mesesNomes = [
      'Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho',
      'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro'
    ];
    const elTituloMes = document.getElementById('cal-month-name');
    if (elTituloMes) {
      elTituloMes.textContent = `${mesesNomes[mes - 1]} ${ano}`;
    }

    const elSummary = document.getElementById('cal-month-summary');
    if (elSummary) {
      const rm = dados.resumo_mes || {};
      elSummary.textContent = `${rm.total_dias_com_aula || 0} dias com aula • ${rm.total_presencas || 0} presenças registradas`;
    }

    renderizarGradeCalendario(dados);

    const hoje = new Date();
    const hojeStr = hoje.toISOString().slice(0, 10);
    const mesmoMes = (hoje.getFullYear() === ano && (hoje.getMonth() + 1) === mes);

    if (mesmoMes) {
      state.calendario.diaSelecionado = hojeStr;
    } else if (!state.calendario.diaSelecionado || !state.calendario.diaSelecionado.startsWith(`${ano}-${String(mes).padStart(2, '0')}`)) {
      if (dados.dias_com_aula && dados.dias_com_aula.length > 0) {
        state.calendario.diaSelecionado = dados.dias_com_aula[0].data;
      } else {
        state.calendario.diaSelecionado = `${ano}-${String(mes).padStart(2, '0')}-01`;
      }
    }

    await carregarChamadaDia(state.calendario.diaSelecionado);
    await carregarRetencaoAusentes();

  } catch (err) {
    console.error('Erro ao carregar calendário:', err);
  }
}

function renderizarGradeCalendario(dados) {
  const container = document.getElementById('cal-days-container');
  if (!container) return;

  const ano = dados.ano;
  const mes = dados.mes;

  const mapaDiasComAula = {};
  (dados.dias_com_aula || []).forEach(d => {
    mapaDiasComAula[d.dia] = d;
  });

  const primeiroDiaDt = new Date(ano, mes - 1, 1);
  let primeiroDiaSemana = primeiroDiaDt.getDay();
  let offsetSegunda = (primeiroDiaSemana === 0) ? 6 : primeiroDiaSemana - 1;

  const ultimoDiaDt = new Date(ano, mes, 0);
  const totalDias = ultimoDiaDt.getDate();

  let html = '';

  for (let i = 0; i < offsetSegunda; i++) {
    html += '<div class="cal-day-cell empty"></div>';
  }

  const hoje = new Date();
  const hojeStr = hoje.toISOString().slice(0, 10);
  const diaSel = state.calendario.diaSelecionado;

  for (let d = 1; d <= totalDias; d++) {
    const dataStr = `${ano}-${String(mes).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
    const ehHoje = (dataStr === hojeStr);
    const ehSelecionado = (dataStr === diaSel);
    const aulaInfo = mapaDiasComAula[d];

    let classes = ['cal-day-cell'];
    if (ehHoje) classes.push('today');
    if (ehSelecionado) classes.push('selected');
    if (aulaInfo) classes.push('has-class');

    let dotStatusHtml = '';
    if (aulaInfo) {
      let dotClass = 'pendente';
      if (aulaInfo.status_dia === 'concluido') dotClass = 'concluido';
      else if (aulaInfo.status_dia === 'parcial') dotClass = 'parcial';
      dotStatusHtml = `<span class="cal-dot ${dotClass}" title="${aulaInfo.turmas_count} turma(s) • ${aulaInfo.status_dia}"></span>`;
    }

    html += `
      <div class="${classes.join(' ')}" data-date="${dataStr}" onclick="selecionarDiaCalendario('${dataStr}')" title="Dia ${d}${aulaInfo ? ` (${aulaInfo.turmas_count} turma(s) - toque para ver)` : ''}">
        <span class="cal-day-circle">${d}</span>
        <div class="cal-dot-container">${dotStatusHtml}</div>
      </div>
    `;
  }

  container.innerHTML = html;
}

function mudarMesCalendario(delta) {
  let novoMes = state.calendario.mes + delta;
  let novoAno = state.calendario.ano;

  if (novoMes > 12) {
    novoMes = 1;
    novoAno++;
  } else if (novoMes < 1) {
    novoMes = 12;
    novoAno--;
  }

  state.calendario.mes = novoMes;
  state.calendario.ano = novoAno;
  carregarCalendario();
}

function irParaHoje() {
  const agora = new Date();
  state.calendario.ano = agora.getFullYear();
  state.calendario.mes = agora.getMonth() + 1;
  state.calendario.diaSelecionado = agora.toISOString().slice(0, 10);
  carregarCalendario();
}

async function selecionarDiaCalendario(dataStr, turmaIdFocus = null) {
  state.calendario.diaSelecionado = dataStr;

  document.querySelectorAll('.cal-day-cell').forEach(cell => {
    if (cell.dataset.date === dataStr) {
      cell.classList.add('selected');
    } else {
      cell.classList.remove('selected');
    }
  });

  await carregarChamadaDia(dataStr, turmaIdFocus);
}

async function carregarChamadaDia(dataStr, turmaIdFocus = null) {
  try {
    const res = await fetch(`/api/calendario/dia?data=${dataStr}`);
    const chamada = await res.json();
    state.calendario.dadosDia = chamada;

    const elTitulo = document.getElementById('cal-selected-day-title');
    if (elTitulo) {
      const dtParts = dataStr.split('-');
      const diaNum = parseInt(dtParts[2]);
      const mesNum = parseInt(dtParts[1]);
      const anoNum = dtParts[0];
      const mesesExtenso = [
        'Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho',
        'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro'
      ];
      const hojeTag = chamada.eh_hoje ? ' <span style="font-size:11px; font-weight:700; background:var(--shanti-terracotta); color:#fff; padding:2px 8px; border-radius:10px; margin-left:6px;">HOJE</span>' : '';
      elTitulo.innerHTML = `<i class="fa-solid fa-calendar-day" style="color: var(--shanti-forest);"></i> ${chamada.dia_semana_nome}, ${diaNum} de ${mesesExtenso[mesNum - 1]} de ${anoNum}${hojeTag}`;
    }

    const t = chamada.totais || { esperados: 0, presentes: 0, faltas: 0, pendentes: 0 };
    const pEsp = document.getElementById('pill-esperados');
    const pPres = document.getElementById('pill-presentes');
    const pFalt = document.getElementById('pill-faltas');
    const pPend = document.getElementById('pill-pendentes');

    if (pEsp) pEsp.textContent = `${t.esperados} esperado${t.esperados === 1 ? '' : 's'}`;
    if (pPres) pPres.textContent = `${t.presentes} presente${t.presentes === 1 ? '' : 's'}`;
    if (pFalt) pFalt.textContent = `${t.faltas} falta${t.faltas === 1 ? '' : 's'}`;
    if (pPend) pPend.textContent = `${t.pendentes} pendente${t.pendentes === 1 ? '' : 's'}`;

    renderizarTurmasChamada(chamada, turmaIdFocus);

    // Rolagem suave até a folha de chamada
    const sheet = document.getElementById('cal-daily-sheet');
    if (sheet) {
      if (turmaIdFocus) {
        setTimeout(() => {
          const turmaEl = document.getElementById(`cal-turma-${turmaIdFocus}`);
          if (turmaEl) {
            turmaEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
            turmaEl.classList.add('focused');
            setTimeout(() => turmaEl.classList.remove('focused'), 2500);
          } else {
            sheet.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
          }
        }, 120);
      } else {
        sheet.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
      }
    }

  } catch (err) {
    console.error('Erro ao carregar chamada do dia:', err);
  }
}

function extrairIniciaisAluno(nome) {
  if (!nome) return 'YS';
  const partes = nome.trim().split(/\s+/).filter(Boolean);
  if (partes.length === 1) return partes[0].slice(0, 2).toUpperCase();
  return (partes[0][0] + partes[partes.length - 1][0]).toUpperCase();
}

function renderizarTurmasChamada(chamada, turmaIdFocus = null) {
  const container = document.getElementById('cal-turmas-chamada-list');
  if (!container) return;

  const turmas = chamada.turmas || [];
  const dataStr = chamada.data;

  if (turmas.length === 0) {
    container.innerHTML = `
      <div style="text-align: center; padding: 28px 16px; background: var(--shanti-sand-light); border: 1px dashed var(--shanti-sand-border); border-radius: 14px; color: var(--shanti-stone);">
        <i class="fa-solid fa-mug-hot" style="font-size: 32px; margin-bottom: 10px; color: var(--shanti-sand);"></i>
        <p style="margin: 0; font-size: 14px; font-weight: 700; color: var(--shanti-charcoal);">Nenhuma turma programada para este dia.</p>
        <span style="font-size: 12px; color: var(--shanti-stone);">Toque em qualquer dia com bolinha verde no calendário acima para ver as turmas e alunos! 🧘‍♀️</span>
      </div>
    `;
    return;
  }

  // Extrair dia da semana curto e dia do mês para o card estilo referência
  const dtParts = (dataStr || '').split('-');
  const diaNum = dtParts[2] ? parseInt(dtParts[2]) : '';
  const dowAbrev = (chamada.dia_semana_nome ? chamada.dia_semana_nome.slice(0, 3).toUpperCase() : 'AULA');

  let html = '';

  turmas.forEach(t => {
    const alunos = t.alunos || [];
    let alunosHtml = '';

    if (alunos.length === 0) {
      alunosHtml = `
        <div style="font-size: 12px; color: var(--shanti-stone); text-align: center; padding: 14px; background: #FFFFFF; border: 1px dashed var(--shanti-sand-border); border-radius: 10px;">
          Nenhum aluno matriculado nesta turma ainda.
        </div>
      `;
    } else {
      alunosHtml = alunos.map(al => {
        const st = al.status || 'pendente';
        const isPausado = al.pausar_alerta_ausencia;

        const badgePausaHtml = isPausado 
          ? `<span class="cal-aluno-pausa-badge" title="Alertas de falta pausados: ${al.motivo_pausa_alerta || 'Viagem'}"><i class="fa-solid fa-umbrella-beach"></i> Pausado: ${al.motivo_pausa_alerta || 'Viagem'}</span>` 
          : '';

        const iniciais = extrairIniciaisAluno(al.nome);

        return `
          <div class="cal-aluno-item" id="aluno-row-${al.aluno_id}-${t.turma_id}">
            <div class="cal-aluno-left">
              <div class="cal-aluno-avatar">${iniciais}</div>
              <div class="cal-aluno-info">
                <div class="cal-aluno-nome">
                  <span>${al.nome}</span>
                  ${badgePausaHtml}
                </div>
                <div class="cal-aluno-detalhe">
                  <i class="fa-solid fa-id-badge" style="font-size: 10px; opacity: 0.7;"></i> ${al.plano}${al.dia_semana_1x ? ` • ${al.dia_semana_1x}` : ''}
                </div>
              </div>
            </div>

            <div class="cal-presence-toggle">
              <button type="button" class="cal-toggle-btn ${st === 'pendente' ? 'active-pendente' : ''}" 
                onclick="atualizarPresenca(${al.aluno_id}, ${t.turma_id}, '${dataStr}', 'pendente')"
                title="Aguardando checagem">
                <i class="fa-solid fa-hourglass-start"></i> Pendente
              </button>
              <button type="button" class="cal-toggle-btn ${st === 'presente' ? 'active-presente' : ''}" 
                onclick="atualizarPresenca(${al.aluno_id}, ${t.turma_id}, '${dataStr}', 'presente')"
                title="Confirmar presença">
                <i class="fa-solid fa-check"></i> Presente
              </button>
              <button type="button" class="cal-toggle-btn ${st === 'faltou' ? 'active-faltou' : ''}" 
                onclick="atualizarPresenca(${al.aluno_id}, ${t.turma_id}, '${dataStr}', 'faltou')"
                title="Registrar falta">
                <i class="fa-solid fa-xmark"></i> Faltou
              </button>
            </div>
          </div>
        `;
      }).join('');
    }

    const isThisFocused = (turmaIdFocus && turmaIdFocus === t.turma_id);

    html += `
      <div class="cal-turma-card ${isThisFocused ? 'focused' : ''}" id="cal-turma-${t.turma_id}">
        <!-- Top bar estilo card da referência visual -->
        <div class="cal-turma-top-bar">
          <div class="cal-turma-dow-badge">
            <span class="cal-turma-dow-name">${dowAbrev}</span>
            <span class="cal-turma-dow-num">${diaNum}</span>
          </div>

          <div class="cal-turma-meta">
            <div class="cal-turma-tags">
              <span class="cal-turma-time-tag">
                <i class="fa-regular fa-clock"></i> ${t.horario}
              </span>
              <span class="cal-turma-cap-tag">
                <i class="fa-solid fa-users"></i> ${alunos.length}/${t.capacidade_vagas} alunos
              </span>
            </div>
            <h4 class="cal-turma-name-title">
              <i class="fa-solid fa-om" style="color: var(--shanti-forest);"></i> ${t.nome}
            </h4>
          </div>
        </div>

        ${alunos.length > 0 ? `
          <div class="cal-turma-actions">
            <button type="button" class="cal-btn-marcar-todos" onclick="marcarTodosPresentesTurma(${t.turma_id}, '${dataStr}')">
              <i class="fa-solid fa-check-double"></i> Marcar Todos Presentes
            </button>
          </div>
        ` : ''}

        <div class="cal-turma-alunos-list">
          ${alunosHtml}
        </div>
      </div>
    `;
  });

  container.innerHTML = html;
}

async function atualizarPresenca(alunoId, turmaId, dataStr, novoStatus) {
  try {
    const rowEl = document.getElementById(`aluno-row-${alunoId}-${turmaId}`);
    if (rowEl) {
      const btns = rowEl.querySelectorAll('.cal-toggle-btn');
      btns.forEach(b => {
        b.classList.remove('active-pendente', 'active-presente', 'active-faltou');
      });
      if (novoStatus === 'pendente') btns[0]?.classList.add('active-pendente');
      if (novoStatus === 'presente') btns[1]?.classList.add('active-presente');
      if (novoStatus === 'faltou') btns[2]?.classList.add('active-faltou');
    }

    const res = await fetch('/api/calendario/presenca', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        aluno_id: alunoId,
        turma_id: turmaId,
        data: dataStr,
        status: novoStatus
      })
    });

    if (!res.ok) {
      showToast('Erro ao salvar presença.');
      return;
    }

    await carregarChamadaDia(dataStr);
    await carregarRetencaoAusentes();

    if (state.calendario.dadosMes) {
      const resMes = await fetch(`/api/calendario/mes?ano=${state.calendario.ano}&mes=${state.calendario.mes}`);
      const dadosMes = await resMes.json();
      state.calendario.dadosMes = dadosMes;
      renderizarGradeCalendario(dadosMes);
    }

  } catch (err) {
    console.error('Erro ao atualizar presença:', err);
    showToast('Erro ao atualizar presença.');
  }
}

async function marcarTodosPresentesTurma(turmaId, dataStr) {
  try {
    showToast('Marcando todos como presentes...');
    const res = await fetch('/api/calendario/turma-presenca-lote', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        turma_id: turmaId,
        data: dataStr
      })
    });

    const resultado = await res.json();
    if (resultado.sucesso) {
      showToast(`✅ ${resultado.total_marcados} alunos marcados como presentes!`);
      await carregarChamadaDia(dataStr);
      await carregarRetencaoAusentes();
      if (state.calendario.dadosMes) {
        const resMes = await fetch(`/api/calendario/mes?ano=${state.calendario.ano}&mes=${state.calendario.mes}`);
        state.calendario.dadosMes = await resMes.json();
        renderizarGradeCalendario(state.calendario.dadosMes);
      }
    }
  } catch (err) {
    console.error('Erro ao marcar lote:', err);
    showToast('Erro ao marcar turma.');
  }
}

async function carregarRetencaoAusentes() {
  try {
    const res = await fetch('/api/calendario/retencao?dias=14');
    const ausentes = await res.json();
    state.calendario.retencao = ausentes;

    const ativosAusentes = ausentes.filter(a => !a.pausado);
    const badgeCal = document.getElementById('badge-cal-retencao');
    const badgeTab = document.getElementById('badge-calendario-alert');

    if (badgeCal) {
      badgeCal.textContent = ativosAusentes.length;
      badgeCal.style.display = ativosAusentes.length > 0 ? 'inline-block' : 'none';
    }
    if (badgeTab) {
      badgeTab.textContent = ativosAusentes.length;
      badgeTab.style.display = ativosAusentes.length > 0 ? 'inline-block' : 'none';
    }

    const container = document.getElementById('cal-retencao-list');
    if (!container) return;

    if (ausentes.length === 0) {
      container.innerHTML = `
        <div style="font-size: 12px; color: var(--shanti-stone); text-align: center; padding: 12px; background: #FFFFFF; border: 1px dashed var(--shanti-sand-border); border-radius: 10px;">
          Nenhum aluno em risco de evasão nas últimas 2 semanas! 🙏
        </div>
      `;
      return;
    }

    container.innerHTML = ausentes.map(au => {
      const isPausado = au.pausado;
      const motivoPausa = au.motivo_pausa ? `<span style="font-size:11px; color:#B45309; display:block;"><i class="fa-solid fa-umbrella-beach"></i> Pausado: ${au.motivo_pausa}</span>` : '';

      return `
        <div class="cal-retencao-item" style="${isPausado ? 'opacity: 0.75; background: #fdfaf6;' : ''}">
          <div style="flex: 1; min-width: 180px;">
            <div style="display: flex; align-items: center; gap: 6px;">
              <strong style="font-size: 13.5px; color: var(--shanti-charcoal);">${au.nome}</strong>
              ${isPausado ? '<span style="font-size:10px; background:#FDF3E7; color:#B45309; padding:2px 6px; border-radius:8px; border:1px solid #F6D6B2; font-weight:600;">Pausado</span>' : ''}
            </div>
            <div style="font-size: 11.5px; color: #B45309; font-weight: 600; margin-top: 2px;">
              <i class="fa-solid fa-triangle-exclamation"></i> ${au.faltas_consecutivas} faltas consecutivas • ${au.plano}
            </div>
            <div style="font-size: 11px; color: var(--shanti-stone); margin-top: 2px;">
              Última presença: ${au.ultima_presenca} • Turma: ${(au.turmas || []).join(', ')}
            </div>
            ${motivoPausa}
          </div>

          <div style="display: flex; align-items: center; gap: 8px; flex-wrap: wrap;">
            ${!isPausado ? `
              <a href="${au.link_whatsapp}" target="_blank" class="wa-btn-sm-whatsapp" style="padding: 6px 12px; font-size: 11.5px; border-radius: 12px; text-decoration: none;">
                <i class="fa-brands fa-whatsapp"></i> Acolher Aluno
              </a>
            ` : ''}
            <button type="button" class="wa-btn-secondary" style="padding: 6px 10px; font-size: 11px; border-radius: 12px;" onclick="abrirModalPausaAlerta(${au.aluno_id}, '${au.nome.replace(/'/g, "\'")}', ${isPausado}, '${(au.motivo_pausa || '').replace(/'/g, "\'")}')">
              <i class="fa-solid ${isPausado ? 'fa-play' : 'fa-pause'}"></i> ${isPausado ? 'Retomar' : 'Pausar'}
            </button>
          </div>
        </div>
      `;
    }).join('');

  } catch (err) {
    console.error('Erro ao carregar retencao:', err);
  }
}

function abrirModalPausaAlerta(alunoId, nomeAluno, estaPausado, motivoAtual) {
  const modal = document.getElementById('modal-pausa-alerta');
  const inputId = document.getElementById('modal-pausa-aluno-id');
  const inputAcao = document.getElementById('modal-pausa-acao');
  const inputMotivo = document.getElementById('modal-pausa-motivo');
  const textoModal = document.getElementById('modal-pausa-texto');
  const grupoMotivo = document.getElementById('grupo-motivo-pausa');
  const btnConfirmar = document.getElementById('btn-confirmar-pausa-alerta');

  if (!modal) return;

  inputId.value = alunoId;
  inputAcao.value = estaPausado ? 'retomar' : 'pausar';

  if (estaPausado) {
    textoModal.innerHTML = `Deseja <strong>reativar os alertas acolhedores</strong> para <strong>${nomeAluno}</strong>? Ele voltará a ser monitorado normalmente.`;
    grupoMotivo.style.display = 'none';
    btnConfirmar.textContent = 'Reativar Alertas';
    btnConfirmar.style.background = 'var(--shanti-forest)';
  } else {
    textoModal.innerHTML = `Deseja <strong>pausar os alertas de falta</strong> para <strong>${nomeAluno}</strong>? Útil quando o aluno avisou viagem ou férias (Cláusula 6 do contrato).`;
    grupoMotivo.style.display = 'block';
    inputMotivo.value = motivoAtual || 'Viagem / Férias comunicadas';
    btnConfirmar.textContent = 'Confirmar Pausa';
    btnConfirmar.style.background = 'var(--shanti-terracotta)';
  }

  modal.style.display = 'flex';
}

function fecharModalPausaAlerta() {
  const modal = document.getElementById('modal-pausa-alerta');
  if (modal) modal.style.display = 'none';
}

async function salvarPausaAlerta() {
  const inputId = document.getElementById('modal-pausa-aluno-id');
  const inputAcao = document.getElementById('modal-pausa-acao');
  const inputMotivo = document.getElementById('modal-pausa-motivo');

  const alunoId = inputId.value;
  const pausar = (inputAcao.value === 'pausar');
  const motivo = inputMotivo.value;

  try {
    const res = await fetch(`/api/alunos/${alunoId}/pausar-alerta`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ pausar, motivo })
    });

    if (res.ok) {
      fecharModalPausaAlerta();
      showToast(pausar ? 'Alertas de ausência pausados!' : 'Alertas reativados com sucesso!');
      await carregarRetencaoAusentes();
      if (state.calendario.diaSelecionado) {
        await carregarChamadaDia(state.calendario.diaSelecionado);
      }
    } else {
      showToast('Erro ao atualizar pausa.');
    }
  } catch (err) {
    console.error('Erro ao salvar pausa:', err);
    showToast('Erro ao atualizar pausa.');
  }
}

// Expor funções no escopo global window para chamadas inline HTML
window.setupCalendario = setupCalendario;
window.carregarCalendario = carregarCalendario;
window.mudarMesCalendario = mudarMesCalendario;
window.irParaHoje = irParaHoje;
window.selecionarDiaCalendario = selecionarDiaCalendario;
window.carregarChamadaDia = carregarChamadaDia;
window.atualizarPresenca = atualizarPresenca;
window.marcarTodosPresentesTurma = marcarTodosPresentesTurma;
window.carregarRetencaoAusentes = carregarRetencaoAusentes;
window.abrirModalPausaAlerta = abrirModalPausaAlerta;
window.fecharModalPausaAlerta = fecharModalPausaAlerta;
window.salvarPausaAlerta = salvarPausaAlerta;
window.abrirSeletorMesAno = abrirSeletorMesAno;
window.selecionarMesAnoDireto = selecionarMesAnoDireto;
window.abrirModal = abrirModal;
window.fecharModal = fecharModal;
