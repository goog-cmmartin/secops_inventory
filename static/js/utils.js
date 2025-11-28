// --- Utility Functions ---

function showToast(message, type = "info") {
  const toastContainer = document.getElementById("toast-container");
  const toastId = `toast-${Date.now()}`;
  const toastColors = {
    info: "bg-blue-500",
    success: "bg-green-500",
    warning: "bg-yellow-500",
    error: "bg-red-500",
  };

  const toastHtml = `
    <div id="${toastId}" class="flex items-center w-full max-w-xs p-4 space-x-4 text-white ${
      toastColors[type]
    } rounded-lg shadow" role="alert">
      <div class="text-sm font-normal">${message}</div>
      <button type="button" class="ms-auto -mx-1.5 -my-1.5 rounded-lg p-1.5 hover:bg-white/20 inline-flex items-center justify-center h-8 w-8" onclick="document.getElementById('${toastId}').remove()">
        <span class="sr-only">Close</span>
        <svg class="w-3 h-3" aria-hidden="true" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 14 14"><path stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="m1 1 6 6m0 0 6 6M7 7l6-6M7 7l-6 6"/></svg>
      </button>
    </div>
  `;
  toastContainer.insertAdjacentHTML("beforeend", toastHtml);

  setTimeout(() => {
    const toastElement = document.getElementById(toastId);
    if (toastElement) {
      toastElement.remove();
    }
  }, 5000);
}

function escapeHtml(unsafe) {
    return unsafe
         .replace(/&/g, "&amp;")
         .replace(/</g, "&lt;")
         .replace(/>/g, "&gt;")
         .replace(/"/g, "&quot;")
         .replace(/'/g, "&#039;");
 }

 async function fetchInitialAuditsAndPrompts() {
  try {
    const response = await fetch("/api/audits");
    if (!response.ok) throw new Error("Failed to fetch audits");
    availableAudits = await response.json();
  } catch (error) {
    showToast(error.message, "error");
  }
}