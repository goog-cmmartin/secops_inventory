// --- Chronicle API Tab Functions ---
async function handleApiRequest() {
  const projectId = document.getElementById("tenant-select").value;
  if (!projectId || projectId === "Choose a tenant") {
    showToast("Please select a tenant first.", "warning");
    return;
  }

  const sendButton = document.querySelector('#api-explorer button[onclick="handleApiRequest()"]');
  const originalButtonText = sendButton.innerHTML;
  sendButton.disabled = true;
  sendButton.innerHTML = 'Sending...';

  const responsePre = document.getElementById("api-response").querySelector("code");
  responsePre.textContent = "Loading...";

  const request = {
    method: document.getElementById("api-method").value,
    api_path: document.getElementById("api-path").value,
    json_data: null,
  };

  const jsonDataText = document.getElementById("api-json").value;
  if (jsonDataText) {
    try {
      request.json_data = JSON.parse(jsonDataText);
    } catch (e) {
      responsePre.textContent = `Error parsing JSON body: ${e.message}`;
      sendButton.disabled = false;
      sendButton.innerHTML = originalButtonText;
      return;
    }
  }

  try {
    const response = await fetch(
      `/api/tenants/${projectId}/chronicle_api`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(request),
      }
    );
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.detail || "API request failed");
    }
    responsePre.textContent = JSON.stringify(data, null, 2);
  } catch (error) {
    responsePre.textContent = `Error: ${error.message}`;
  } finally {
    sendButton.disabled = false;
    sendButton.innerHTML = originalButtonText;
  }
}
