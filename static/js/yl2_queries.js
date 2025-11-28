// --- YL2 Query Functions ---
async function fetchCustomYl2Queries() {
  try {
    const response = await fetch("/api/yl2_queries");
    if (!response.ok) throw new Error("Failed to fetch YL2 queries");
    const queries = await response.json();
    const tableBody = document.getElementById("yl2-queries-table");
    tableBody.innerHTML = "";
    queries.forEach((query) => {
      const row = `
        <tr class="bg-white border-b dark:bg-gray-800 dark:border-gray-700">
          <td class="px-6 py-4 font-medium">${query.name}</td>
          <td class="px-6 py-4">${query.category}</td>
          <td class="px-6 py-4">${query.time_value} ${query.time_unit}(s)</td>
          <td class="px-6 py-4 space-x-2">
            <button class="font-medium text-blue-600 hover:underline" onclick='openYl2Modal(${JSON.stringify(
              query
            )})'>Edit</button>
            <button class="font-medium text-red-600 hover:underline" onclick="deleteYl2Query(${
              query.id
            })">Delete</button>
          </td>
        </tr>
      `;
      tableBody.insertAdjacentHTML("beforeend", row);
    });
  } catch (error) {
    showToast(error.message, "error");
  }
}

function openYl2Modal(query = null) {
  const form = document.getElementById("yl2-query-form");
  form.reset();
  document.getElementById("yl2-query-id").value = "";

  // --- NEW: Populate Category Dropdown ---
  const categorySelect = document.getElementById("yl2-query-category");
  categorySelect.innerHTML = ""; // Clear existing options
  const uniqueCategories = [...new Set(Object.values(availableAudits).map(a => a.category))];
  uniqueCategories.sort().forEach(category => {
    const option = new Option(category, category);
    categorySelect.add(option);
  });
  // --- END NEW ---

  if (query) {
    document.getElementById("yl2-modal-title").textContent = "Edit Custom Query";
    document.getElementById("yl2-query-id").value = query.id;
    document.getElementById("yl2-query-name").value = query.name;
    document.getElementById("yl2-query-text").value = query.query;
    categorySelect.value = query.category; // Pre-select the category
  } else {
    document.getElementById("yl2-modal-title").textContent =
      "Create Custom Query";
  }
  yl2QueryModal.show();
}

async function saveYl2Query() {
  const saveButton = document.querySelector('#yl2-query-modal button[onclick="saveYl2Query()"]');
  const originalButtonText = saveButton.innerHTML;
  saveButton.disabled = true;
  saveButton.innerHTML = 'Saving...';

  const queryId = document.getElementById("yl2-query-id").value;
  const data = {
    name: document.getElementById("yl2-query-name").value,
    category: document.getElementById("yl2-query-category").value,
    yl2_query: document.getElementById("yl2-query-text").value,
    time_unit: document.getElementById("yl2-query-time-unit").value,
    time_value: parseInt(document.getElementById("yl2-query-time-value").value, 10)
  };
  const url = queryId ? `/api/yl2_queries/${queryId}` : "/api/yl2_queries";
  const method = queryId ? "PUT" : "POST";

  try {
    const response = await fetch(url, {
      method: method,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
    if (!response.ok) {
      const err = await response.json();
      throw new Error(err.detail || "Failed to save query.");
    }
    showToast("Query saved successfully!", "success");
    yl2QueryModal.hide();
    fetchCustomYl2Queries(); // Refresh the settings table
    if (typeof populateAudits === "function") {
      populateAudits(); // Refresh the main audits tab table
    }
  } catch (error) {
    showToast(error.message, "error");
  } finally {
    saveButton.disabled = false;
    saveButton.innerHTML = originalButtonText;
  }
}

async function deleteYl2Query(queryId) {
  if (!confirm("Are you sure you want to delete this query?")) return;
  try {
    const response = await fetch(`/api/yl2_queries/${queryId}`, {
      method: "DELETE",
    });
    if (!response.ok) {
      const err = await response.json();
      throw new Error(err.detail || "Failed to delete query.");
    }
    showToast("Query deleted successfully.", "success");
    fetchCustomYl2Queries();
    if (typeof populateAudits === "function") {
      populateAudits(); // Refresh the main audits tab table
    }
  } catch (error) {
    showToast(error.message, "error");
  }
}
