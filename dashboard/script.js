document.addEventListener('DOMContentLoaded', async () => {
    // Check Auth Status
    try {
        const response = await fetch('/api/me');
        if (response.ok) {
            const data = await response.json();
            if (data.authenticated) {
                initializeDashboard(data);
                document.body.classList.remove('auth-pending');
            }
        }
    } catch (error) {
        console.error('Auth check failed:', error);
    }

    // Load dynamic stats if authenticated
    if (!document.body.classList.contains('auth-pending')) {
        loadStats();
    }
});

function initializeDashboard(data) {
    const user = data.discord;
    const internal = data.internal;
    const guilds = data.guilds || [];

    // Update Sidebar User Pill
    const avatarImg = user.avatar
        ? `https://cdn.discordapp.com/avatars/${user.id}/${user.avatar}.png`
        : null;

    const userPill = document.querySelector('.user-pill');
    if (userPill) {
        const avatarDiv = userPill.querySelector('.avatar');
        if (avatarImg) {
            avatarDiv.innerHTML = `<img src="${avatarImg}" style="width:100%; height:100%; border-radius:50%;">`;
        } else {
            avatarDiv.textContent = user.username.charAt(0).toUpperCase();
        }
        userPill.querySelector('.user-name').textContent = user.username;
        userPill.querySelector('.user-role').textContent = internal.levels.level >= 10 ? 'Elite Member' : 'System User';
    }

    // Update Welcome Title
    const welcomeTitle = document.querySelector('.welcome-text h2 span');
    if (welcomeTitle) {
        welcomeTitle.textContent = user.username;
    }

    const welcomeDesc = document.querySelector('.welcome-text p');
    if (welcomeDesc) {
        welcomeDesc.textContent = `Prime AI is currently connected to ${guilds.length} of your servers.`;
    }

    // Populate Guilds List in Activity Feed area (or dedicated section)
    const logList = document.querySelector('.log-list');
    if (logList && guilds.length > 0) {
        logList.innerHTML = '<h3>Your Connected Servers</h3>';
        guilds.slice(0, 8).forEach(guild => {
            const iconUrl = guild.icon
                ? `https://cdn.discordapp.com/icons/${guild.id}/${guild.icon}.png`
                : 'https://cdn.discordapp.com/embed/avatars/0.png';

            const guildItem = document.createElement('div');
            guildItem.className = 'log-item';
            guildItem.innerHTML = `
                <div class="log-time"><img src="${iconUrl}" style="width:30px; border-radius:8px;"></div>
                <div class="log-content">
                    <strong>${guild.name}</strong><br>
                    <span style="font-size:0.8rem; opacity:0.6;">${guild.permissions_new ? 'Administrator' : 'Member'}</span>
                </div>
            `;
            logList.appendChild(guildItem);
        });
    }
}

async function loadStats() {
    try {
        const response = await fetch('/api/stats');
        const stats = await response.json();

        // Update Stats Cards
        const totalUsersEl = document.querySelectorAll('.stat-info h3')[0];
        if (totalUsersEl) totalUsersEl.textContent = stats.total_users.toLocaleString();

        const statusLabel = document.querySelector('.status-indicator span');
        if (statusLabel) statusLabel.textContent = `SYSTEM ${stats.system_status}`;

        const uptimeVal = document.querySelector('.m-val');
        if (uptimeVal) uptimeVal.textContent = '99.9%';
    } catch (error) {
        console.warn('Failed to load stats');
    }
}

// Back to Top Functionality
function scrollToTop() {
    window.scrollTo({
        top: 0,
        behavior: 'smooth'
    });
}

window.addEventListener('scroll', () => {
    const btt = document.getElementById('backToTop');
    if (window.scrollY > 300) {
        btt.classList.add('active');
    } else {
        btt.classList.remove('active');
    }
});
