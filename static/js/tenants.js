// --- Global variable to store the active tenant ---
window.activeTenant = null;

// --- Function to update the active tenant chip in the header ---
window.updateActiveTenantChip = function(tenant) {
  const chip = document.getElementById('active-tenant-chip');
  const chipText = document.getElementById('active-tenant-chip-text');

  if (tenant && tenant.project_id) {
    window.activeTenant = tenant;
    chipText.textContent = `${tenant.project_name} (${tenant.project_id})`;
    chip.classList.remove('hidden');
    chip.classList.add('inline-flex');
  } else {
    window.activeTenant = null;
    chip.classList.add('hidden');
    chip.classList.remove('inline-flex');
  }
}

document.addEventListener("DOMContentLoaded", () => {
  // ... (rest of the file)
});
// --- Active Tenant Management ---

function getActiveTenant() {
    return localStorage.getItem('activeTenantId');
}

function setActiveTenant(projectId) {
    localStorage.setItem('activeTenantId', projectId);
    updateAllTenantDropdowns(projectId);
    fetchTenants(); // Re-render the tenants table to show the new "Active" badge
    if (typeof renderSuggestionChips === 'function') {
        renderSuggestionChips();
    }
    showToast(`Tenant ${projectId} is now the active tenant.`, "info");
}



// --- Event Listeners for Tenant Filters ---
document.getElementById("tenant-filter-input").addEventListener("input", applyTenantFilter);
document.getElementById("show-configured-only-checkbox").addEventListener("change", applyTenantFilter);

function applyTenantFilter() {
  const filterText = document.getElementById("tenant-filter-input").value.toLowerCase();
  const showConfiguredOnly = document.getElementById("show-configured-only-checkbox").checked;
  
  // Use the global tenantData variable for filtering
  const filteredTenants = tenantData.filter(tenant => {
    const nameMatch = tenant.project_name.toLowerCase().includes(filterText);
    const idMatch = tenant.project_id.toLowerCase().includes(filterText);
    const textMatch = nameMatch || idMatch;

    if (showConfiguredOnly) {
      const isConfigured = tenant.api_status.chronicle === 'Success' || 
                           tenant.api_status.soar === 'Success' || 
                           tenant.api_status.bindplane === 'Success';
      return textMatch && isConfigured;
    }
    
    return textMatch;
  });

  renderTenantsTable(filteredTenants);
}

function updateAllTenantDropdowns(projectId) {
    const dropdowns = [
        document.getElementById('tenant-select'),
        document.getElementById('audit-tenant-select'),
        document.getElementById('insight-tenant-select'),
        document.getElementById('report-tenant-filter'),
        document.getElementById('llm-tenant-select')
    ];
    dropdowns.forEach(dropdown => {
        if (dropdown) {
            if (projectId) {
                dropdown.value = projectId;
            } else {
                dropdown.selectedIndex = 0; // Reset to the "Choose a tenant..." option
            }
            // Manually trigger a change event where necessary
            if (dropdown.id === 'audit-tenant-select') {
                dropdown.dispatchEvent(new Event('change'));
            }
        }
    });
}


function renderTenantsTable(tenants) {
  const tenantsTable = document.getElementById("tenants-table");
  tenantsTable.innerHTML = ""; // Clear existing rows
  const activeTenantId = getActiveTenant();

  tenants.forEach((tenant) => {
    let actionButton;
    const hasWorkingApi = (tenant.api_status.chronicle === 'Success' || tenant.api_status.soar === 'Success' || tenant.api_status.bindplane === 'Success');

    if (tenant.project_id === activeTenantId) {
      actionButton = `<span class="bg-green-100 text-green-800 text-xs font-medium me-2 px-2.5 py-0.5 rounded dark:bg-green-900 dark:text-green-300">Active</span>`;
    } else if (hasWorkingApi) {
      actionButton = `<button type="button" class="font-medium text-blue-600 dark:text-blue-500 hover:underline" onclick="setActiveTenant('${tenant.project_id}')">Set Active</button>`;
    } else {
      actionButton = `<span class="font-medium text-gray-400 dark:text-gray-500 cursor-not-allowed" title="Requires at least one working API to set as active.">Set Active</span>`;
    }

    const status_colors = {
      "Success": "green",
      "Failed": "red",
      "Not Configured": "gray"
    };

    const chronicle_status = tenant.api_status.chronicle;
    const soar_status = tenant.api_status.soar;
    const bindplane_status = tenant.api_status.bindplane;

    const row = `
    <tr class="bg-white border-b dark:bg-gray-800 dark:border-gray-700">
      <th scope="row" class="px-6 py-4 font-medium text-gray-900 whitespace-nowrap dark:text-white">${tenant.project_name}</th>
      <td class="px-6 py-4">${tenant.project_id}</td>
      <td class="px-6 py-4">
        <div class="flex items-center space-x-2">
          <span class="h-3 w-3 rounded-full bg-${status_colors[chronicle_status]}-500" title="Chronicle: ${chronicle_status}"></span>
          <span class="h-3 w-3 rounded-full bg-${status_colors[soar_status]}-500" title="SOAR: ${soar_status}"></span>
          <span class="h-3 w-3 rounded-full bg-${status_colors[bindplane_status]}-500" title="BindPlane: ${bindplane_status}"></span>
        </div>
      </td>
      <td class="px-6 py-4 space-x-4">
        <button type="button" class="font-medium text-blue-600 dark:text-blue-500 hover:underline" onclick="openConfigModal('${tenant.project_id}')">Configure</button>
        ${actionButton}
      </td>
    </tr>`;
    tenantsTable.insertAdjacentHTML("beforeend", row);
  });
}

// --- Tenant Management ---
async function fetchTenants() {
  console.log("--- fetchTenants started ---");
  const tenantSelect = document.getElementById("tenant-select");
  const auditTenantSelect = document.getElementById("audit-tenant-select");
  const insightTenantSelect = document.getElementById("insight-tenant-select");
  const reportTenantFilter = document.getElementById("report-tenant-filter");
  const dbStatus = document.getElementById("db-status");

  try {
    const response = await fetch("/api/tenants");
    if (response.status === 412) {
      setupWizardModal.show();
      document.getElementById("myTab").classList.add("hidden");
      document.getElementById("myTabContent").classList.add("hidden");
      return;
    }
    if (!response.ok) throw new Error("Failed to fetch tenants");
    const tenants = await response.json();
    tenantData = tenants; // Store globally
    applyTenantFilter(); // Apply filters after data is loaded

    if (tenantData.length > 0) {
      dbStatus.classList.add('hidden');
    } else {
      dbStatus.innerHTML = `<span class="font-medium">Database is empty.</span> No tenants found. Consider running the setup wizard.`;
      dbStatus.classList.remove('hidden');
    }

    // Populate dropdowns
    [tenantSelect, auditTenantSelect, insightTenantSelect, reportTenantFilter].forEach(sel => {
      if (sel) sel.innerHTML = "";
    });
    tenantSelect.innerHTML = "<option selected>Choose a tenant</option>";
    auditTenantSelect.innerHTML = "<option selected>Choose a tenant</option>";
    insightTenantSelect.innerHTML = "<option selected>Choose a tenant to run against...</option>";
    reportTenantFilter.innerHTML = '<option value="">All Tenants</option>';

    tenants.forEach(tenant => {
      const option = `<option value="${tenant.project_id}">${tenant.project_name} (${tenant.project_id})</option>`;
      
      if (tenant.is_configured) {
        reportTenantFilter.insertAdjacentHTML("beforeend", option);
        tenantSelect.insertAdjacentHTML("beforeend", option);
        auditTenantSelect.insertAdjacentHTML("beforeend", option);
        insightTenantSelect.insertAdjacentHTML("beforeend", option);
      }
    });

    auditTenantSelect.addEventListener('change', populateAudits);
    updateAllTenantDropdowns(getActiveTenant());
    
    // Initial render and filter application
    applyTenantFilter();
    fetchReports();

  } catch (error) {
    if (error.response && error.response.status !== 412) {
      dbStatus.textContent = "Error: " + error.message;
      dbStatus.className = "mb-4 p-4 text-sm text-red-800 rounded-lg bg-red-50 dark:bg-red-900 dark:text-red-200";
    }
  }
}

async function openConfigModal(projectId) {
  document.getElementById("config-project-id").value = projectId;
  try {
    const response = await fetch(`/api/tenants/${projectId}`);
    if (!response.ok) throw new Error("Could not fetch tenant details.");
    const config = await response.json();
    document.getElementById("config-name").value = config.name;
    document.getElementById("config-customer-id").value = config.secops_customer_id;
    document.getElementById("config-region").value = config.secops_region;
    document.getElementById("config-soar-url").value = config.soar_url;
    document.getElementById("config-soar-api-key").value = config.soar_api_key;
    document.getElementById("config-bindplane-url").value = config.bindplane_url || "https://app.bindplane.com/"; // Use default if null
    document.getElementById("config-bindplane-api-key").value = config.bindplane_api_key || "";
    configModal.show();
  } catch (error) {
    showToast(error.message, "error");
  }
}

async function saveConfig() {
  const form = document.getElementById("config-form");
  const projectId = document.getElementById("config-project-id").value;
  const formData = new FormData(form);
  const configData = Object.fromEntries(formData.entries());
  try {
    const response = await fetch(`/api/tenants/${projectId}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(configData),
    });
    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || "Failed to save configuration");
    }
    showToast("Configuration saved successfully!", "success");
    configModal.hide();
    fetchTenants();
  } catch (error) {
    showToast(error.message, "error");
  }
}

async function testChronicleConnection() {
  const projectId = document.getElementById("config-project-id").value;
  const button = document.querySelector('#config-form fieldset:nth-of-type(1) button');
  const originalButtonText = button.innerHTML;
  button.disabled = true;
  button.innerHTML = 'Testing...';

  try {
    const response = await fetch(`/api/tenants/${projectId}/test`, { method: "POST" });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || "Test failed");
    showToast(result.message, "success");
  } catch (error) {
    showToast(error.message, "error");
  } finally {
    button.disabled = false;
    button.innerHTML = originalButtonText;
  }
}

async function testSoarConnection() {
  const projectId = document.getElementById("config-project-id").value;
  const soarUrl = document.getElementById("config-soar-url").value;
  const soarApiKey = document.getElementById("config-soar-api-key").value;
  
  if (!soarUrl || !soarApiKey) {
    showToast("Please provide both SOAR URL and API Key.", "warning");
    return;
  }

  const button = document.querySelector('#config-form fieldset:nth-of-type(2) button');
  const originalButtonText = button.innerHTML;
  button.disabled = true;
  button.innerHTML = 'Testing...';

  try {
    const response = await fetch(`/api/tenants/${projectId}/test_soar`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ soar_url: soarUrl, soar_api_key: soarApiKey }),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || "Test failed");
    showToast(result.message, "success");
  } catch (error) {
    showToast(error.message, "error");
  } finally {
    button.disabled = false;
    button.innerHTML = originalButtonText;
  }
}

async function testBindplaneConnection() {
  const projectId = document.getElementById("config-project-id").value;
  const bindplaneUrl = document.getElementById("config-bindplane-url").value;
  const bindplaneApiKey = document.getElementById("config-bindplane-api-key").value;

  if (!bindplaneUrl || !bindplaneApiKey) {
    showToast("Please provide both BindPlane URL and API Key.", "warning");
    return;
  }

  const button = document.querySelector('#config-form fieldset:nth-of-type(3) button');
  const originalButtonText = button.innerHTML;
  button.disabled = true;
  button.innerHTML = 'Testing...';

  try {
    const response = await fetch(`/api/tenants/${projectId}/test_bindplane`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ bindplane_url: bindplaneUrl, bindplane_api_key: bindplaneApiKey }),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || "Test failed");
    showToast(result.message, "success");
  } catch (error) {
    showToast(error.message, "error");
  } finally {
    button.disabled = false;
    button.innerHTML = originalButtonText;
  }
}
