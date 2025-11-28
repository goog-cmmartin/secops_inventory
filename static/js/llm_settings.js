// --- Global Variables ---
let llmSettingsData = {};
// The llmEditModal is now initialized globally in index.html

// --- Event Listener for Filter ---
document.addEventListener('DOMContentLoaded', () => {
    const filterInput = document.getElementById('llm-audit-filter-input');
    if (filterInput) {
        filterInput.addEventListener('input', renderLlmSettingsTable);
    }
});

// --- Main Population Function ---
async function populateLlmSettings() {
    console.log("--- Populating LLM settings ---");
    const spinner = document.getElementById('llm-settings-spinner');
    if (!spinner) {
        console.warn('LLM settings spinner not found. Tab may not be visible yet.');
        return; 
    }
    spinner.classList.remove('hidden');

    try {
        const [auditsResponse, promptsResponse] = await Promise.all([
            fetch('/api/audits'),
            fetch('/api/prompts')
        ]);

        if (!auditsResponse.ok) throw new Error('Failed to fetch available audits.');
        if (!promptsResponse.ok) throw new Error('Failed to fetch prompts.');

        const availableAudits = await auditsResponse.json();
        const prompts = await promptsResponse.json();

        llmSettingsData = Object.keys(availableAudits).map(auditName => {
            const audit = availableAudits[auditName];
            const promptInfo = prompts[auditName] || { prompt_text: '', excluded_fields: '' };
            return {
                name: auditName,
                category: audit.category,
                icon: audit.audit_type_icon,
                prompt: promptInfo.prompt_text,
                excludedFields: promptInfo.excluded_fields
            };
        });

        renderLlmSettingsTable();

    } catch (error) {
        console.error("Error populating LLM settings:", error);
        showToast(error.message, 'error');
    } finally {
        if (spinner) {
            spinner.classList.add('hidden');
        }
    }
}

// --- Render Table ---
function renderLlmSettingsTable() {
    const tbody = document.getElementById('llm-settings-tbody');
    const filterInput = document.getElementById('llm-audit-filter-input');
    if (!tbody || !filterInput) return;

    const filterText = filterInput.value.toLowerCase();
    tbody.innerHTML = '';

    const filteredData = llmSettingsData.filter(audit => 
        audit.name.toLowerCase().includes(filterText)
    );

    if (filteredData.length === 0) {
        tbody.innerHTML = `<tr><td colspan="5" class="text-center py-4">No audits found matching your filter.</td></tr>`;
        return;
    }

    filteredData.forEach(audit => {
        const excludedFieldsCount = audit.excludedFields ? audit.excludedFields.split(',').filter(Boolean).length : 0;
        const hasPrompt = audit.prompt && audit.prompt.trim() !== '';

        const row = `
            <tr class="bg-white border-b dark:bg-gray-800 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-600">
                <th scope="row" class="px-6 py-4 font-medium text-gray-900 whitespace-nowrap dark:text-white">
                    <div class="flex items-center">
                        <img src="/static/icons/${audit.icon}.svg" class="h-5 w-5 mr-2" alt="${audit.icon} icon">
                        ${audit.name}
                    </div>
                </th>
                <td class="px-6 py-4">${audit.category}</td>
                <td class="px-6 py-4">
                    <span class="text-2xl ${hasPrompt ? 'text-green-500' : 'text-gray-400'}">
                        ${hasPrompt ? '✓' : '✗'}
                    </span>
                </td>
                <td class="px-6 py-4">${excludedFieldsCount}</td>
                <td class="px-6 py-4">
                    <button type="button" class="font-medium text-blue-600 dark:text-blue-500 hover:underline" onclick="openLlmEditModal('${audit.name}')">Edit</button>
                </td>
            </tr>
        `;
        tbody.insertAdjacentHTML('beforeend', row);
    });
}

// --- Modal Management ---
function openLlmEditModal(auditName) {
    const auditData = llmSettingsData.find(a => a.name === auditName);
    if (!auditData) {
        showToast(`Could not find data for audit: ${auditName}`, 'error');
        return;
    }

    document.getElementById('llm-edit-modal-title').textContent = `Edit LLM Settings for ${auditName}`;
    document.getElementById('llm-edit-audit-name').value = auditName;
    document.getElementById('llm-edit-prompt').value = auditData.prompt;
    document.getElementById('llm-edit-excluded-fields').value = auditData.excludedFields;
    
    llmEditModal.show();
}

function saveLlmSettingFromModal() {
    const auditName = document.getElementById('llm-edit-audit-name').value;
    const newPrompt = document.getElementById('llm-edit-prompt').value;
    const newExcludedFields = document.getElementById('llm-edit-excluded-fields').value;

    const auditData = llmSettingsData.find(a => a.name === auditName);
    if (auditData) {
        auditData.prompt = newPrompt;
        auditData.excludedFields = newExcludedFields;
    }

    llmEditModal.hide();
    renderLlmSettingsTable(); // Re-render the table to show the changes
    showToast(`Updated settings for ${auditName}. Click "Save All Changes" to persist.`, 'info');
}


// --- Save All Data ---
async function saveLlmSettings() {
    const saveButton = document.querySelector('#llm-settings button[onclick="saveLlmSettings()"]');
    const originalButtonText = saveButton.innerHTML;
    saveButton.disabled = true;
    saveButton.innerHTML = 'Saving...';

    const promptsToUpdate = {};
    const excludedFieldsToUpdate = {};

    llmSettingsData.forEach(audit => {
        promptsToUpdate[audit.name] = audit.prompt;
        excludedFieldsToUpdate[audit.name] = audit.excludedFields;
    });

    try {
        const response = await fetch('/api/prompts', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                prompts: promptsToUpdate,
                excluded_fields: excludedFieldsToUpdate
            })
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Failed to save settings.');
        }

        showToast('LLM settings saved successfully!', 'success');
        await populateLlmSettings(); // Refresh data from the server

    } catch (error) {
        console.error('Error saving LLM settings:', error);
        showToast(error.message, 'error');
    } finally {
        saveButton.disabled = false;
        saveButton.innerHTML = originalButtonText;
    }
}