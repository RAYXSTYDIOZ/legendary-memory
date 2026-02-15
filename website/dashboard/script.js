const Dashboard = {
    token: localStorage.getItem('prime_session_token'),
    user: null,
    guilds: [],

    async init() {
        // Sync token from URL
        const params = new URLSearchParams(window.location.search);
        const newToken = params.get('session_token');
        if (newToken) {
            this.token = newToken;
            localStorage.setItem('prime_session_token', newToken);
            window.history.replaceState({}, document.title, window.location.pathname);
        }

        this.startClock();
        this.bindNav();

        if (this.token) {
            await this.boot();
        } else {
            this.logout();
        }
    },

    async boot() {
        try {
            const res = await fetch(`/api/me`, {
                headers: { 'X-Session-Token': this.token }
            });
            if (!res.ok) throw new Error();
            const data = await res.json();
            if (data.authenticated) {
                this.user = data.user;
                this.guilds = data.guilds;
                this.renderBase();
                this.renderServers();
                this.fetchSystemStats();
                document.body.classList.add('authenticated');
                document.body.classList.remove('loading');
                return;
            }
        } catch (e) {
            console.error("Boot sequence failed.");
        }
        this.logout();
    },

    logout() {
        localStorage.removeItem('prime_session_token');
        this.token = null;
        document.body.classList.remove('authenticated');
        document.body.classList.remove('loading');
    },

    renderBase() {
        document.getElementById('userName').textContent = this.user.name;
        document.getElementById('welcomeName').textContent = this.user.name;
        if (this.user.avatar) {
            document.getElementById('userAvatar').src = `https://cdn.discordapp.com/avatars/${this.user.id}/${this.user.avatar}.png`;
        } else {
            document.getElementById('userAvatar').src = `https://cdn.discordapp.com/embed/avatars/0.png`;
        }
    },

    renderServers() {
        const grid = document.getElementById('guildGrid');
        grid.innerHTML = '';

        const managed = this.guilds.filter(g => (g.permissions & 0x8) || (g.permissions & 0x20));

        if (managed.length === 0) {
            grid.innerHTML = '<p style="opacity:0.3">No managed servers found.</p>';
            return;
        }

        managed.forEach(g => {
            const icon = g.icon ? `https://cdn.discordapp.com/icons/${g.id}/${g.icon}.png` : 'https://cdn.discordapp.com/embed/avatars/0.png';
            const card = document.createElement('div');
            card.className = `guild-card ${g.bot_present ? '' : 'missing'}`;

            card.innerHTML = `
                <img src="${icon}">
                <div class="g-meta">
                    <strong>${g.name}</strong>
                    <div class="tag">${g.bot_present ? 'ACTIVE' : 'INVITE REQUIRED'}</div>
                </div>
            `;

            card.onclick = () => {
                if (g.bot_present) this.openConfig(g);
                else this.invite(g.id);
            };
            grid.appendChild(card);
        });
    },

    async fetchSystemStats() {
        try {
            const res = await fetch(`/api/dashboard/stats`, {
                headers: { 'X-Session-Token': this.token }
            });
            const data = await res.json();
            document.getElementById('statUsers').textContent = (data.users || 0).toLocaleString();
            document.getElementById('statMsgs').textContent = ((data.messages || 0) / 1000).toFixed(1) + 'K';

            // Render Leaderboard if in data
            if (data.leaderboard) {
                const list = document.getElementById('leaderboardList');
                list.innerHTML = data.leaderboard.map((u, i) => `
                    <div class="rank-row">
                        <div class="u-info">
                            <b>#${i + 1}</b>
                            <span>ID: ${u.id.toString().slice(-4)}</span>
                        </div>
                        <div class="u-info">
                            <b>LVL ${u.level}</b>
                            <span>${u.xp} XP</span>
                        </div>
                    </div>
                `).join('');
            }
        } catch (e) { }
    },

    async openConfig(guild) {
        this.activeGuild = guild;

        // Show the customization tab
        this.switchTab('customization');
        document.getElementById('custTitle').textContent = guild.name.toUpperCase();
        document.getElementById('custFormContainer').style.display = 'block';
        document.getElementById('aiArchitectSection').style.display = 'block';
        document.getElementById('noGuildSelected').style.display = 'none';

        try {
            const res = await fetch(`/api/guilds/${guild.id}/settings`, {
                headers: { 'X-Session-Token': this.token }
            });
            if (res.ok) {
                const s = await res.json();

                // CORE
                document.getElementById('mCfgPrefix').value = s.prefix || '!';
                document.getElementById('mCfgVibe').value = s.vibe || 'chill';

                // CHANNELS
                document.getElementById('mCfgWelcomeChan').value = s.welcome_channel || '';
                document.getElementById('mCfgLogChan').value = s.log_channel || '';
                document.getElementById('mCfgRulesChan').value = s.rules_channel || '';
                document.getElementById('mCfgRoleReqChan').value = s.role_request_channel || '';
                document.getElementById('mCfgVerifyChan').value = s.verification_channel || '';
                document.getElementById('mCfgLevelChan').value = s.leveling_channel || '';
                document.getElementById('mCfgGeneralChan').value = s.general_channel || '';

                // ROLES
                document.getElementById('mCfgVerifiedRole').value = s.verified_role || '';
                document.getElementById('mCfgUnverifiedRole').value = s.unverified_role || '';
                document.getElementById('mCfgMutedRole').value = s.muted_role || '';

                // SOFTWARE
                document.getElementById('mCfgAeRole').value = s.ae_role || '';
                document.getElementById('mCfgAmRole').value = s.am_role || '';
                document.getElementById('mCfgCapcutRole').value = s.capcut_role || '';
                document.getElementById('mCfgPrRole').value = s.pr_role || '';
                document.getElementById('mCfgPsRole').value = s.ps_role || '';

                // ADVANCED
                document.getElementById('mCfgAesthetic').value = s.aesthetic_overlay || '';
                document.getElementById('mCfgPrompt').value = s.custom_system_prompt || '';
                document.getElementById('mCfgRoleChan').value = s.roles_channel || '';

                // Fetch Roles for suggestions
                this.fetchRoles(guild.id);
            }
        } catch (e) { }
    },

    async fetchRoles(guildId) {
        try {
            const res = await fetch(`/api/guilds/${guildId}/roles`, {
                headers: { 'X-Session-Token': this.token }
            });
            if (res.ok) {
                this.currentRoles = await res.json();
                console.log("Fetched Roles:", this.currentRoles);
            }
        } catch (e) { }
    },

    switchTab(tabId) {
        document.querySelectorAll('.nav-item').forEach(btn => {
            if (btn.getAttribute('data-tab') === tabId) btn.classList.add('active');
            else btn.classList.remove('active');
        });
        document.querySelectorAll('.tab').forEach(el => {
            if (el.id === `tab-${tabId}`) el.classList.add('active');
            else el.classList.remove('active');
        });
    },

    async invite(id) {
        try {
            const res = await fetch(`/api/invite-url?guild_id=${id}`);
            const data = await res.json();
            window.open(data.url, '_blank');
        } catch (e) { }
    },

    bindNav() {
        document.querySelectorAll('.nav-item').forEach(btn => {
            btn.onclick = () => {
                const tab = btn.getAttribute('data-tab');
                document.querySelectorAll('.nav-item, .tab').forEach(el => el.classList.remove('active'));
                btn.classList.add('active');
                document.getElementById(`tab-${tab}`).classList.add('active');
            };
        });
    },

    startClock() {
        setInterval(() => {
            document.getElementById('osClock').textContent = new Date().toLocaleTimeString();
        }, 1000);
    }
};



document.addEventListener('DOMContentLoaded', () => Dashboard.init());

function closeModal() { document.getElementById('configModal').classList.remove('active'); }

async function triggerAction(action) {
    if (!Dashboard.activeGuild) return;

    // Find the button that was clicked to show status
    const btn = event.target;
    const originalText = btn.textContent;
    btn.textContent = "SENDING...";
    btn.disabled = true;

    try {
        const res = await fetch(`/api/guilds/${Dashboard.activeGuild.id}/trigger?token=${Dashboard.token}`, {
            method: 'POST',
            body: JSON.stringify({ action }),
            headers: { 'Content-Type': 'application/json' }
        });
        const data = await res.json();
        if (data.status === 'success') {
            btn.textContent = "✓ SENT";
            btn.style.color = "#00ffaa";
        } else {
            btn.textContent = "❌ ERROR";
            btn.style.color = "#ff4d4d";
            console.error(data.error);
        }
    } catch (e) {
        btn.textContent = "❌ FAIL";
    }

    setTimeout(() => {
        btn.textContent = originalText;
        btn.style.color = "";
        btn.disabled = false;
    }, 2000);
}

async function saveActiveSettings() {
    if (!Dashboard.activeGuild) return;
    const btn = document.querySelector('.btn-sync-top');
    const oldText = btn.textContent;
    btn.textContent = "SYNCING SIGNALS...";

    const data = {
        prefix: document.getElementById('mCfgPrefix').value,
        vibe: document.getElementById('mCfgVibe').value,
        welcome_channel: document.getElementById('mCfgWelcomeChan').value,
        log_channel: document.getElementById('mCfgLogChan').value,
        rules_channel: document.getElementById('mCfgRulesChan').value,
        role_request_channel: document.getElementById('mCfgRoleReqChan').value,
        verification_channel: document.getElementById('mCfgVerifyChan').value,
        leveling_channel: document.getElementById('mCfgLevelChan').value,
        general_channel: document.getElementById('mCfgGeneralChan').value,
        verified_role: document.getElementById('mCfgVerifiedRole').value,
        unverified_role: document.getElementById('mCfgUnverifiedRole').value,
        muted_role: document.getElementById('mCfgMutedRole').value,
        ae_role: document.getElementById('mCfgAeRole').value,
        am_role: document.getElementById('mCfgAmRole').value,
        capcut_role: document.getElementById('mCfgCapcutRole').value,
        pr_role: document.getElementById('mCfgPrRole').value,
        ps_role: document.getElementById('mCfgPsRole').value,
        aesthetic_overlay: document.getElementById('mCfgAesthetic').value,
        custom_system_prompt: document.getElementById('mCfgPrompt').value,
        roles_channel: document.getElementById('mCfgRoleChan').value
    };

    try {
        const res = await fetch(`/api/guilds/${Dashboard.activeGuild.id}/settings`, {
            method: 'POST',
            body: JSON.stringify(data),
            headers: {
                'Content-Type': 'application/json',
                'X-Session-Token': Dashboard.token
            }
        });
        btn.textContent = "✓ SIGNALS SYNCED";
        setTimeout(() => btn.textContent = oldText, 2000);
    } catch (e) {
        btn.textContent = "❌ SYNC FAILED";
        setTimeout(() => btn.textContent = oldText, 2000);
    }
}

async function triggerAiBuild() {
    if (!Dashboard.activeGuild) return;
    const promptField = document.getElementById('aiArchPrompt');
    const prompt = promptField.value.trim();
    if (!prompt) return alert("Please describe your server architecture first.");

    const btn = document.querySelector('.btn-arch');
    const oldText = btn.textContent;
    btn.disabled = true;
    btn.textContent = "BRAINSTORMING STRUCTURE...";

    try {
        const res = await fetch(`/api/guilds/${Dashboard.activeGuild.id}/ai-plan`, {
            method: 'POST',
            body: JSON.stringify({ prompt }),
            headers: {
                'Content-Type': 'application/json',
                'X-Session-Token': Dashboard.token
            }
        });

        if (res.status === 401) throw new Error("Unauthorized: Please log in again.");
        if (!res.ok) throw new Error(`HTTP Error: ${res.status}`);

        const data = await res.json();

        if (data.status === "success") {
            window.activeAiPlan = data.plan;
            const list = document.getElementById('aiPlanList');
            document.getElementById('aiArchPlanReview').style.display = 'block';

            list.innerHTML = data.plan.map(item => `
                <div class="plan-item">
                    <b style="color: ${item.color || 'var(--p)'}">${item.icon || '🛠️'} ${item.action.replace('create_', '')}</b>
                    <span>${item.name} ${item.type ? `(${item.type})` : ''}</span>
                </div>
            `).join('');

            btn.disabled = false;
            btn.textContent = "PLAN GENERATED";
        } else {
            throw new Error(data.error || "Brainstorm failed");
        }
    } catch (e) {
        btn.textContent = "AI CALCULATION ERROR";
        setTimeout(() => {
            btn.disabled = false;
            btn.textContent = oldText;
        }, 3000);
        console.error("Architect Error:", e);
        alert(e.message);
    }
}

async function executeAiBuild() {
    if (!window.activeAiPlan) return;
    const btn = document.querySelector('#aiArchPlanReview .btn-arch');
    const oldText = btn.textContent;
    btn.disabled = true;
    btn.textContent = "MANIFESTING ARCHITECTURE...";

    try {
        const res = await fetch(`/api/guilds/${Dashboard.activeGuild.id}/ai-execute`, {
            method: 'POST',
            body: JSON.stringify({ plan: window.activeAiPlan }),
            headers: {
                'Content-Type': 'application/json',
                'X-Session-Token': Dashboard.token
            }
        });
        const data = await res.json();

        if (data.status === "success") {
            btn.textContent = "✓ ACTION COMPLETE - IT'S DONE!";
            btn.style.color = "#00ffaa";
            document.getElementById('aiArchPrompt').value = "";
            setTimeout(() => {
                document.getElementById('aiArchPlanReview').style.display = 'none';
                btn.disabled = false;
                btn.textContent = oldText;
            }, 4000);
        } else {
            throw new Error(data.error || "Manifestation failed");
        }
    } catch (e) {
        btn.textContent = "EXECUTION ERROR";
        setTimeout(() => {
            btn.disabled = false;
            btn.textContent = oldText;
        }, 3000);
        alert(e.message);
    }
}

async function suggestRoles() {
    if (!Dashboard.currentRoles || Dashboard.currentRoles.length === 0) {
        const btn = event.target;
        btn.textContent = "SCANNING...";
        await Dashboard.fetchRoles(Dashboard.activeGuild.id);
        btn.textContent = "AI SUGGEST";
    }

    const roles = Dashboard.currentRoles;
    const mappings = {
        'mCfgAeRole': ['ae', 'after effects', 'vfx'],
        'mCfgAmRole': ['am', 'alight motion'],
        'mCfgCapcutRole': ['capcut', 'mobile'],
        'mCfgPrRole': ['pr', 'premiere'],
        'mCfgPsRole': ['ps', 'photoshop']
    };

    let foundCount = 0;
    for (const [fieldId, keywords] of Object.entries(mappings)) {
        const match = roles.find(r => keywords.some(k => r.name.toLowerCase().includes(k)));
        if (match) {
            document.getElementById(fieldId).value = match.id;
            foundCount++;
        }
    }

    if (foundCount > 0) {
        alert(`Successfully mapped ${foundCount} roles based on server scanning!`);
    } else {
        alert("No clear matches found. You can try using the AI Architect to create these roles for you first.");
    }
}
