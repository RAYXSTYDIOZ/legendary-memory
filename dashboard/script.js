// Prime AI Dashboard Interactivity

document.addEventListener('DOMContentLoaded', () => {
    // 1. Simulate dynamic stats updates
    const statCards = document.querySelectorAll('.stat-info h3');

    function animateValue(obj, start, end, duration) {
        let startTimestamp = null;
        const step = (timestamp) => {
            if (!startTimestamp) startTimestamp = timestamp;
            const progress = Math.min((timestamp - startTimestamp) / duration, 1);
            const val = Math.floor(progress * (end - start) + start);
            obj.innerHTML = val.toLocaleString() + (obj.innerHTML.includes('k') ? 'k' : '');
            if (progress < 1) {
                window.requestAnimationFrame(step);
            }
        };
        window.requestAnimationFrame(step);
    }

    // Small delay before pulse
    setTimeout(() => {
        // Just a subtle flicker effect for data
        statCards.forEach((card, index) => {
            const currentVal = parseInt(card.innerText.replace(/[^0-9]/g, ''));
            // simulate a small increase randomly
            const increase = Math.floor(Math.random() * 5) + 1;
            // animateValue(card, currentVal, currentVal + increase, 2000);
        });
    }, 2000);

    // 2. Search bar focus effect
    const searchBar = document.querySelector('.search-bar');
    const searchInput = document.querySelector('.search-bar input');

    searchInput.addEventListener('focus', () => {
        searchBar.style.borderColor = 'var(--p)';
        searchBar.style.boxShadow = '0 0 15px rgba(0, 255, 170, 0.1)';
    });

    searchInput.addEventListener('blur', () => {
        searchBar.style.borderColor = 'var(--border)';
        searchBar.style.boxShadow = 'none';
    });

    // 3. Simple log addition simulation
    const logList = document.querySelector('.log-list');
    const activities = [
        "Updated user memory for @BMR.",
        "Detected 3 potential spam messages in 'Creators Heaven'.",
        "Successfully resumed 2 pending reminders.",
        "Gemini response generated for !ask command in DM.",
        "Captcha solved correctly by @Newbie_Edits."
    ];

    function addRandomLog() {
        const activity = activities[Math.floor(Math.random() * activities.length)];
        const logItem = document.createElement('div');
        logItem.className = 'log-item';
        logItem.style.opacity = '0';
        logItem.style.transform = 'translateX(-20px)';
        logItem.style.transition = '0.5s';

        logItem.innerHTML = `
            <div class="log-time">Just now</div>
            <div class="log-content">
                <strong>System:</strong> ${activity}
            </div>
        `;

        logList.insertBefore(logItem, logList.firstChild);

        // Trigger animation
        setTimeout(() => {
            logItem.style.opacity = '1';
            logItem.style.transform = 'translateX(0)';
        }, 100);

        // Remove last item if too many
        if (logList.children.length > 8) {
            logList.lastElementChild.remove();
        }
    }

    // Add a new log every 15-30 seconds
    setInterval(addRandomLog, Math.random() * 15000 + 15000);

    // 4. Hover effect for Sidebar Nav
    const navItems = document.querySelectorAll('.nav-item');
    navItems.forEach(item => {
        item.addEventListener('click', (e) => {
            navItems.forEach(i => i.classList.remove('active'));
            item.classList.add('active');
        });
    });

    console.log("Prime AI Dashboard Initialized.");
});

function scrollToTop() {
    window.scrollTo({
        top: 0,
        behavior: 'smooth'
    });
}

window.addEventListener('scroll', () => {
    const btt = document.getElementById('backToTop');
    if (window.scrollY > 200) {
        btt.classList.add('active');
    } else {
        btt.classList.remove('active');
    }
});
