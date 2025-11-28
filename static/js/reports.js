// --- Reports Tab Functions ---

async function fetchReports() {
  const reportsTable = document.getElementById("reports-table");
  const reportTenantFilter = document.getElementById("report-tenant-filter");
  const tenantFilter = reportTenantFilter.value;
  const url = tenantFilter
    ? `/api/reports?project_id=${tenantFilter}`
    : "/api/reports";

  try {
    const response = await fetch(url);
    if (!response.ok) throw new Error("Failed to fetch reports.");
    const reports = await response.json();

    reportsTable.innerHTML = ""; // Clear existing
    reports.forEach((report) => {
      const row = `
        <tr class="bg-white border-b dark:bg-gray-800 dark:border-gray-700">
          <td class="p-4"><input type="checkbox" class="report-checkbox w-4 h-4" data-id="${report.id}"></td>
          <td class="px-6 py-4 font-medium">${report.report_name}</td>
          <td class="px-6 py-4">${report.project_name}</td>
          <td class="px-6 py-4">${new Date(
            report.generation_timestamp
          ).toLocaleString()}</td>
          <td class="px-6 py-4">
            <button class="font-medium text-blue-600 hover:underline" onclick="viewReport(${report.id})">
            <svg class="w-5 h-5 inline-block" aria-hidden="true" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
            </svg>
          </button>
            <button class="font-medium text-yellow-600 hover:underline ml-2" onclick="renameReport(${report.id}, '${report.report_name}')">Rename</button>
          </td>
        </tr>`;
      reportsTable.insertAdjacentHTML("beforeend", row);
    });
  } catch (error) {
    showToast(error.message, "error");
  }
}

async function viewReport(reportId) {
  try {
    const response = await fetch(`/api/reports/${reportId}`);
    if (!response.ok) throw new Error("Failed to fetch report content.");
    const report = await response.json();

    document.getElementById("report-modal-title").textContent = report.report_name;
    const contentDiv = document.getElementById("report-modal-content");
    // Use DOMPurify to sanitize the HTML before rendering
    contentDiv.innerHTML = DOMPurify.sanitize(marked.parse(report.report_content));

    reportViewerModal.show();
    
    // Deep Linking: Update URL without reloading
    const newUrl = new URL(window.location);
    newUrl.searchParams.set('report_id', reportId);
    window.history.pushState({ report_id: reportId }, '', newUrl);

  } catch (error) {
    showToast(error.message, "error");
  }
}

function closeReportModal() {
    reportViewerModal.hide();
    // Deep Linking: Remove query param
    const newUrl = new URL(window.location);
    newUrl.searchParams.delete('report_id');
    window.history.pushState({}, '', newUrl);
}

window.copyReportLink = function() {
    const url = window.location.href;
    navigator.clipboard.writeText(url).then(() => {
        showToast("Report link copied to clipboard!", "success");
    }).catch(err => {
        console.error('Failed to copy link:', err);
        showToast("Failed to copy link.", "error");
    });
}

async function handleDeepLinking() {
    const urlParams = new URLSearchParams(window.location.search);
    const reportId = urlParams.get('report_id');
    if (reportId) {
        // Ensure the Reports tab logic is loaded/active if needed, or just open the modal
        // For a smoother UX, we might want to switch to the Reports tab behind the modal
        document.getElementById('reports-tab').click(); 
        await viewReport(reportId);
    }
}

// Add this to the initialization block or call it at the end of the file
document.addEventListener('DOMContentLoaded', handleDeepLinking);

async function renameReport(reportId, currentName) {
    const newName = prompt("Enter a new name for the report:", currentName);
    if (newName && newName.trim() !== "") {
        try {
            const response = await fetch(`/api/reports/${reportId}/rename`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ new_name: newName.trim() })
            });
            if (!response.ok) {
                const err = await response.json();
                throw new Error(err.detail || "Failed to rename report.");
            }
            showToast("Report renamed successfully!", "success");
            fetchReports(); // Refresh the list
        } catch (error) {
            showToast(error.message, "error");
        }
    }
}

async function deleteSelectedReports() {
  const selectedIds = Array.from(
    document.querySelectorAll(".report-checkbox:checked")
  ).map((cb) => parseInt(cb.dataset.id));

  if (selectedIds.length === 0) {
    showToast("No reports selected.", "warning");
    return;
  }

  if (confirm(`Are you sure you want to delete ${selectedIds.length} report(s)?`)) {
    try {
      const response = await fetch("/api/reports/delete", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ report_ids: selectedIds }),
      });
      if (!response.ok) throw new Error("Failed to delete reports.");
      showToast("Selected reports deleted.", "success");
      fetchReports(); // Refresh
    } catch (error) {
      showToast(error.message, "error");
    }
  }
}

async function exportSelectedReports() {
    const selectedIds = Array.from(document.querySelectorAll(".report-checkbox:checked"))
        .map(cb => parseInt(cb.dataset.id));

    if (selectedIds.length === 0) {
        showToast("No reports selected for export.", "warning");
        return;
    }

    try {
        const response = await fetch('/api/reports/export', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ report_ids: selectedIds })
        });

        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.detail || "Failed to export reports.");
        }

        // Trigger file download
        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.style.display = 'none';
        a.href = url;
        a.download = 'secops_inventory_reports.md';
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        a.remove();

            showToast("Reports exported successfully.", "success");
          } catch (error) {
            showToast(`Export failed: ${error.message}`, "error");
          }
        }
        
        async function generateReport() {
  const projectId = auditTenantSelect.value;
  if (!projectId || projectId === "Choose a tenant") {
    showToast("Please select a tenant first.", "warning");
    return;
  }
  const selectedAudits = Array.from(
    document.querySelectorAll('#audit-selection-tbody input[type="checkbox"]:checked')
  ).map((cb) => cb.value);
  if (selectedAudits.length === 0) {
    showToast("Please select at least one audit for the report.", "warning");
    return;
  }

  const reportButton = document.getElementById("generate-report-btn");
  const originalButtonText = reportButton.innerHTML;
  reportButton.disabled = true;
  reportButton.innerHTML = `<svg aria-hidden="true" class="inline w-4 h-4 mr-2 text-gray-200 animate-spin dark:text-gray-600 fill-green-500" viewBox="0 0 100 101" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M100 50.5908C100 78.2051 77.6142 100.591 50 100.591C22.3858 100.591 0 78.2051 0 50.5908C0 22.9766 22.3858 0.59082 50 0.59082C77.6142 0.59082 100 22.9766 100 50.5908ZM9.08144 50.5908C9.08144 73.1895 27.4013 91.5094 50 91.5094C72.5987 91.5094 90.9186 73.1895 90.9186 50.5908C90.9186 27.9921 72.5987 9.67226 50 9.67226C27.4013 9.67226 9.08144 27.9921 9.08144 50.5908Z" fill="currentColor"/><path d="M93.9676 39.0409C96.393 38.4038 97.8624 35.9116 97.0079 33.5539C95.2932 28.8227 92.871 24.3692 89.8167 20.348C85.8452 15.1192 80.8826 10.7238 75.2124 7.41289C69.5422 4.10194 63.2754 1.94025 56.7698 1.05124C51.7666 0.367541 46.6976 0.446843 41.7345 1.27873C39.2613 1.69328 37.813 4.19778 38.4501 6.62326C39.0873 9.04874 41.5694 10.4717 44.0505 10.1071C47.8511 9.54855 51.7191 9.52689 55.5402 10.0492C60.8642 10.7766 65.9928 12.5457 70.6331 15.2552C75.2735 17.9648 79.3347 21.5619 82.5849 25.841C84.9175 28.9121 86.7997 32.2913 88.1811 35.8758C89.083 38.2158 91.5421 39.6781 93.9676 39.0409Z" fill="currentFill"/></svg>Generating...`;

  try {
    const response = await fetch(
      `/api/tenants/${projectId}/reports/generate`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ audit_names: selectedAudits }),
      }
    );
    const result = await response.json();
    if (!response.ok) {
      throw new Error(result.detail || "Failed to start report generation.");
    }
    showToast(result.message, "info");
    pollReportStatus(result.task_id, reportButton, originalButtonText); // Pass button to poll function
  } catch (error) {
    showToast(error.message, "error");
    reportButton.disabled = false;
    reportButton.innerHTML = originalButtonText;
  }
}

function pollReportStatus(taskId, button, originalText) {
  const interval = setInterval(async () => {
    try {
      const response = await fetch(`/api/reports/status/${taskId}`);
      const result = await response.json();

      if (result.state === "SUCCESS" || result.state === "FAILURE") {
        clearInterval(interval);
        button.disabled = false;
        button.innerHTML = originalText;
        if (result.state === "SUCCESS") {
          showToast("Report generated successfully!", "success");
          fetchReports();
        } else {
          showToast(`Report generation failed: ${result.status}`, "error");
        }
      }
      // If still pending or in progress, the polling continues silently
    } catch (error) {
      clearInterval(interval);
      button.disabled = false;
      button.innerHTML = originalText;
      showToast("Error checking report status.", "error");
    }
  }, 3000); // Poll every 3 seconds
}
            
// Event Listeners for Reports Tab
document.getElementById("report-tenant-filter").addEventListener("change", fetchReports);

document.getElementById("select-all-reports").addEventListener("change", function (e) {
    document.querySelectorAll(".report-checkbox").forEach((checkbox) => {
        checkbox.checked = e.target.checked;
    });
});

window.copyReportContent = async function() {
  const reportContentDiv = document.getElementById("report-modal-content");
  if (!reportContentDiv) {
    showToast("Report content not found.", "warning");
    return;
  }

  const htmlContent = reportContentDiv.innerHTML;
  const textContent = reportContentDiv.innerText; // Use innerText to preserve newlines better

  // 1. Try Modern Clipboard API with MIME types (Best for preserving formatting in Word/Docs)
  if (navigator.clipboard && typeof ClipboardItem !== 'undefined') {
    try {
      const clipboardItem = new ClipboardItem({
        "text/html": new Blob([htmlContent], { type: "text/html" }),
        "text/plain": new Blob([textContent], { type: "text/plain" }),
      });
      await navigator.clipboard.write([clipboardItem]);
      showToast("Report content copied to clipboard!", "success");
      return;
    } catch (err) {
      console.warn('ClipboardItem copy failed, trying simple text copy:', err);
    }
  }

  // 2. Try Modern Clipboard API Text-Only (Good for simple editors)
  if (navigator.clipboard && navigator.clipboard.writeText) {
    try {
      await navigator.clipboard.writeText(textContent);
      showToast("Copied as plain text.", "info");
      return;
    } catch (err) {
      console.warn('navigator.clipboard.writeText failed, trying legacy method:', err);
    }
  }

  // 3. Legacy Fallback (textarea hack) - Works in insecure contexts (HTTP)
  try {
    const textArea = document.createElement("textarea");
    textArea.value = textContent;
    
    // Ensure it's not visible but part of the DOM
    textArea.style.position = "fixed";
    textArea.style.left = "-9999px";
    textArea.style.top = "0";
    document.body.appendChild(textArea);
    
    textArea.focus();
    textArea.select();
    
    const successful = document.execCommand('copy');
    document.body.removeChild(textArea);
    
    if (successful) {
      showToast("Copied to clipboard (legacy mode).", "info");
    } else {
      throw new Error("execCommand returned false");
    }
  } catch (err) {
    console.error('All copy methods failed:', err);
    showToast("Failed to copy report content. Please copy manually.", "error");
  }
}