document.addEventListener('DOMContentLoaded', () => {
    const homeTabButton = document.getElementById('home-tab');
    if (homeTabButton) {
        homeTabButton.addEventListener('click', loadDashboardData);
        // Load initial data if Home is the default active tab
        if (homeTabButton.getAttribute('aria-selected') === 'true') {
            loadDashboardData();
        }
    }

    // Auto-refresh dashboard every 30 seconds if Home tab is active
    setInterval(() => {
        const homeTab = document.getElementById('home-tab');
        if (homeTab && homeTab.getAttribute('aria-selected') === 'true') {
            loadDashboardData();
        }
    }, 30000);
});

async function loadDashboardData() {
    try {
        const response = await fetch('/api/dashboard/stats');
        if (!response.ok) throw new Error('Failed to fetch dashboard stats');
        const data = await response.json();

        // 1. Tenants
        updateElement('dash-tenants-total', data.tenants.total);
        updateElement('dash-tenants-configured', data.tenants.configured);
        updateElement('dash-tenants-unconfigured', data.tenants.unconfigured);

        // 2. Audits
        updateElement('dash-audits-total', data.audits.total_definitions);
        updateElement('dash-audits-runs', data.audits.total_runs);

        // 3. Insights
        updateElement('dash-insights-total', data.insights.total);

        // 4. Schedules
        updateElement('dash-schedules-total', data.schedules.total);
        updateElement('dash-schedules-active', data.schedules.active);
        const lastRun = data.schedules.last_run ? new Date(data.schedules.last_run).toLocaleString() : 'Never';
        updateElement('dash-schedules-last-run', lastRun);

        // 5. Settings
        updateElement('dash-settings-prompts', data.settings.custom_prompts);
        updateElement('dash-settings-yl2', data.settings.yl2_queries);
        updateElement('dash-settings-audits', data.settings.configurable_audits);

        // 6. Recent Reports
        renderRecentReports(data.recent_reports);

    } catch (error) {
        console.error('Error loading dashboard:', error);
        showToast('Failed to load dashboard data.', 'error');
    }
}

function updateElement(id, value) {
    const el = document.getElementById(id);
    if (el) el.textContent = value;
}

function renderRecentReports(reports) {
    const listContainer = document.getElementById('dash-recent-reports-list');
    if (!listContainer) return;

    listContainer.innerHTML = ''; // Clear loading state

    if (reports.length === 0) {
        listContainer.innerHTML = '<li class="py-3 sm:py-4 text-sm text-gray-500 dark:text-gray-400">No reports generated yet.</li>';
        return;
    }

    reports.forEach(report => {
        const li = document.createElement('li');
        li.className = 'py-3 sm:py-4';
        li.innerHTML = `
            <div class="flex items-center space-x-4">
                <div class="flex-shrink-0">
                    <svg class="w-6 h-6 text-blue-600 dark:text-blue-400" aria-hidden="true" xmlns="http://www.w3.org/2000/svg" fill="currentColor" viewBox="0 0 20 20">
                        <path d="M19 4h-1V2a1 1 0 0 0-1-1H3a1 1 0 0 0-1 1v2H1a1 1 0 0 0-1 1v14a1 1 0 0 0 1 1h18a1 1 0 0 0 1-1V5a1 1 0 0 0-1-1ZM3 3h14v1H3V3Zm15 15H2V6h16v12Z"/>
                    </svg>
                </div>
                <div class="flex-1 min-w-0">
                    <p class="text-sm font-medium text-gray-900 truncate dark:text-white">
                        ${report.report_name}
                    </p>
                    <p class="text-sm text-gray-500 truncate dark:text-gray-400">
                        ${report.project_name}
                    </p>
                </div>
                <div class="inline-flex items-center text-base font-semibold text-gray-900 dark:text-white">
                    ${new Date(report.generation_timestamp).toLocaleDateString()}
                </div>
                <div>
                     <button onclick="viewReport(${report.id})" class="text-blue-600 hover:underline text-sm">View</button>
                </div>
            </div>
        `;
        listContainer.appendChild(li);
    });
}