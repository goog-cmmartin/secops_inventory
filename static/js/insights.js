let insightsData = []; // Store fetched insights

document.addEventListener("DOMContentLoaded", () => {
  const createInsightBtn = document.getElementById("create-insight-btn");
  const insightModalEl = document.getElementById("insight-modal");
  const insightForm = document.getElementById("insight-form");
  const insightModalTitle = document.getElementById("insight-modal-title");
  const insightIdInput = document.getElementById("insight-id");
  const insightTitleInput = document.getElementById("insight-title");
  const insightPromptTextarea = document.getElementById("insight-prompt");
  const insightExcludedFieldsTextarea = document.getElementById("insight-excluded-fields");
  const insightsTableBody = document.getElementById("insights-table-body");
  const insightFilterInput = document.getElementById("insight-filter-input");

  createInsightBtn.addEventListener("click", () => openInsightModal());
  insightFilterInput.addEventListener("input", applyInsightFilter);

  // Initialize TomSelect for the audit sources dropdown in the modal
  insightAuditSelect = new TomSelect("#insight-audits", {
    create: false,
    sortField: { field: "text", direction: "asc" },
  });

  // --- Tab Click Listener ---
  document.getElementById('insights-tab').addEventListener('click', () => {
    fetchInsights();
    // Set the tenant dropdown to the active tenant if one is selected
    if (window.activeTenant && window.activeTenant.project_id) {
      const insightTenantSelect = document.getElementById('insight-tenant-select');
      insightTenantSelect.value = window.activeTenant.project_id;
    }
  });

  async function fetchInsights() {
    try {
      const response = await fetch("/api/insights");
      if (!response.ok) throw new Error("Failed to fetch insights.");
      insightsData = await response.json(); // Store data globally
      renderInsightsTable(insightsData);
    } catch (error) {
      showToast(error.message, "error");
    }
  }

  function renderInsightsTable(insights) {
    insightsTableBody.innerHTML = "";
    if (insights.length === 0) {
      insightsTableBody.innerHTML = `<tr><td colspan="3" class="text-center p-4">No insights found. Create one to get started.</td></tr>`;
      return;
    }

    insights.forEach((insight) => {
      const row = document.createElement("tr");
      row.className = "bg-white border-b dark:bg-gray-800 dark:border-gray-700";
      row.innerHTML = `
        <td class="px-6 py-4 font-medium text-gray-900 dark:text-white">${insight.title}</td>
        <td class="px-6 py-4 text-sm text-gray-500 dark:text-gray-400">${insight.audit_sources.join(', ')}</td>
        <td class="px-6 py-4 space-x-2 whitespace-nowrap">
          <button class="font-medium text-green-600 hover:underline" onclick="runInsightFromTable(${insight.id}, this)">Run</button>
          <button class="font-medium text-blue-600 hover:underline" onclick="openInsightModal(${insight.id})">Edit</button>
          <button class="font-medium text-red-600 hover:underline" onclick="deleteInsight(${insight.id})">Delete</button>
        </td>
      `;
      insightsTableBody.appendChild(row);
    });
    applyInsightFilter();
  }
  
  function applyInsightFilter() {
    const filterText = insightFilterInput.value.toLowerCase();
    document.querySelectorAll("#insights-table-body tr").forEach((row) => {
      const titleCell = row.querySelector("td:first-child");
      if (titleCell) {
        const title = titleCell.textContent.toLowerCase();
        if (title.includes(filterText)) {
          row.style.display = "";
        } else {
          row.style.display = "none";
        }
      }
    });
  }

  window.openInsightModal = function (insightOrId = null) {
    let insight = null;
    if (typeof insightOrId === 'number') {
        insight = insightsData.find(i => i.id === insightOrId);
    } else if (typeof insightOrId === 'object' && insightOrId !== null) {
        insight = insightOrId;
    }

    insightForm.reset();
    insightIdInput.value = "";
    insightAuditSelect.clear();
    insightAuditSelect.clearOptions();

    const auditOptions = Object.keys(availableAudits).map((name) => ({
      value: name,
      text: name,
    }));
    insightAuditSelect.addOptions(auditOptions);

    if (insight) {
      insightModalTitle.textContent = "Edit Insight";
      insightIdInput.value = insight.id;
      insightTitleInput.value = insight.title;
      insightPromptTextarea.value = insight.prompt;
      insightExcludedFieldsTextarea.value = insight.excluded_fields || "";
      insightAuditSelect.setValue(insight.audit_sources);
    } else {
      insightModalTitle.textContent = "Create Insight";
    }
    insightModal.show();
  };

  window.saveInsight = async function () {
    const insightId = insightIdInput.value;
    const data = {
      title: insightTitleInput.value,
      prompt: insightPromptTextarea.value,
      audit_sources: insightAuditSelect.getValue(),
      excluded_fields: insightExcludedFieldsTextarea.value,
    };

    const url = insightId ? `/api/insights/${insightId}` : "/api/insights";
    const method = insightId ? "PUT" : "POST";

    try {
      const response = await fetch(url, {
        method: method,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data),
      });
      const result = await response.json();
      if (!response.ok) {
        throw new Error(result.detail || "Failed to save insight.");
      }
      showToast("Insight saved successfully!", "success");
      insightModal.hide();
      fetchInsights();
    } catch (error) {
      showToast(error.message, "error");
    }
  };

  window.deleteInsight = async function (insightId) {
    if (!confirm("Are you sure you want to delete this insight?")) return;

    try {
      const response = await fetch(`/api/insights/${insightId}`, {
        method: "DELETE",
      });
      if (!response.ok) {
        const err = await response.json();
        throw new Error(err.detail || "Failed to delete insight.");
      }
      showToast("Insight deleted successfully.", "success");
      fetchInsights();
    } catch (error) {
      showToast(error.message, "error");
    }
  };

  window.runInsightFromTable = async function (insightId, button) {
    const projectId = document.getElementById("insight-tenant-select").value;
    if (!projectId || projectId.startsWith("Choose")) {
      showToast("Please select a tenant to run the insight against.", "warning");
      return;
    }

    const originalButtonText = button.innerHTML;
    button.disabled = true;
    button.innerHTML = "Running...";

    try {
      const response = await fetch(
        `/api/tenants/${projectId}/insights/${insightId}/run`,
        { method: "POST" }
      );
      const result = await response.json();
      if (!response.ok) {
        throw new Error(result.detail || "Failed to start insight run.");
      }
      showToast("Insight generation started...", "info");
      pollReportStatus(result.task_id, button, originalButtonText);
    } catch (error) {
      showToast(error.message, "error");
      button.disabled = false;
      button.innerHTML = originalButtonText;
    }
  };
});
