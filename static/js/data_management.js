document.addEventListener('DOMContentLoaded', () => {
  const dataManagementTab = document.getElementById('data-management-tab');
  if (dataManagementTab) {
    dataManagementTab.addEventListener('click', populatePurgeAuditSelect);
  }
});

function populatePurgeAuditSelect() {
  const select = document.getElementById('purge-audit-select');
  // Prevent re-populating if already filled
  if (select.options.length > 1) return;

  // Use the global availableAudits variable
  const auditNames = Object.keys(availableAudits).sort();
  auditNames.forEach(name => {
    const option = new Option(name, name);
    select.add(option);
  });
}

async function purgeOldAudits() {
  if (!confirm("Are you sure you want to permanently delete old audit records? This action cannot be undone.")) {
    return;
  }

  const purgeButton = document.querySelector('button[onclick="purgeOldAudits()"]');
  const originalButtonText = purgeButton.innerHTML;
  purgeButton.disabled = true;
  purgeButton.innerHTML = 'Purging...';

  const olderThanDays = document.getElementById("purge-days-input").value;
  const auditName = document.getElementById("purge-audit-select").value;

  const payload = {
    older_than_days: parseInt(olderThanDays),
    audit_name: auditName || null,
  };

  try {
    const response = await fetch("/api/audits/purge", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const result = await response.json();
    if (!response.ok) {
      throw new Error(result.detail || "Failed to start purge task.");
    }
    showToast("Purge task started...", "info");
    pollPurgeStatus(result.task_id, purgeButton, originalButtonText);
  } catch (error) {
    showToast(error.message, "error");
    purgeButton.disabled = false;
    purgeButton.innerHTML = originalButtonText;
  }
}

function pollPurgeStatus(taskId, button, originalText) {
  const interval = setInterval(async () => {
    try {
      const response = await fetch(`/api/reports/status/${taskId}`);
      const result = await response.json();

      if (result.state === "SUCCESS" || result.state === "FAILURE") {
        clearInterval(interval);
        button.disabled = false;
        button.innerHTML = originalText;
        if (result.state === "SUCCESS") {
          showToast(result.status, "success");
        } else {
          showToast(`Purge failed: ${result.status}`, "error");
        }
      }
    } catch (error) {
      clearInterval(interval);
      button.disabled = false;
      button.innerHTML = originalText;
      showToast("Error checking purge status.", "error");
    }
  }, 3000);
}
