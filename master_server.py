"""VoidCore Stealth - Master Server & Painel Central de Licenciamento (Admin Hub).
Controla aprovação de novos cadastros de usuários, geração de chaves HWID-locked,
verificação de status e publicação de atualizações OTA (Over-The-Air) em tempo real.
Funciona 100% com a biblioteca padrão do Python e banco de dados SQLite.
"""
import base64
import hashlib
import hmac
import json
import os
import random
import secrets
import sqlite3
import string
import sys
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

HOST = "0.0.0.0"
PORT = int(os.environ.get("PORT", 8888))
BASE_DIR = Path(__file__).resolve().parent
DB_FILE = BASE_DIR / "voidcore_master.db"
ADMIN_PASSWORD = os.environ.get("VOIDCORE_ADMIN_PASS", "voidcore_admin_2026")

# Segredo de assinatura criptográfica idêntico ao license_gate
MASTER_SALT = "VOIDCORE_STEALTH_2026_DRM_PROTECTED"
MASTER_SIGN_KEY = "VOIDCORE_SUPER_MASTER_SECRET_KEY_9981"


def get_db():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS licenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT UNIQUE NOT NULL,
            hwid TEXT,
            user_name TEXT,
            contact TEXT,
            tier TEXT DEFAULT 'PRO_LIFETIME',
            max_machines INTEGER DEFAULT 1,
            created_at INTEGER,
            expires_at INTEGER,
            is_active INTEGER DEFAULT 1,
            last_heartbeat INTEGER,
            notes TEXT
        );

        CREATE TABLE IF NOT EXISTS access_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            hwid TEXT NOT NULL,
            name TEXT NOT NULL,
            contact TEXT NOT NULL,
            notes TEXT,
            client_version TEXT,
            status TEXT DEFAULT 'PENDING',
            assigned_key TEXT,
            ip_address TEXT,
            created_at INTEGER,
            updated_at INTEGER
        );

        CREATE TABLE IF NOT EXISTS updates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            version TEXT UNIQUE NOT NULL,
            release_date INTEGER,
            changelog TEXT,
            download_url TEXT,
            mandatory INTEGER DEFAULT 0,
            is_active INTEGER DEFAULT 1
        );
        """)
        # Cria atualização padrão inicial v2.0.0 se não existir
        cur = conn.cursor()
        cur.execute("SELECT id FROM updates WHERE version = '2.0.0'")
        if not cur.fetchone():
            conn.execute(
                "INSERT INTO updates (version, release_date, changelog, download_url, mandatory, is_active) VALUES (?, ?, ?, ?, ?, ?)",
                ("2.0.0", int(time.time()), "Lançamento oficial VoidCore Stealth v2.0 Pro com C CDP Shield & Captcha Solver.", "", 0, 1)
            )


init_db()


def generate_key_string() -> str:
    """Gera chave no formato VOID-XXXX-XXXX-XXXX-XXXX."""
    chars = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    parts = ["".join(random.choices(chars, k=4)) for _ in range(4)]
    return f"VOID-{'-'.join(parts)}"


def sign_payload(payload: Dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hmac.new(MASTER_SIGN_KEY.encode("utf-8"), canonical.encode("utf-8"), hashlib.sha256).hexdigest()


# HTML do Painel Admin Moderno Dark / VoidCore Stealth
ADMIN_HTML = """<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>VoidCore Master Control · Central de Licenciamento & Atualizações</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;600&display=swap" rel="stylesheet">
<style>
:root {
  --bg-dark: #07080d;
  --bg-card: rgba(18, 20, 29, 0.85);
  --bg-card-hover: rgba(24, 27, 40, 0.95);
  --border: rgba(255, 255, 255, 0.08);
  --border-cyan: rgba(6, 182, 212, 0.35);
  --cyan: #06b6d4;
  --cyan-bright: #22d3ee;
  --indigo: #6366f1;
  --emerald: #10b981;
  --rose: #f43f5e;
  --amber: #f59e0b;
  --text-main: #f1f5f9;
  --text-muted: #94a3b8;
  --font: 'Plus Jakarta Sans', sans-serif;
  --mono: 'JetBrains Mono', monospace;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  background: var(--bg-dark);
  color: var(--text-main);
  font-family: var(--font);
  min-height: 100vh;
  background-image: 
    radial-gradient(ellipse 80% 50% at 50% -20%, rgba(6, 182, 212, 0.15), transparent),
    radial-gradient(ellipse 60% 40% at 90% 80%, rgba(99, 102, 241, 0.08), transparent);
}
.header {
  border-bottom: 1px solid var(--border);
  background: rgba(11, 13, 20, 0.8);
  backdrop-filter: blur(16px);
  padding: 16px 32px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  position: sticky;
  top: 0;
  z-index: 50;
}
.brand-area { display: flex; align-items: center; gap: 14px; }
.logo-tile {
  width: 40px; height: 40px; border-radius: 10px;
  background: linear-gradient(135deg, rgba(6,182,212,0.2), rgba(99,102,241,0.25));
  border: 1px solid var(--border-cyan);
  display: flex; align-items: center; justify-content: center;
  box-shadow: 0 0 16px rgba(6,182,212,0.25);
}
.logo-tile svg { width: 22px; height: 22px; fill: var(--cyan); }
.brand-title { font-size: 19px; font-weight: 800; letter-spacing: 0.5px; }
.brand-title b { color: var(--cyan); }
.brand-sub { font-size: 11px; color: var(--cyan-bright); letter-spacing: 1.5px; text-transform: uppercase; font-weight: 700; }
.auth-bar { display: flex; align-items: center; gap: 12px; }
.input-auth {
  background: rgba(255,255,255,0.05); border: 1px solid var(--border);
  color: #fff; padding: 7px 12px; border-radius: 8px; font-family: var(--mono); font-size: 13px;
  outline: none; transition: 0.2s;
}
.input-auth:focus { border-color: var(--cyan); box-shadow: 0 0 10px rgba(6,182,212,0.3); }
.btn {
  background: linear-gradient(135deg, var(--cyan), var(--indigo));
  color: #fff; font-weight: 600; font-size: 13px; padding: 8px 16px; border-radius: 8px;
  border: none; cursor: pointer; display: inline-flex; align-items: center; gap: 6px;
  box-shadow: 0 4px 14px rgba(6,182,212,0.25); transition: 0.2s;
}
.btn:hover { filter: brightness(1.15); transform: translateY(-1px); }
.btn.sm { padding: 5px 10px; font-size: 12px; border-radius: 6px; }
.btn.danger { background: linear-gradient(135deg, #e11d48, #be123c); box-shadow: 0 4px 14px rgba(225,29,72,0.3); }
.btn.ghost { background: rgba(255,255,255,0.06); border: 1px solid var(--border); box-shadow: none; }
.btn.ghost:hover { background: rgba(255,255,255,0.12); border-color: rgba(255,255,255,0.2); }
.container { max-width: 1360px; margin: 0 auto; padding: 28px 24px 60px; }
.stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 18px; margin-bottom: 28px; }
.stat-card {
  background: var(--bg-card); border: 1px solid var(--border); border-radius: 14px; padding: 20px;
  display: flex; flex-direction: column; gap: 6px; position: relative; overflow: hidden;
}
.stat-card::after {
  content: ''; position: absolute; top: 0; left: 0; right: 0; height: 2px;
  background: linear-gradient(90deg, var(--cyan), transparent);
}
.stat-lbl { font-size: 12px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.8px; color: var(--text-muted); }
.stat-val { font-size: 32px; font-weight: 800; font-family: var(--mono); color: #fff; }
.stat-desc { font-size: 12px; color: var(--cyan); }
.tabs { display: flex; gap: 8px; margin-bottom: 20px; border-bottom: 1px solid var(--border); padding-bottom: 12px; }
.tab-btn {
  background: transparent; border: none; color: var(--text-muted); font-size: 14px; font-weight: 600;
  padding: 8px 16px; border-radius: 8px; cursor: pointer; transition: 0.2s; display: flex; align-items: center; gap: 8px;
}
.tab-btn.active { background: rgba(6,182,212,0.15); color: var(--cyan-bright); border: 1px solid var(--border-cyan); }
.badge {
  background: rgba(255,255,255,0.08); padding: 2px 7px; border-radius: 12px; font-size: 11px; font-family: var(--mono);
}
.badge.alert { background: rgba(244,63,94,0.2); color: var(--rose); border: 1px solid rgba(244,63,94,0.3); }
.section-card {
  background: var(--bg-card); border: 1px solid var(--border); border-radius: 14px; padding: 24px; margin-bottom: 24px;
}
.section-title { font-size: 18px; font-weight: 700; margin-bottom: 16px; display: flex; align-items: center; justify-content: space-between; }
.table-wrap { overflow-x: auto; border: 1px solid var(--border); border-radius: 10px; }
table { width: 100%; border-collapse: collapse; text-align: left; font-size: 13px; }
th { background: rgba(255,255,255,0.03); color: var(--text-muted); font-size: 11px; text-transform: uppercase; letter-spacing: 0.6px; padding: 12px 16px; border-bottom: 1px solid var(--border); }
td { padding: 14px 16px; border-bottom: 1px solid var(--border); vertical-align: middle; }
tr:last-child td { border-bottom: none; }
tr:hover td { background: rgba(255,255,255,0.02); }
.mono { font-family: var(--mono); font-size: 12px; color: #a5f3fc; }
.pill { padding: 4px 9px; border-radius: 6px; font-size: 11px; font-weight: 700; display: inline-block; text-transform: uppercase; }
.pill.active { background: rgba(16,185,129,0.15); color: var(--emerald); border: 1px solid rgba(16,185,129,0.3); }
.pill.pending { background: rgba(245,158,11,0.15); color: var(--amber); border: 1px solid rgba(245,158,11,0.3); }
.pill.revoked { background: rgba(244,63,94,0.15); color: var(--rose); border: 1px solid rgba(244,63,94,0.3); }
.form-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 14px; margin-top: 14px; }
.form-field { display: flex; flex-direction: column; gap: 6px; }
.form-lbl { font-size: 11px; font-weight: 600; text-transform: uppercase; color: var(--text-muted); }
.form-input {
  background: rgba(255,255,255,0.04); border: 1px solid var(--border); color: #fff;
  padding: 10px 12px; border-radius: 8px; font-family: var(--font); font-size: 13px; outline: none;
}
.form-input:focus { border-color: var(--cyan); box-shadow: 0 0 10px rgba(6,182,212,0.25); }
.alert-box {
  padding: 12px 16px; border-radius: 8px; background: rgba(16,185,129,0.1); border: 1px solid rgba(16,185,129,0.3);
  color: #6ee7b7; font-size: 13px; margin-bottom: 16px; display: none; align-items: center; justify-content: space-between;
}
.copy-btn { cursor: pointer; color: var(--cyan-bright); text-decoration: underline; background: none; border: none; font-size: 12px; }
</style>
</head>
<body>

<header class="header">
  <div class="brand-area">
    <div class="logo-tile">
      <svg viewBox="0 0 24 24"><path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/></svg>
    </div>
    <div>
      <div class="brand-title">VOID<b>CORE</b> MASTER</div>
      <div class="brand-sub">Admin DRM & OTA Update Hub</div>
    </div>
  </div>
  <div class="auth-bar">
    <input type="password" id="admin-pass" class="input-auth" placeholder="Senha do Administrador" value="voidcore_admin_2026">
    <button class="btn sm" onclick="loadAllData()">Conectar / Atualizar</button>
  </div>
</header>

<div class="container">
  <div id="flash-msg" class="alert-box">
    <span id="flash-txt"></span>
    <button class="btn sm ghost" onclick="document.getElementById('flash-msg').style.display='none'">Fechar</button>
  </div>

  <div class="stats-grid">
    <div class="stat-card">
      <span class="stat-lbl">Pedidos Pendentes</span>
      <span class="stat-val" id="stat-pending">0</span>
      <span class="stat-desc">Amigos aguardando aprovação</span>
    </div>
    <div class="stat-card">
      <span class="stat-lbl">Licenças Ativas</span>
      <span class="stat-val" id="stat-active-lic">0</span>
      <span class="stat-desc">Máquinas autorizadas</span>
    </div>
    <div class="stat-card">
      <span class="stat-lbl">Versão Atual em Produção</span>
      <span class="stat-val" id="stat-version">v2.0.0</span>
      <span class="stat-desc">Distribuição OTA pronta</span>
    </div>
  </div>

  <div class="tabs">
    <button class="tab-btn active" onclick="switchTab('requests')" id="tab-btn-requests">
      <span>Solicitações de Acesso</span>
      <span class="badge alert" id="badge-pending-count">0</span>
    </button>
    <button class="tab-btn" onclick="switchTab('licenses')" id="tab-btn-licenses">
      <span>Licenças & Chaves Ativas</span>
    </button>
    <button class="tab-btn" onclick="switchTab('generate')" id="tab-btn-generate">
      <span>+ Gerador Manual de Chaves</span>
    </button>
    <button class="tab-btn" onclick="switchTab('updates')" id="tab-btn-updates">
      <span>Central de Atualizações (OTA)</span>
    </button>
  </div>

  <!-- TAB 1: SOLICITAÇÕES DE ACESSO -->
  <div id="tab-requests" class="section-card">
    <div class="section-title">
      <span>Solicitações de Cadastro Recebidas</span>
      <button class="btn sm ghost" onclick="loadRequests()">Recarregar Lista</button>
    </div>
    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Data</th>
            <th>Nome / Usuário</th>
            <th>Contato (Zap / Discord)</th>
            <th>Identificador HWID</th>
            <th>Notas</th>
            <th>Status</th>
            <th>Ações do Administrador</th>
          </tr>
        </thead>
        <tbody id="table-requests-body">
          <tr><td colspan="7" style="text-align:center;color:var(--text-muted);padding:30px;">Carregando solicitações...</td></tr>
        </tbody>
      </table>
    </div>
  </div>

  <!-- TAB 2: TODAS AS LICENÇAS -->
  <div id="tab-licenses" class="section-card" style="display:none;">
    <div class="section-title">
      <span>Licenças Cadastradas no Sistema</span>
      <button class="btn sm ghost" onclick="loadLicenses()">Recarregar Lista</button>
    </div>
    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Chave (Key)</th>
            <th>Usuário / Destinatário</th>
            <th>HWID Bloqueado</th>
            <th>Plano / Validade</th>
            <th>Status</th>
            <th>Último Heartbeat</th>
            <th>Ação</th>
          </tr>
        </thead>
        <tbody id="table-licenses-body">
          <tr><td colspan="7" style="text-align:center;color:var(--text-muted);padding:30px;">Carregando licenças...</td></tr>
        </tbody>
      </table>
    </div>
  </div>

  <!-- TAB 3: GERADOR MANUAL DE CHAVES -->
  <div id="tab-generate" class="section-card" style="display:none;">
    <div class="section-title">Gerar Nova Licença sob Demanda</div>
    <p style="color:var(--text-muted);font-size:13px;margin-bottom:14px;">Gere chaves avulsas para enviar diretamente a amigos ou clientes. A chave se amarra automaticamente à primeira máquina que ativá-la.</p>
    <div class="form-grid">
      <div class="form-field">
        <label class="form-lbl">Nome do Usuário</label>
        <input type="text" id="gen-user" class="form-input" placeholder="Ex: Felipe Silveira">
      </div>
      <div class="form-field">
        <label class="form-lbl">Contato / WhatsApp</label>
        <input type="text" id="gen-contact" class="form-input" placeholder="Ex: (11) 98888-7777">
      </div>
      <div class="form-field">
        <label class="form-lbl">Plano / Duração</label>
        <select id="gen-tier" class="form-input">
          <option value="PRO_LIFETIME">Vitalício PRO (Sem expiração)</option>
          <option value="PRO_30D">Mensal (30 Dias)</option>
          <option value="PRO_90D">Trimestral (90 Dias)</option>
          <option value="TRIAL_7D">Trial de Degustação (7 Dias)</option>
        </select>
      </div>
      <div class="form-field">
        <label class="form-lbl">Vincular a HWID específico (Opcional)</label>
        <input type="text" id="gen-hwid" class="form-input mono" placeholder="VC-XXXX... (Deixe em branco p/ qualquer PC)">
      </div>
    </div>
    <div style="margin-top:20px;">
      <button class="btn" onclick="submitGenerateKey()">Gerar Chave Agora</button>
    </div>
  </div>

  <!-- TAB 4: CENTRAL DE ATUALIZAÇÕES (OTA) -->
  <div id="tab-updates" class="section-card" style="display:none;">
    <div class="section-title">Publicador de Atualizações em Massa (OTA)</div>
    <p style="color:var(--text-muted);font-size:13px;margin-bottom:14px;">Publique novas versões para que todos os VoidCore instalados notifiquem os usuários e baixem as novas funções automaticamente.</p>
    <div class="form-grid">
      <div class="form-field">
        <label class="form-lbl">Número da Versão</label>
        <input type="text" id="upd-version" class="form-input" placeholder="Ex: 2.0.1">
      </div>
      <div class="form-field">
        <label class="form-lbl">URL do Pacote ZIP de Atualização (Opcional)</label>
        <input type="text" id="upd-url" class="form-input" placeholder="https://... ou vazio para aviso manual">
      </div>
    </div>
    <div class="form-field" style="margin-top:14px;">
      <label class="form-lbl">Changelog / Novas Funções Adicionadas</label>
      <textarea id="upd-changelog" class="form-input" rows="4" placeholder="- Adicionado novo bypass do Shopee e Mercado Livre&#10;- Solver de Captcha nativo agora 40% mais veloz&#10;- Correções de estabilidade"></textarea>
    </div>
    <div style="margin-top:20px;">
      <button class="btn" onclick="publishUpdate()">Publicar Nova Atualização Para Todos</button>
    </div>
  </div>
</div>

<script>
function getPass() { return document.getElementById('admin-pass').value.trim(); }

function switchTab(name) {
  ['requests', 'licenses', 'generate', 'updates'].forEach(t => {
    document.getElementById('tab-' + t).style.display = (t === name) ? 'block' : 'none';
    document.getElementById('tab-btn-' + t).classList.toggle('active', t === name);
  });
}

function flash(msg, isSuccess=true) {
  const box = document.getElementById('flash-msg');
  const txt = document.getElementById('flash-txt');
  txt.innerHTML = msg;
  box.style.display = 'flex';
  box.style.borderColor = isSuccess ? 'rgba(16,185,129,0.4)' : 'rgba(244,63,94,0.4)';
}

async function api(path, data=null) {
  const headers = { 'X-Admin-Token': getPass() };
  if (data) headers['Content-Type'] = 'application/json';
  const res = await fetch(path, {
    method: data ? 'POST' : 'GET',
    headers,
    body: data ? JSON.stringify(data) : undefined
  });
  return await res.json();
}

async function loadAllData() {
  await Promise.all([loadRequests(), loadLicenses(), loadUpdates()]);
}

async function loadRequests() {
  const res = await api('/api/admin/requests');
  if (res.error) return flash('Erro de autenticação: ' + res.error, false);
  const rows = res.requests || [];
  const tbody = document.getElementById('table-requests-body');
  
  const pending = rows.filter(r => r.status === 'PENDING').length;
  document.getElementById('stat-pending').innerText = pending;
  document.getElementById('badge-pending-count').innerText = pending;

  if (rows.length === 0) {
    tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;color:var(--text-muted);padding:30px;">Nenhuma solicitação recebida ainda.</td></tr>';
    return;
  }

  tbody.innerHTML = rows.map(r => {
    const dt = new Date(r.created_at * 1000).toLocaleString('pt-BR');
    const isPending = r.status === 'PENDING';
    const pillClass = isPending ? 'pending' : (r.status === 'APPROVED' ? 'active' : 'revoked');
    const actions = isPending ? `
      <div style="display:flex;gap:6px;">
        <button class="btn sm" onclick="approveRequest(${r.id}, '${r.hwid}', '${r.name}')">✓ Aprovar & Gerar Key</button>
        <button class="btn sm danger" onclick="rejectRequest(${r.id})">✕ Recusar</button>
      </div>` : `<span style="font-size:12px;color:var(--text-muted);">${r.assigned_key ? '<span class="mono">' + r.assigned_key + '</span>' : 'Concluído'}</span>`;

    return `<tr>
      <td>${dt}</td>
      <td><b>${r.name}</b></td>
      <td>${r.contact}</td>
      <td><span class="mono">${r.hwid}</span></td>
      <td>${r.notes || '-'}</td>
      <td><span class="pill ${pillClass}">${r.status}</span></td>
      <td>${actions}</td>
    </tr>`;
  }).join('');
}

async function approveRequest(id, hwid, name) {
  const tier = prompt("Escolha o Plano de Licença:\\n1 = Vitalício PRO\\n2 = 30 Dias\\n3 = 7 Dias Trial", "1");
  if (!tier) return;
  const tierMap = { '1': 'PRO_LIFETIME', '2': 'PRO_30D', '3': 'TRIAL_7D' };
  const selectedTier = tierMap[tier] || 'PRO_LIFETIME';

  const res = await api('/api/admin/approve_request', { id, hwid, name, tier: selectedTier });
  if (res.success) {
    flash(`✓ <b>Solicitação de ${name} APROVADA!</b> Chave Gerada: <span class="mono" style="font-size:14px;font-weight:bold;">${res.key}</span> (Já vinculada ao HWID)`, true);
    loadAllData();
  } else {
    flash('Falha: ' + (res.error || 'Erro desconhecido'), false);
  }
}

async function rejectRequest(id) {
  if (!confirm("Tem certeza que deseja recusar esta solicitação?")) return;
  const res = await api('/api/admin/reject_request', { id });
  if (res.success) {
    flash('Solicitação recusada com sucesso.');
    loadRequests();
  }
}

async function loadLicenses() {
  const res = await api('/api/admin/licenses');
  if (res.error) return;
  const rows = res.licenses || [];
  const tbody = document.getElementById('table-licenses-body');
  
  const activeCount = rows.filter(l => l.is_active === 1).length;
  document.getElementById('stat-active-lic').innerText = activeCount;

  if (rows.length === 0) {
    tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;color:var(--text-muted);padding:30px;">Nenhuma licença emitida ainda.</td></tr>';
    return;
  }

  tbody.innerHTML = rows.map(l => {
    const isAct = l.is_active === 1;
    const pill = isAct ? '<span class="pill active">Ativa</span>' : '<span class="pill revoked">Revogada</span>';
    const hb = l.last_heartbeat ? new Date(l.last_heartbeat * 1000).toLocaleTimeString('pt-BR') : 'Nunca';
    const exp = l.expires_at ? new Date(l.expires_at * 1000).toLocaleDateString('pt-BR') : 'Vitalício';
    const btnAction = isAct 
      ? `<button class="btn sm danger" onclick="toggleLicense('${l.key}', 0)">Revogar / Bloquear</button>`
      : `<button class="btn sm" onclick="toggleLicense('${l.key}', 1)">Reativar</button>`;

    return `<tr>
      <td><b class="mono">${l.key}</b></td>
      <td>${l.user_name || 'Sem nome'}</td>
      <td><span class="mono">${l.hwid || '<i>Qualquer máquina (livre)</i>'}</span></td>
      <td><b>${l.tier}</b> (${exp})</td>
      <td>${pill}</td>
      <td><span style="font-size:11px;color:var(--text-muted);">${hb}</span></td>
      <td>${btnAction}</td>
    </tr>`;
  }).join('');
}

async function toggleLicense(key, newStatus) {
  const res = await api('/api/admin/toggle_license', { key, is_active: newStatus });
  if (res.success) {
    flash(`Licença <b>${key}</b> ${newStatus === 1 ? 'reativada' : 'revogada'} com sucesso!`);
    loadLicenses();
  }
}

async function submitGenerateKey() {
  const user_name = document.getElementById('gen-user').value.trim();
  const contact = document.getElementById('gen-contact').value.trim();
  const tier = document.getElementById('gen-tier').value;
  const hwid = document.getElementById('gen-hwid').value.trim();

  const res = await api('/api/admin/generate_license', { user_name, contact, tier, hwid });
  if (res.success) {
    flash(`✓ <b>Nova Chave Gerada com Sucesso!</b><br><span class="mono" style="font-size:15px;color:#fff;">${res.key}</span><br>Envie esta chave para o usuário!`, true);
    document.getElementById('gen-user').value = '';
    document.getElementById('gen-contact').value = '';
    document.getElementById('gen-hwid').value = '';
    loadLicenses();
    switchTab('licenses');
  } else {
    flash('Erro: ' + (res.error || 'Falha ao gerar chave'), false);
  }
}

async function loadUpdates() {
  const res = await api('/api/admin/updates');
  if (res.updates && res.updates.length > 0) {
    document.getElementById('stat-version').innerText = 'v' + res.updates[0].version;
  }
}

async function publishUpdate() {
  const version = document.getElementById('upd-version').value.trim();
  const download_url = document.getElementById('upd-url').value.trim();
  const changelog = document.getElementById('upd-changelog').value.trim();

  if (!version) return alert('Informe o número da versão');
  const res = await api('/api/admin/publish_update', { version, download_url, changelog });
  if (res.success) {
    flash(`✓ <b>Atualização v${version} Publicada com Sucesso!</b> Todos os clientes agora a receberão.`, true);
    loadUpdates();
  }
}

document.addEventListener('DOMContentLoaded', loadAllData);
</script>

</body>
</html>
"""


class MasterHandler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code: int, body: Any = b"", ctype: str = "application/json"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False).encode("utf-8")
        elif isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def do_OPTIONS(self):
        self._send(204, b"")

    def _body(self) -> Dict[str, Any]:
        n = int(self.headers.get("Content-Length") or 0)
        if not n:
            return {}
        try:
            return json.loads(self.rfile.read(n).decode("utf-8") or "{}")
        except json.JSONDecodeError:
            return {}

    def _check_admin_auth(self) -> bool:
        token = self.headers.get("X-Admin-Token") or ""
        return token == ADMIN_PASSWORD

    def do_GET(self):
        url = urllib.parse.urlparse(self.path)
        path = url.path
        qs = urllib.parse.parse_qs(url.query)

        # 1. Painel Web Administrativo
        if path in ("/admin", "/admin/"):
            return self._send(200, ADMIN_HTML, "text/html; charset=utf-8")

        # 2. Cliente API: Consulta de status de aprovação de cadastro
        if path == "/api/v1/access/status":
            hwid = qs.get("hwid", [""])[0]
            if not hwid:
                return self._send(400, {"error": "HWID obrigatório"})
            with get_db() as conn:
                row = conn.execute(
                    "SELECT status, assigned_key FROM access_requests WHERE hwid = ? ORDER BY id DESC LIMIT 1",
                    (hwid,)
                ).fetchone()
                if not row:
                    return self._send(200, {"status": "NONE"})
                return self._send(200, {"status": row["status"], "key": row["assigned_key"]})

        # 3. Cliente API: Verificação de atualizações OTA
        if path == "/api/v1/updates/check":
            client_v = qs.get("version", ["0.0.0"])[0]
            with get_db() as conn:
                row = conn.execute(
                    "SELECT version, release_date, changelog, download_url, mandatory FROM updates WHERE is_active = 1 ORDER BY id DESC LIMIT 1"
                ).fetchone()
                if not row:
                    return self._send(200, {"has_update": False})
                latest_v = row["version"]
                has_update = latest_v != client_v
                return self._send(200, {
                    "has_update": has_update,
                    "latest_version": latest_v,
                    "release_date": row["release_date"],
                    "changelog": row["changelog"],
                    "download_url": row["download_url"],
                    "mandatory": bool(row["mandatory"]),
                })

        # 4. Endpoints Protegidos do Admin
        if path.startswith("/api/admin/"):
            if not self._check_admin_auth():
                return self._send(401, {"error": "Senha de administrador incorreta"})
            
            with get_db() as conn:
                if path == "/api/admin/requests":
                    rows = conn.execute("SELECT * FROM access_requests ORDER BY id DESC LIMIT 100").fetchall()
                    return self._send(200, {"requests": [dict(r) for r in rows]})

                if path == "/api/admin/licenses":
                    rows = conn.execute("SELECT * FROM licenses ORDER BY id DESC LIMIT 200").fetchall()
                    return self._send(200, {"licenses": [dict(r) for r in rows]})

                if path == "/api/admin/updates":
                    rows = conn.execute("SELECT * FROM updates ORDER BY id DESC").fetchall()
                    return self._send(200, {"updates": [dict(r) for r in rows]})

        self._send(404, {"error": "Rota não encontrada"})

    def do_POST(self):
        url = urllib.parse.urlparse(self.path)
        path = url.path
        b = self._body()

        # ==========================================
        # ROTAS PÚBLICAS PARA CLIENTES VOIDCORE
        # ==========================================

        # A. Solicitação de Cadastro / Acesso
        if path == "/api/v1/access/request":
            hwid = (b.get("hwid") or "").strip()
            name = (b.get("name") or "").strip()
            contact = (b.get("contact") or "").strip()
            notes = (b.get("notes") or "").strip()
            version = (b.get("client_version") or "").strip()
            ip = self.client_address[0]

            if not hwid or not name or not contact:
                return self._send(400, {"error": "Dados incompletos (HWID, Nome e Contato são obrigatórios)"})

            with get_db() as conn:
                # Se já houver pendente, atualiza; senão cria nova
                existing = conn.execute("SELECT id FROM access_requests WHERE hwid = ? AND status = 'PENDING'", (hwid,)).fetchone()
                now = int(time.time())
                if existing:
                    conn.execute(
                        "UPDATE access_requests SET name = ?, contact = ?, notes = ?, client_version = ?, updated_at = ? WHERE id = ?",
                        (name, contact, notes, version, now, existing["id"])
                    )
                else:
                    conn.execute(
                        "INSERT INTO access_requests (hwid, name, contact, notes, client_version, status, ip_address, created_at, updated_at) VALUES (?, ?, ?, ?, ?, 'PENDING', ?, ?, ?)",
                        (hwid, name, contact, notes, version, ip, now, now)
                    )
            return self._send(200, {
                "success": True,
                "status": "PENDING",
                "message": "Solicitação recebida com sucesso! O administrador foi notificado para aprovação."
            })

        # B. Ativação de Licença com Chave
        if path == "/api/v1/license/activate":
            key = (b.get("key") or "").strip().upper()
            hwid = (b.get("hwid") or "").strip()

            if not key or not hwid:
                return self._send(400, {"error": "Chave e HWID são obrigatórios para ativação"})

            with get_db() as conn:
                lic = conn.execute("SELECT * FROM licenses WHERE key = ?", (key,)).fetchone()
                if not lic:
                    return self._send(403, {"error": "Chave de licença não encontrada ou inválida."})

                if not lic["is_active"]:
                    return self._send(403, {"error": "Esta licença foi revogada pelo administrador."})

                if lic["expires_at"] and time.time() > lic["expires_at"]:
                    return self._send(403, {"error": "Esta licença expirou."})

                # Se a licença já estiver amarrada a outro HWID
                if lic["hwid"] and lic["hwid"] != hwid:
                    return self._send(403, {
                        "error": f"Esta chave já está ativada e bloqueada em outra máquina ({lic['hwid'][:10]}...)."
                    })

                # Se a chave era livre, amarra permanentemente a este HWID
                now = int(time.time())
                if not lic["hwid"]:
                    conn.execute("UPDATE licenses SET hwid = ?, last_heartbeat = ? WHERE id = ?", (hwid, now, lic["id"]))
                else:
                    conn.execute("UPDATE licenses SET last_heartbeat = ? WHERE id = ?", (now, lic["id"]))

                # Gera token criptográfico assinado para o cliente salvar em license.dat
                payload = {
                    "key": key,
                    "hwid": hwid,
                    "user_name": lic["user_name"] or "Usuário VoidCore",
                    "tier": lic["tier"],
                    "expires_at": lic["expires_at"],
                    "activated_at": now,
                }
                token = sign_payload(payload)

                return self._send(200, {
                    "success": True,
                    "token": token,
                    "license": payload,
                })

        # C. Heartbeat de Verificação Contínua
        if path == "/api/v1/license/heartbeat":
            key = (b.get("key") or "").strip().upper()
            hwid = (b.get("hwid") or "").strip()

            with get_db() as conn:
                lic = conn.execute("SELECT is_active, expires_at FROM licenses WHERE key = ? AND hwid = ?", (key, hwid)).fetchone()
                if not lic or not lic["is_active"]:
                    return self._send(200, {"status": "REVOKED"})
                if lic["expires_at"] and time.time() > lic["expires_at"]:
                    return self._send(200, {"status": "EXPIRED"})
                
                conn.execute("UPDATE licenses SET last_heartbeat = ? WHERE key = ?", (int(time.time()), key))
                return self._send(200, {"status": "ACTIVE"})

        # ==========================================
        # ROTAS ADMINISTRATIVAS DO PAINEL ADMIN
        # ==========================================
        if path.startswith("/api/admin/"):
            if not self._check_admin_auth():
                return self._send(401, {"error": "Senha de administrador incorreta"})

            # Aprovar solicitação e gerar chave amarrada
            if path == "/api/admin/approve_request":
                req_id = int(b.get("id"))
                hwid = b.get("hwid")
                name = b.get("name")
                tier = b.get("tier", "PRO_LIFETIME")
                
                now = int(time.time())
                expires_at = None
                if tier == "PRO_30D":
                    expires_at = now + 30 * 86400
                elif tier == "TRIAL_7D":
                    expires_at = now + 7 * 86400

                new_key = generate_key_string()
                with get_db() as conn:
                    # Cria a licença já vinculada ao HWID
                    conn.execute(
                        "INSERT INTO licenses (key, hwid, user_name, contact, tier, created_at, expires_at, is_active, last_heartbeat, notes) VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?)",
                        (new_key, hwid, name, "", tier, now, expires_at, now, f"Aprovado via solicitação #{req_id}")
                    )
                    # Atualiza a solicitação
                    conn.execute(
                        "UPDATE access_requests SET status = 'APPROVED', assigned_key = ?, updated_at = ? WHERE id = ?",
                        (new_key, now, req_id)
                    )

                return self._send(200, {"success": True, "key": new_key})

            # Recusar solicitação
            if path == "/api/admin/reject_request":
                req_id = int(b.get("id"))
                with get_db() as conn:
                    conn.execute("UPDATE access_requests SET status = 'REJECTED', updated_at = ? WHERE id = ?", (int(time.time()), req_id))
                return self._send(200, {"success": True})

            # Gerar licença avulsa
            if path == "/api/admin/generate_license":
                user_name = b.get("user_name") or "Amigo VoidCore"
                contact = b.get("contact") or ""
                tier = b.get("tier", "PRO_LIFETIME")
                hwid = (b.get("hwid") or "").strip() or None

                now = int(time.time())
                expires_at = None
                if tier == "PRO_30D":
                    expires_at = now + 30 * 86400
                elif tier == "PRO_90D":
                    expires_at = now + 90 * 86400
                elif tier == "TRIAL_7D":
                    expires_at = now + 7 * 86400

                new_key = generate_key_string()
                with get_db() as conn:
                    conn.execute(
                        "INSERT INTO licenses (key, hwid, user_name, contact, tier, created_at, expires_at, is_active, notes) VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?)",
                        (new_key, hwid, user_name, contact, tier, now, expires_at, "Gerada manualmente no painel")
                    )
                return self._send(200, {"success": True, "key": new_key})

            # Alternar status da licença (Revogar / Ativar)
            if path == "/api/admin/toggle_license":
                key = b.get("key")
                new_act = int(b.get("is_active", 0))
                with get_db() as conn:
                    conn.execute("UPDATE licenses SET is_active = ? WHERE key = ?", (new_act, key))
                return self._send(200, {"success": True})

            # Publicar atualização OTA
            if path == "/api/admin/publish_update":
                version = b.get("version")
                download_url = b.get("download_url") or ""
                changelog = b.get("changelog") or ""
                with get_db() as conn:
                    conn.execute(
                        "INSERT INTO updates (version, release_date, changelog, download_url, mandatory, is_active) VALUES (?, ?, ?, ?, 0, 1)",
                        (version, int(time.time()), changelog, download_url)
                    )
                return self._send(200, {"success": True})

        self._send(404, {"error": "Rota não encontrada"})


def run_master_server():
    server = ThreadingHTTPServer((HOST, PORT), MasterHandler)
    print("=" * 60)
    print(f"[*] VOIDCORE MASTER CONTROL SERVER INICIADO!")
    print(f"[*] Escutando em: http://127.0.0.1:{PORT}")
    print(f"[*] Painel Admin Web: http://127.0.0.1:{PORT}/admin")
    print(f"[*] Senha Padrão do Painel: {ADMIN_PASSWORD}")
    print(f"[*] Banco de Dados: {DB_FILE.name}")
    print("=" * 60)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[!] Encerrando servidor.")
        server.server_close()


if __name__ == "__main__":
    run_master_server()
