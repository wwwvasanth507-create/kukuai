/**
 * Nexus AI v6 - Simplified Logic
 * - Isolated chat histories
 * - Admin selection for AI mode
 */

let currentUser = null;
let currentToken = localStorage.getItem('nexus_auth_v6');

// Selectors
const screens = {
    auth: document.getElementById('login-screen'),
    dash: document.getElementById('dashboard')
};

const components = {
    sidebar: document.querySelector('.sidebar'),
    chatBox: document.getElementById('chat-messages'),
    chatIn: document.getElementById('chat-input'),
    aiMode: document.getElementById('ai-mode-selector'),
    aiDropdown: document.getElementById('ai-mode-dropdown'),
    avatar: document.getElementById('user-avatar-char')
};

// Start
document.addEventListener('DOMContentLoaded', () => {
    if (currentToken) verifySession();
    else openAuth();
    initApp();
});

async function verifySession() {
    try {
        const res = await fetch('/api/me', { headers: { 'Authorization': `Bearer ${currentToken}` } });
        if (res.ok) {
            currentUser = await res.json();
            openDashboard();
        } else deauth();
    } catch (e) { deauth(); }
}

function openAuth() {
    screens.auth.classList.add('active');
    screens.dash.classList.remove('active');
}

function openDashboard() {
    screens.auth.classList.remove('active');
    screens.dash.classList.add('active');
    
    // Header Data
    document.getElementById('display-name').textContent = currentUser.username;
    document.getElementById('display-role').textContent = currentUser.role.charAt(0).toUpperCase() + currentUser.role.slice(1);
    components.avatar.textContent = currentUser.username.charAt(0).toUpperCase();

    // Permissions
    document.querySelectorAll('.nav-links li').forEach(li => {
        const roles = li.dataset.role.split(' ');
        li.style.display = roles.includes(currentUser.role) ? 'flex' : 'none';
    });

    // Special Admin UI
    components.aiMode.style.display = currentUser.role === 'admin' ? 'block' : 'none';
    
    switchTab('chat');
}

function deauth() {
    localStorage.removeItem('nexus_auth_v6');
    currentUser = null;
    currentToken = null;
    openAuth();
}

function initApp() {
    // Auth Forms
    document.getElementById('show-register').onclick = () => {
        document.getElementById('login-form').style.display = 'none';
        document.getElementById('register-form').style.display = 'block';
    };
    document.getElementById('show-login').onclick = () => {
        document.getElementById('login-form').style.display = 'block';
        document.getElementById('register-form').style.display = 'none';
    };

    document.getElementById('login-form').onsubmit = handleAuth;
    document.getElementById('register-form').onsubmit = handleAuth;

    // Sidebar & Navigation
    document.getElementById('menu-toggle').onclick = (e) => { e.stopPropagation(); components.sidebar.classList.toggle('open'); };
    document.addEventListener('click', (e) => {
        if (components.sidebar.classList.contains('open') && !components.sidebar.contains(e.target)) components.sidebar.classList.remove('open');
    });

    document.querySelectorAll('.nav-links li').forEach(li => {
        li.onclick = () => { switchTab(li.dataset.tab); components.sidebar.classList.remove('open'); };
    });

    // Chat
    document.getElementById('send-msg').onclick = askAI;
    components.chatIn.onkeypress = (e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); askAI(); } };

    // Logout
    document.getElementById('logout-btn').onclick = deauth;
    document.getElementById('top-logout-btn').onclick = deauth;

    // Chat Tools
    document.getElementById('clear-chat-btn').onclick = clearChat;

    // Tools
    const dropZone = document.getElementById('drop-zone');
    dropZone.onclick = () => document.getElementById('db-file').click();
    
    // Drag and Drop
    ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(evt => {
        dropZone.addEventListener(evt, (e) => { e.preventDefault(); e.stopPropagation(); }, false);
    });

    dropZone.addEventListener('dragover', () => dropZone.classList.add('dragging'));
    dropZone.addEventListener('dragleave', () => dropZone.classList.remove('dragging'));
    dropZone.addEventListener('drop', (e) => {
        dropZone.classList.remove('dragging');
        document.getElementById('db-file').files = e.dataTransfer.files;
        const count = e.dataTransfer.files.length;
        document.querySelector('#drop-zone p').textContent = count > 0 ? `${count} files selected` : "Click to select .txt files";
    });

    document.getElementById('db-file').onchange = (e) => {
        const count = e.target.files.length;
        document.querySelector('#drop-zone p').textContent = count > 0 ? `${count} files selected` : "Click to select .txt files";
    };
    document.getElementById('upload-db-form').onsubmit = uploadFile;
    document.getElementById('create-user-form').onsubmit = createUser;
    document.querySelector('.close-modal').onclick = () => document.getElementById('edit-db-modal').style.display = 'none';
    document.getElementById('save-db-btn').onclick = saveModifiedFile;
}

// Logic Functions
async function handleAuth(e) {
    e.preventDefault();
    const isReg = e.target.id === 'register-form';
    const body = isReg ? 
        JSON.stringify({ username: document.getElementById('reg-username').value, password: document.getElementById('reg-password').value, role: 'user' }) : 
        new URLSearchParams({ username: document.getElementById('username').value, password: document.getElementById('password').value });

    const res = await fetch(isReg ? '/api/register' : '/token', {
        method: 'POST',
        headers: isReg ? { 'Content-Type': 'application/json' } : {},
        body: body
    });

    if (res.ok) {
        if (isReg) { alert("Registration done. Please log in."); document.getElementById('show-login').click(); }
        else {
            const data = await res.json();
            currentToken = data.access_token;
            localStorage.setItem('nexus_auth_v6', currentToken);
            verifySession();
        }
    } else { alert("Error: Please check your details."); }
}

async function switchTab(tabId) {
    document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.nav-links li').forEach(l => l.classList.remove('active'));
    
    document.getElementById(`tab-${tabId}`).classList.add('active');
    const link = document.querySelector(`li[data-tab="${tabId}"]`);
    if(link) link.classList.add('active');

    // Toggle Chat Specific Tools
    document.getElementById('clear-chat-btn').style.display = tabId === 'chat' ? 'flex' : 'none';

    if (tabId === 'chat') loadHistory();
    if (tabId === 'database') loadFileList();
    if (tabId === 'management') loadMemberList();
    if (tabId === 'storage') loadStorageStats();
}

async function askAI() {
    const text = components.chatIn.value.trim();
    if (!text) return;
    
    appendMsg('user', text);
    components.chatIn.value = '';
    const loading = appendMsg('bot', '<i class="fas fa-spinner fa-spin"></i> Thinking...');

    const res = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${currentToken}` },
        body: JSON.stringify({ message: text, mode: components.aiDropdown ? components.aiDropdown.value : 'local' })
    });
    const data = await res.json();
    loading.innerHTML = data.response;
}

function appendMsg(role, text) {
    const div = document.createElement('div');
    div.className = `message ${role}`;
    div.innerHTML = `<div class="message-content">${text}</div>`;
    components.chatBox.appendChild(div);
    components.chatBox.scrollTop = components.chatBox.scrollHeight;
    return div.querySelector('.message-content');
}

async function loadHistory() {
    const res = await fetch('/api/chat/history', { headers: { 'Authorization': `Bearer ${currentToken}` } });
    const hist = await res.json();
    components.chatBox.innerHTML = '';
    hist.forEach(h => {
        appendMsg('user', h.message);
        appendMsg('bot', h.response);
    });
    if (hist.length === 0) appendMsg('bot', `Hello ${currentUser.username}, how can I help you today?`);
}

async function clearChat() {
    if (confirm("Are you sure you want to delete your entire chat history? This cannot be undone.")) {
        const res = await fetch('/api/chat/clear', {
            method: 'DELETE',
            headers: { 'Authorization': `Bearer ${currentToken}` }
        });
        if (res.ok) loadHistory();
    }
}

async function loadFileList() {
    const res = await fetch('/api/database/files', { headers: { 'Authorization': `Bearer ${currentToken}` } });
    const files = await res.json();
    document.getElementById('db-files-list').innerHTML = files.map(f => {
        const date = new Date(f.mtime * 1000).toLocaleString();
        return `
            <div class="db-card glass-card">
                <div class="card-badge">Newest</div>
                <h4>${f.name}</h4>
                <div class="meta-row">
                    <p class="meta">Size: ${(f.size/1024).toFixed(1)} KB</p>
                    <p class="meta">Date: ${date}</p>
                </div>
                <div class="card-ops">
                    <button class="btn-small" onclick="editKnowledge('${f.name}')"><i class="fas fa-edit"></i> Edit</button>
                    <button class="btn-small btn-danger" onclick="deleteKnowledge('${f.name}')"><i class="fas fa-trash"></i> Delete</button>
                </div>
            </div>
        `;
    }).join('') || '<p style="text-align:center; opacity:0.5">No files added yet.</p>';
}

window.editKnowledge = async (name) => {
    const res = await fetch(`/api/database/content/${name}`, { headers: { 'Authorization': `Bearer ${currentToken}` } });
    const data = await res.json();
    document.getElementById('modal-db-name').textContent = name;
    document.getElementById('modal-db-name').dataset.name = name;
    document.getElementById('db-content-editor').value = data.content;
    document.getElementById('edit-db-modal').style.display = 'flex';
};

async function saveModifiedFile() {
    const name = document.getElementById('modal-db-name').dataset.name;
    const content = document.getElementById('db-content-editor').value;
    await fetch(`/api/database/save/${name}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${currentToken}` },
        body: JSON.stringify({ content })
    });
    document.getElementById('edit-db-modal').style.display = 'none';
    loadFileList();
}

window.deleteKnowledge = async (name) => {
    if(confirm(`Remove this file permanently?`)) {
        await fetch(`/api/database/${name}`, { method: 'DELETE', headers: { 'Authorization': `Bearer ${currentToken}` } });
        loadFileList();
    }
};

async function uploadFile(e) {
    e.preventDefault();
    const files = document.getElementById('db-file').files;
    if (files.length === 0) return;
    
    const fd = new FormData();
    for (let i = 0; i < files.length; i++) {
        fd.append('files', files[i]);
    }
    
    await fetch('/api/trainer/upload', {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${currentToken}` },
        body: fd
    });
    document.getElementById('upload-db-form').reset();
    loadFileList();
}

async function loadMemberList() {
    const res = await fetch('/api/admin/users', { headers: { 'Authorization': `Bearer ${currentToken}` } });
    const users = await res.json();
    document.querySelector('#users-table tbody').innerHTML = users.map(u => `
        <tr>
            <td>${u.username}</td>
            <td><span class="badge ${u.role}">${u.role}</span></td>
            <td>${u.username !== 'admin' ? `<button onclick="removeMember('${u.username}')" style="background:none; border:none; color:red; cursor:pointer">Remove</button>` : '-'}</td>
        </tr>
    `).join('');
}

window.removeMember = async (name) => {
    if(confirm(`Deactivate member ${name}?`)) {
        await fetch(`/api/admin/users/${name}`, { method: 'DELETE', headers: { 'Authorization': `Bearer ${currentToken}` } });
        loadMemberList();
    }
};

async function createUser(e) {
    e.preventDefault();
    const body = { username: document.getElementById('new-user-name').value, password: document.getElementById('new-user-pass').value, role: document.getElementById('new-user-role').value };
    await fetch('/api/admin/users', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${currentToken}` },
        body: JSON.stringify(body)
    });
    e.target.reset();
    loadMemberList();
}

async function loadStorageStats() {
    const res = await fetch('/api/admin/storage', { headers: { 'Authorization': `Bearer ${currentToken}` } });
    const data = await res.json();
    document.getElementById('total-storage').textContent = `${data.total_storage_mb} MB Used`;
}
