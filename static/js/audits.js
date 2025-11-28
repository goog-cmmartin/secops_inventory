let currentSort = {
    column: 'last_run',
    direction: 'desc'
};

function sortAndRenderAudits() {
    // Create a map that includes the name, then sort it.
    const auditList = Object.entries(availableAudits).map(([name, details]) => ({ name, ...details }));

    auditList.sort((a, b) => {
        // Map the friendly sort key from the data-sort attribute to the actual data property key
        const sortKey = currentSort.column === 'last_run' ? 'last_successful_run' : currentSort.column;

        const valA = a[sortKey];
        const valB = b[sortKey];

        let comparison = 0;
        if (sortKey === 'last_successful_run') {
            const dateA = valA ? new Date(valA) : null;
            const dateB = valB ? new Date(valB) : null;
            if (dateA === null && dateB === null) comparison = 0;
            else if (dateA === null) comparison = 1; // Nulls go to the bottom
            else if (dateB === null) comparison = -1;
            else comparison = dateA.getTime() - dateB.getTime();
        } else { // Default to locale-aware string comparison for name and category
            comparison = (valA || '').toString().localeCompare((valB || '').toString());
        }

        return currentSort.direction === 'asc' ? comparison : -comparison;
    });

    renderAuditsTable(auditList);
    updateSortIndicators();
}

function renderAuditsTable(auditList) {
    const tableBody = document.getElementById("audit-selection-tbody");
    tableBody.innerHTML = ""; // Clear previous audits

    for (const audit of auditList) {
        let isDisabled = false;
        let tooltipText = '';
        // ... (rest of your isDisabled logic remains the same)

        const disabledAttr = isDisabled ? 'disabled' : '';
        const labelClass = isDisabled ? 'text-gray-400 dark:text-gray-500' : 'text-gray-900 dark:text-gray-300';
        const titleAttr = isDisabled ? `title="${tooltipText}"` : '';
        const cursorClass = isDisabled ? 'cursor-not-allowed' : '';
        const iconOpacity = isDisabled ? 'opacity-50' : '';
        const compareButtonDisabled = audit.successful_run_count < 2 ? 'disabled' : '';

        const lastRunTimestamp = audit.last_successful_run 
          ? new Date(audit.last_successful_run).toLocaleString()
          : 'N/A';

        let auditNameContent;
        if (audit.latest_run_id && !isDisabled) {
          auditNameContent = `<button type="button" class="text-sm font-medium text-blue-600 dark:text-blue-500 hover:underline" onclick="viewLastAuditRun('${audit.name}')">${audit.name}</button>`;
        } else {
          auditNameContent = `<label for="checkbox-${audit.name}" class="text-sm font-medium ${labelClass} ${cursorClass}">${audit.name}</label>`;
        }

        const row = document.createElement('tr');
        row.className = 'bg-white border-b dark:bg-gray-800 dark:border-gray-700';
        row.innerHTML = `
            <td class="p-4">
                <input id="checkbox-${audit.name}" type="checkbox" value="${audit.name}" class="w-4 h-4 text-blue-600 bg-gray-100 border-gray-300 rounded" ${disabledAttr}>
            </td>
            <td class="px-6 py-4 font-medium text-gray-900 dark:text-white">
                <div class="flex items-center">
                    <img src="/static/icons/${audit.audit_type_icon}.svg" class="h-5 w-5 mr-2 text-gray-500 dark:text-gray-400 ${iconOpacity}">
                    ${auditNameContent}
                </div>
            </td>
            <td class="px-6 py-4">${audit.category}</td>
            <td class="px-6 py-4 text-sm text-gray-500 dark:text-gray-400">${lastRunTimestamp}</td>
            <td class="px-6 py-4">${audit.item_count !== null && audit.item_count !== undefined ? audit.item_count : 'N/A'}</td>
            <td class="px-6 py-4">${audit.size_bytes !== null && audit.size_bytes !== undefined ? (audit.size_bytes / 1024).toFixed(2) + ' KB' : 'N/A'}</td>
            <td class="px-6 py-4">
                <button type="button" class="text-sm font-medium text-purple-600 dark:text-purple-500 hover:underline" onclick="openCompareRunsModal('${audit.name}')" ${compareButtonDisabled}>Compare Runs</button>
            </td>
        `;
        tableBody.appendChild(row);
    }
    applyAuditFilter(); // Re-apply the filter after populating
}

function updateSortIndicators() {
    document.querySelectorAll('#audit-selection-table th button').forEach(button => {
        const indicator = button.querySelector('.sort-indicator');
        const sortKey = button.dataset.sort;
        if (sortKey === currentSort.column) {
            indicator.innerHTML = currentSort.direction === 'asc' ? '&#9650;' : '&#9660;'; // Up or down arrow
        } else {
            indicator.innerHTML = '';
        }
    });
}

document.querySelectorAll('#audit-selection-table th button').forEach(button => {
    button.addEventListener('click', () => {
        const sortKey = button.dataset.sort;
        if (currentSort.column === sortKey) {
            currentSort.direction = currentSort.direction === 'asc' ? 'desc' : 'asc';
        } else {
            currentSort.column = sortKey;
            currentSort.direction = 'asc';
        }
        sortAndRenderAudits();
    });
});

async function populateAudits() {
  const projectId = auditTenantSelect.value;
  const tableBody = document.getElementById("audit-selection-tbody");
  const spinner = document.getElementById("audit-list-spinner");

  spinner.classList.remove("hidden");
  tableBody.innerHTML = ""; // Clear previous audits

  if (!projectId || projectId === "Choose a tenant") {
    spinner.classList.add("hidden");
    window.updateActiveTenantChip(null); // Clear the active tenant chip
    return;
  }

  const selectedTenant = tenantData.find(t => t.project_id === projectId);
  window.updateActiveTenantChip(selectedTenant); // Update the active tenant chip
  const apiStatus = selectedTenant ? selectedTenant.api_status : null;

  try {
    const response = await fetch(`/api/tenants/${projectId}/audits/status`);
    if (!response.ok) throw new Error("Failed to fetch audits for tenant");
    const audits = await response.json();
    availableAudits = audits;
    sortAndRenderAudits(); // Initial sort and render
  } catch (error) {
    showToast(error.message, "error");
  } finally {
    spinner.classList.add("hidden");
  }
}

async function viewLastAuditRun(auditName) {
  const projectId = auditTenantSelect.value;
  if (!projectId || projectId === "Choose a tenant") {
    showToast("Please select a tenant first.", "warning");
    return;
  }

  try {
    const response = await fetch(`/api/tenants/${projectId}/audits/${auditName}/view`);
    if (!response.ok) {
      const err = await response.json();
      throw new Error(err.detail || "Could not fetch last audit run.");
    }
    const data = await response.json();
    
    const sizeKb = (data.size_bytes / 1024).toFixed(2);
    const tokenString = data.token_count ? `, ~${data.token_count} tokens` : '';
    document.getElementById("json-modal-title").textContent = `${auditName} (Last Run: ${data.item_count} items, ${sizeKb} KB${tokenString})`;
    document.getElementById("json-modal-content").querySelector('code').textContent = JSON.stringify(data.results, null, 2);
    jsonViewerModal.show();

  } catch (error) {
    showToast(error.message, "error");
  }
}

async function fetchConfigurableAudits() {
    const showAllFields = document.getElementById('show-all-fields-radio').checked;
    const tableBody = document.getElementById("configurable-audits-table");
    const tableHead = document.getElementById("configurable-audits-thead");

    try {
        const response = await fetch("/api/configurable_audits");
        if (!response.ok)
        throw new Error("Failed to fetch configurable audits");
        const audits = await response.json();
        
        // Clear existing content
        tableHead.innerHTML = '';
        tableBody.innerHTML = "";

        // Define headers based on the view
        let headers = ['Name', 'Category', 'Type', 'Actions'];
        if (showAllFields) {
            headers = ['Name', 'Category', 'Type', 'API Path', 'Method', 'Response Key', 'Page Size', 'Response Format', 'Actions'];
        }
        
        // Populate headers
        const headerRow = `<tr>${headers.map(h => `<th scope="col" class="px-6 py-3">${h}</th>`).join('')}</tr>`;
        tableHead.innerHTML = headerRow;

        // Populate table body
        audits.forEach((audit) => {
            const row = document.createElement('tr');
            row.className = 'bg-white border-b dark:bg-gray-800 dark:border-gray-700';

            let rowContent = `
                <td class="px-6 py-4 font-medium">${audit.name}</td>
                <td class="px-6 py-4">${audit.category}</td>
                <td class="px-6 py-4 flex items-center">
                    <img src="/static/icons/${audit.audit_type_icon}.svg" class="h-5 w-5 mr-2 text-gray-500">
                    ${audit.audit_type_name}
                </td>
            `;

            if (showAllFields) {
                rowContent += `
                    <td class="px-6 py-4 font-mono text-xs">${audit.api_path || 'N/A'}</td>
                    <td class="px-6 py-4">${audit.method || 'N/A'}</td>
                    <td class="px-6 py-4">${audit.response_key || 'N/A'}</td>
                    <td class="px-6 py-4">${audit.default_page_size || 'N/A'}</td>
                    <td class="px-6 py-4">${audit.response_format || 'JSON'}</td>
                `;
            }

            rowContent += `
                <td class="px-6 py-4 space-x-2">
                    <button class="font-medium text-blue-600 hover:underline" onclick='openConfigurableAuditModal(${JSON.stringify(audit)})'>Edit</button>
                    <button class="font-medium text-red-600 hover:underline" onclick="deleteConfigurableAudit(${audit.id})">Delete</button>
                </td>
            `;
            
            row.innerHTML = rowContent;
            tableBody.appendChild(row);
        });
        
        // Re-apply the filter after the table is repopulated
        applyConfigurableAuditFilter();
    } catch (error) {
        showToast(error.message, "error");
    }
}

// Add event listener for the new checkbox
document.getElementById('show-all-fields-radio').addEventListener('change', fetchConfigurableAudits);

async function runSelectedAudits() {
  const projectId = auditTenantSelect.value;
  if (!projectId || projectId === "Choose a tenant") {
    showToast("Please select a tenant first.", "warning");
    return;
  }
  const selectedAudits = Array.from(
    document.querySelectorAll('#audit-selection-tbody input[type="checkbox"]:checked')
  ).map((cb) => cb.value);

  if (selectedAudits.length === 0) {
    showToast("Please select at least one audit to run.", "warning");
    return;
  }

  const runButton = document.getElementById('run-audits-btn');
  const originalButtonText = runButton.innerHTML;
  runButton.disabled = true;
  runButton.innerHTML = `<svg aria-hidden="true" class="inline w-4 h-4 mr-2 text-gray-200 animate-spin dark:text-gray-600 fill-blue-600" viewBox="0 0 100 101" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M100 50.5908C100 78.2051 77.6142 100.591 50 100.591C22.3858 100.591 0 78.2051 0 50.5908C0 22.9766 22.3858 0.59082 50 0.59082C77.6142 0.59082 100 22.9766 100 50.5908ZM9.08144 50.5908C9.08144 73.1895 27.4013 91.5094 50 91.5094C72.5987 91.5094 90.9186 73.1895 90.9186 50.5908C90.9186 27.9921 72.5987 9.67226 50 9.67226C27.4013 9.67226 9.08144 27.9921 9.08144 50.5908Z" fill="currentColor"/><path d="M93.9676 39.0409C96.393 38.4038 97.8624 35.9116 97.0079 33.5539C95.2932 28.8227 92.871 24.3692 89.8167 20.348C85.8452 15.1192 80.8826 10.7238 75.2124 7.41289C69.5422 4.10194 63.2754 1.94025 56.7698 1.05124C51.7666 0.367541 46.6976 0.446843 41.7345 1.27873C39.2613 1.69328 37.813 4.19778 38.4501 6.62326C39.0873 9.04874 41.5694 10.4717 44.0505 10.1071C47.8511 9.54855 51.7191 9.52689 55.5402 10.0492C60.8642 10.7766 65.9928 12.5457 70.6331 15.2552C75.2735 17.9648 79.3347 21.5619 82.5849 25.841C84.9175 28.9121 86.7997 32.2913 88.1811 35.8758C89.083 38.2158 91.5421 39.6781 93.9676 39.0409Z" fill="currentFill"/></svg>Running...`;

  try {
    for (const auditName of selectedAudits) {
      try {
        const response = await fetch(
          `/api/tenants/${projectId}/audits/run`,
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ audit_name: auditName }),
          }
        );
        const result = await response.json();
        if (!response.ok) {
          throw new Error(result.detail || `Failed to run audit: ${auditName}`);
        }
        showToast(result.message, "success");
        
      } catch (error) {
        showToast(error.message, "error");
      }
    }
  } finally {
    // Refresh the audit list to show new timestamps
    await populateAudits();
    runButton.disabled = false;
    runButton.innerHTML = originalButtonText;
  }
}

window.openConfigurableAuditModal = async function (audit = null) {
  const form = document.getElementById("configurable-audit-form");
  form.reset();
  document.getElementById("configurable-audit-id").value = "";

  // Fetch and populate audit types
  const typeSelect = document.getElementById("configurable-audit-type");
  typeSelect.innerHTML = "";
  try {
    const response = await fetch("/api/audit_types");
    const types = await response.json();
    types.forEach((type) => {
      const option = new Option(type.name, type.id);
      typeSelect.add(option);
    });
  } catch (error) {
    showToast("Failed to load audit types.", "error");
  }

  // Populate the test tenant dropdown
  const testTenantSelect = document.getElementById(
    "configurable-audit-test-tenant"
  );
  testTenantSelect.innerHTML =
    "<option selected>Select Tenant for Test...</option>";
  tenantData.forEach((tenant) => {
    if (tenant.is_configured) {
      const option = new Option(
        `${tenant.project_name} (${tenant.project_id})`,
        tenant.project_id
      );
      testTenantSelect.add(option);
    }
  });

  if (audit) {
    document.getElementById(
      "configurable-audit-modal-title"
    ).textContent = "Edit Audit";
    document.getElementById("configurable-audit-id").value = audit.id;
    document.getElementById("configurable-audit-name").value =
      audit.name;
    document.getElementById("configurable-audit-category").value =
      audit.category;
    document.getElementById("configurable-audit-type").value =
      audit.audit_type_id;
    document.getElementById("configurable-audit-api-path").value =
      audit.api_path || "";
    document.getElementById("configurable-audit-method").value =
      audit.method || "GET";
    document.getElementById("configurable-audit-response-key").value =
      audit.response_key || "";
    document.getElementById("configurable-audit-page-size").value =
      audit.default_page_size || "";
    document.getElementById("configurable-audit-max-pages").value =
      audit.max_pages || "0";
    document.getElementById("configurable-audit-pagination-token-key").value = 
      audit.pagination_token_key || "";
    document.getElementById("configurable-audit-pagination-results-key").value = 
      audit.pagination_results_key || "";
    document.getElementById("configurable-audit-pagination-request-token-key").value =
      audit.pagination_request_token_key || "";
    document.getElementById(
      "configurable-audit-response-format"
    ).value = audit.response_format || "JSON";
  } else {
    document.getElementById(
      "configurable-audit-modal-title"
    ).textContent = "Create Audit";
  }
  configurableAuditModal.show();
};

async function testConfigurableAudit() {
  const projectId = document.getElementById("configurable-audit-test-tenant").value;
  if (!projectId || projectId.startsWith("Select")) {
    showToast("Please select a tenant to run the test against.", "warning");
    return;
  }

  // Gather audit details from the form
  const auditDetails = {
    name: document.getElementById("configurable-audit-name").value,
    category: document.getElementById("configurable-audit-category").value,
    audit_type_id: parseInt(document.getElementById("configurable-audit-type").value),
    api_path: document.getElementById("configurable-audit-api-path").value,
    method: document.getElementById("configurable-audit-method").value,
    response_key: document.getElementById("configurable-audit-response-key").value,
    default_page_size: parseInt(document.getElementById("configurable-audit-page-size").value) || null,
    response_format: document.getElementById("configurable-audit-response-format").value,
  };

  try {
    const response = await fetch(`/api/tenants/${projectId}/audits/run`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ audit_details: auditDetails })
    });
    const result = await response.json();
    if (!response.ok) {
      throw new Error(result.detail || "Test run failed.");
    }
    showToast(result.message, "success");
    // Optionally, display the result in a modal or preformatted block
    alert(`Test successful:\n\n${JSON.stringify(result, null, 2)}`);
  } catch (error) {
    showToast(error.message, "error");
  }
}

// Event Listener for Audit Filter
document.getElementById("audit-filter-input").addEventListener("input", applyAuditFilter);

function applyAuditFilter() {
  const filterText = document.getElementById("audit-filter-input").value.toLowerCase();
  document.querySelectorAll("#audit-selection-tbody tr").forEach((row) => {
    // Ignore category header rows
    if (row.querySelectorAll('td').length === 1) {
        row.style.display = ""; // Always show category headers
        return;
    }
    const auditNameCell = row.querySelector("td:nth-child(2)");
    if (auditNameCell) {
      const auditName = auditNameCell.textContent.toLowerCase();
      if (auditName.includes(filterText)) {
        row.style.display = "";
      } else {
        row.style.display = "none";
      }
    }
  });
}

// Event Listener for checkbox changes to enable/disable buttons
document.getElementById("audit-selection-tbody").addEventListener("change", updateAuditActionButtonsState);

function updateAuditActionButtonsState() {
    const runButton = document.getElementById('run-audits-btn');
    const reportButton = document.getElementById('generate-report-btn');
    const scheduleButton = document.getElementById('create-schedule-from-audits-btn');
    const checkedBoxes = document.querySelectorAll('#audit-selection-tbody input[type="checkbox"]:checked');
    const areAnyChecked = checkedBoxes.length > 0;

    runButton.disabled = !areAnyChecked;
    reportButton.disabled = !areAnyChecked;
    scheduleButton.disabled = !areAnyChecked;

    [runButton, reportButton, scheduleButton].forEach(button => {
        if (areAnyChecked) {
            button.classList.remove('opacity-50', 'cursor-not-allowed');
        } else {
            button.classList.add('opacity-50', 'cursor-not-allowed');
        }
    });
}

// Event Listener for Select All Audits
document.getElementById("select-all-audits-checkbox").addEventListener("change", (event) => {
  document.querySelectorAll('#audit-selection-tbody input[type="checkbox"]:not(:disabled)').forEach((checkbox) => {
    const row = checkbox.closest('tr');
    if (row.style.display !== 'none') {
      checkbox.checked = event.target.checked;
    }
  });
  updateAuditActionButtonsState(); // Update button states after toggling all
});

function createScheduleFromAudits() {
  const projectId = auditTenantSelect.value;
  if (!projectId || projectId === "Choose a tenant") {
    showToast("Please select a tenant first.", "warning");
    return;
  }

  const selectedAudits = Array.from(
    document.querySelectorAll('#audit-selection-tbody input[type="checkbox"]:checked')
  ).map((cb) => cb.value);

  if (selectedAudits.length === 0) {
    showToast("Please select at least one audit to create a schedule.", "warning");
    return;
  }

  const prefillData = {
    project_id: projectId,
    audit_names: selectedAudits,
  };

  // Switch to the schedules tab before opening the modal
  document.getElementById('schedules-tab').click();

  // Use a short timeout to allow the tab switch animation to complete
  setTimeout(() => {
    if (window.openScheduleModal) {
      window.openScheduleModal(prefillData);
    } else {
      console.error("Schedule modal function not found.");
      showToast("Could not open schedule modal.", "error");
    }
  }, 150);
}

// Make function global for onclick attribute
window.createScheduleFromAudits = createScheduleFromAudits;
window.openCompareRunsModal = async function(auditName) {
  const projectId = auditTenantSelect.value;
  if (!projectId || projectId === "Choose a tenant") {
    showToast("Please select a tenant first.", "warning");
    return;
  }

  document.getElementById("compare-runs-modal-title").textContent = `Compare Runs for: ${auditName}`;
  const listContainer = document.getElementById("compare-runs-list");
  const generateBtn = document.getElementById("generate-diff-report-btn");
  listContainer.innerHTML = '<p>Loading runs...</p>';
  generateBtn.disabled = true;

  try {
    const response = await fetch(`/api/tenants/${projectId}/audits/${auditName}/runs`);
    if (!response.ok) throw new Error("Failed to fetch audit runs.");
    const runs = await response.json();

    if (runs.length < 2) {
      listContainer.innerHTML = '<p>Fewer than two successful runs exist. Cannot compare.</p>';
      return;
    }

    listContainer.innerHTML = runs.map(run => `
      <div class="flex items-center">
        <input id="run-${run.id}" name="audit_run" type="checkbox" value="${run.id}" class="w-4 h-4 text-blue-600 bg-gray-100 border-gray-300 rounded">
        <label for="run-${run.id}" class="ms-2 text-sm font-medium text-gray-900 dark:text-gray-300">
          ${new Date(run.run_timestamp).toLocaleString()}
        </label>
      </div>
    `).join('');

    listContainer.addEventListener('change', () => {
      const selected = listContainer.querySelectorAll('input[type="checkbox"]:checked');
      generateBtn.disabled = selected.length !== 2;
    });

    generateBtn.onclick = () => {
      const selected = Array.from(listContainer.querySelectorAll('input[type="checkbox"]:checked')).map(cb => parseInt(cb.value));
      generateDiffReport(selected[0], selected[1]);
    };

    compareRunsModal.show();

  } catch (error) {
    showToast(error.message, 'error');
    listContainer.innerHTML = `<p class="text-red-500">${error.message}</p>`;
  }
}

async function generateDiffReport(auditId1, auditId2) {
    compareRunsModal.hide();
    const generateBtn = document.getElementById("generate-diff-report-btn");
    const originalButtonText = generateBtn.innerHTML;
    generateBtn.disabled = true;
    generateBtn.innerHTML = 'Generating...';

    showToast("Diff report generation started...", "info");
    
    try {
        const response = await fetch('/api/reports/generate_diff', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ audit_id_1: auditId1, audit_id_2: auditId2 }),
        });
        const result = await response.json();
        if (!response.ok) {
            throw new Error(result.detail || "Failed to start diff report generation.");
        }
        // Pass the button and its original text to the polling function
        pollReportStatus(result.task_id, generateBtn, originalButtonText);
    } catch (error) {
        showToast(error.message, "error");
        generateBtn.disabled = false;
        generateBtn.innerHTML = originalButtonText;
    }
}


window.saveConfigurableAudit = async function() {
  const saveButton = document.querySelector('#configurable-audit-modal button[onclick="saveConfigurableAudit()"]');
  const originalButtonText = saveButton.innerHTML;
  saveButton.disabled = true;
  saveButton.innerHTML = 'Saving...';

  const auditId = document.getElementById("configurable-audit-id").value;
  const data = {
    name: document.getElementById("configurable-audit-name").value,
    category: document.getElementById("configurable-audit-category").value,
    audit_type_id: parseInt(document.getElementById("configurable-audit-type").value),
    api_path: document.getElementById("configurable-audit-api-path").value || null,
    method: document.getElementById("configurable-audit-method").value,
    response_key: document.getElementById("configurable-audit-response-key").value || null,
    default_page_size: parseInt(document.getElementById("configurable-audit-page-size").value) || null,
    max_pages: parseInt(document.getElementById("configurable-audit-max-pages").value) || 0,
    pagination_token_key: document.getElementById("configurable-audit-pagination-token-key").value || null,
    pagination_results_key: document.getElementById("configurable-audit-pagination-results-key").value || null,
    pagination_request_token_key: document.getElementById("configurable-audit-pagination-request-token-key").value || null,
    response_format: document.getElementById("configurable-audit-response-format").value,
  };

  const url = auditId ? `/api/configurable_audits/${auditId}` : "/api/configurable_audits";
  const method = auditId ? "PUT" : "POST";

  try {
    const response = await fetch(url, {
      method: method,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
    if (!response.ok) {
      const err = await response.json();
      throw new Error(err.detail || "Failed to save audit.");
    }
    showToast("Audit saved successfully!", "success");
    configurableAuditModal.hide();
    fetchConfigurableAudits(); // Refresh the list in settings
    populateAudits(); // Refresh the main audit selection view
  } catch (error) {
    showToast(error.message, "error");
  } finally {
    saveButton.disabled = false;
    saveButton.innerHTML = originalButtonText;
  }
}

window.deleteConfigurableAudit = async function(auditId) {
    if (!confirm("Are you sure you want to delete this audit? This cannot be undone.")) return;

    try {
        const response = await fetch(`/api/configurable_audits/${auditId}`, { method: 'DELETE' });
        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.detail || "Failed to delete audit.");
        }
        showToast("Audit deleted successfully.", "success");
        fetchConfigurableAudits(); // Refresh the list
        populateAudits(); // Refresh the main audit selection view
    } catch (error) {
        showToast(error.message, "error");
    }
}

window.testConfigurableAudit = testConfigurableAudit;

window.exportAudits = async function() {
  const confirmation = confirm(
    "This will download the current audit configuration as a JSON file.\n\n" +
    "To make these the new defaults, you must manually replace the 'default_audits.json' file on the server.\n\n" +
    "Do you want to continue?"
  );

  if (!confirmation) {
    return;
  }

  try {
    const response = await fetch('/api/audits/export');
    if (!response.ok) {
      throw new Error('Failed to fetch audit configurations for export.');
    }
    const data = await response.json();
    
    // Trigger file download
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'default_audits.json';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);

    showToast("Audit configuration exported successfully.", "success");

  } catch (error) {
    showToast(error.message, 'error');
  }
}

// Event Listener for Configurable Audit Filter
document.getElementById("configurable-audit-filter-input").addEventListener("input", applyConfigurableAuditFilter);

function applyConfigurableAuditFilter() {
  const filterText = document.getElementById("configurable-audit-filter-input").value.toLowerCase();
  document.querySelectorAll("#configurable-audits-table tr").forEach((row) => {
    const auditNameCell = row.querySelector("td:first-child");
    if (auditNameCell) {
      const auditName = auditNameCell.textContent.toLowerCase();
      if (auditName.includes(filterText)) {
        row.style.display = "";
      } else {
        row.style.display = "none";
      }
    }
  });
}