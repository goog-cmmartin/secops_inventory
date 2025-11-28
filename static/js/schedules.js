document.addEventListener('DOMContentLoaded', () => {
  // --- DOM Elements ---
  const createScheduleBtn = document.getElementById('create-schedule-btn');
  const schedulesTableBody = document.getElementById('schedules-table');
  const scheduleModalEl = document.getElementById('schedule-modal');
  const scheduleModalTitle = document.getElementById('schedule-modal-title');
  const scheduleForm = document.getElementById('schedule-form');
  const scheduleIdInput = document.getElementById('schedule-id');
  const scheduleNameInput = document.getElementById('schedule-name');
  const scheduleTenantSelect = document.getElementById('schedule-tenant');
  const scheduleCronInput = document.getElementById('schedule-cron');
  const scheduleEnabledCheckbox = document.getElementById('schedule-enabled');
  const scheduleTypeRadios = document.querySelectorAll('input[name="schedule-type"]');
  const reportNameFormatGroup = document.getElementById('report-name-format-group');
  const reportNameFormatInput = document.getElementById('schedule-report-name-format');

  // --- State ---
  let scheduleModal;
  let scheduleAuditSelect;


  // --- Initialization ---
  function initializeScheduleModal() {
    scheduleModal = new Modal(scheduleModalEl);
    scheduleAuditSelect = new TomSelect('#schedule-audits', {
      create: false,
      sortField: { field: 'text', direction: 'asc' }
    });

    scheduleTypeRadios.forEach(radio => {
      radio.addEventListener('change', () => {
        if (radio.value === 'report' || radio.value === 'diff') {
          reportNameFormatGroup.classList.remove('hidden');
        } else {
          reportNameFormatGroup.classList.add('hidden');
        }
      });
    });
  }

  // --- API Calls ---
  async function fetchSchedules() {
    try {
      const response = await fetch('/api/schedules');
      if (!response.ok) throw new Error('Failed to fetch schedules.');
      const schedules = await response.json();
      renderSchedulesTable(schedules);
    } catch (error) {
      console.error('Error fetching schedules:', error);
      showToast(error.message, 'error');
    }
  }

async function saveSchedule() {
  const saveButton = document.querySelector('#schedule-modal button[onclick="saveSchedule()"]');
  const originalButtonText = saveButton.innerHTML;
  saveButton.disabled = true;
  saveButton.innerHTML = 'Saving...';

  const scheduleId = document.getElementById("schedule-id").value;
  const scheduleType = document.querySelector('input[name="schedule-type"]:checked').value;
  
  const data = {
    name: document.getElementById("schedule-name").value,
    project_id: document.getElementById("schedule-tenant").value,
    cron_schedule: document.getElementById("schedule-cron").value,
    is_enabled: document.getElementById("schedule-enabled").checked,
    audit_names: scheduleAuditSelect.getValue(),
    schedule_type: scheduleType,
    report_name_format: scheduleType === 'report' ? document.getElementById("schedule-report-name-format").value : null,
  };

  const url = scheduleId ? `/api/schedules/${scheduleId}` : "/api/schedules";
  const method = scheduleId ? "PUT" : "POST";

  try {
    const response = await fetch(url, {
      method: method,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
    if (!response.ok) {
      const err = await response.json();
      throw new Error(err.detail || "Failed to save schedule.");
    }
    showToast("Schedule saved successfully!", "success");
    scheduleModal.hide();
    fetchSchedules();
  } catch (error) {
    showToast(error.message, "error");
  } finally {
    saveButton.disabled = false;
    saveButton.innerHTML = originalButtonText;
  }
}

  async function deleteSchedule(scheduleId) {
    if (!confirm('Are you sure you want to delete this schedule?')) return;

    try {
      const response = await fetch(`/api/schedules/${scheduleId}`, { method: 'DELETE' });
      const result = await response.json();
      if (!response.ok) {
        throw new Error(result.detail || 'Failed to delete schedule.');
      }
      showToast('Schedule deleted successfully!', 'success');
      fetchSchedules(); // Refresh the table
    } catch (error) {
      console.error('Error deleting schedule:', error);
      showToast(error.message, 'error');
    }
  }


  // --- Rendering ---
  function renderSchedulesTable(schedules) {
    schedulesTableBody.innerHTML = '';
    if (schedules.length === 0) {
      schedulesTableBody.innerHTML = `<tr><td colspan="6" class="text-center p-4">No schedules found.</td></tr>`;
      return;
    }

    schedules.forEach(schedule => {
      const row = document.createElement('tr');
      row.className = 'bg-white border-b dark:bg-gray-800 dark:border-gray-700';
      row.innerHTML = `
        <td class="px-6 py-4 font-medium text-gray-900 whitespace-nowrap dark:text-white">${schedule.name}</td>
        <td class="px-6 py-4">${schedule.project_id}</td>
        <td class="px-6 py-4">${schedule.schedule_type.charAt(0).toUpperCase() + schedule.schedule_type.slice(1)}</td>
        <td class="px-6 py-4 font-mono">${schedule.cron_schedule}</td>
        <td class="px-6 py-4">
            <label class="relative inline-flex items-center cursor-pointer">
                <input type="checkbox" value="" class="sr-only peer" ${schedule.is_enabled ? 'checked' : ''} disabled>
                <div class="w-11 h-6 bg-gray-200 rounded-full peer dark:bg-gray-700 peer-checked:after:translate-x-full rtl:peer-checked:after:-translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-0.5 after:start-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all dark:border-gray-600 peer-checked:bg-blue-600"></div>
            </label>
        </td>
        <td class="px-6 py-4">
            <button type="button" class="font-medium text-blue-600 dark:text-blue-500 hover:underline mr-3">Edit</button>
            <button type="button" class="font-medium text-green-600 dark:text-green-500 hover:underline mr-3">Test Now</button>
            <button type="button" class="font-medium text-red-600 dark:text-red-500 hover:underline">Delete</button>
        </td>
      `;
      row.querySelector('button.text-blue-600').addEventListener('click', () => openScheduleModal(schedule));
      row.querySelector('button.text-green-600').addEventListener('click', () => testSchedule(schedule.id));
      row.querySelector('button.text-red-600').addEventListener('click', () => deleteSchedule(schedule.id));
      schedulesTableBody.appendChild(row);
    });
  }

  // --- Modal Logic ---
  function openScheduleModal(data = null) {
    scheduleForm.reset();
    scheduleAuditSelect.clear();
    scheduleAuditSelect.clearOptions();
    reportNameFormatGroup.classList.add('hidden');
    document.getElementById('schedule-type-audit').checked = true;


    // Populate tenants
    scheduleTenantSelect.innerHTML = tenantData.map(t => `<option value="${t.project_id}">${t.project_name} (${t.project_id})</option>`).join('');

    // Populate audits
    const auditOptions = Object.keys(availableAudits).map(name => ({ value: name, text: name }));
    scheduleAuditSelect.addOptions(auditOptions);

    if (data && data.id) { // Editing an existing schedule
      const schedule = data;
      scheduleModalTitle.textContent = 'Edit Schedule';
      scheduleIdInput.value = schedule.id;
      scheduleNameInput.value = schedule.name;
      scheduleTenantSelect.value = schedule.project_id;
      scheduleCronInput.value = schedule.cron_schedule;
      scheduleEnabledCheckbox.checked = schedule.is_enabled;
      scheduleAuditSelect.setValue(schedule.audits);
      
      document.getElementById(`schedule-type-${schedule.schedule_type}`).checked = true;
      if (schedule.schedule_type === 'report' || schedule.schedule_type === 'diff') {
        reportNameFormatGroup.classList.remove('hidden');
        reportNameFormatInput.value = schedule.report_name_format || '';
      }

    } else { // Creating a new schedule
      scheduleModalTitle.textContent = 'Create Schedule';
      scheduleIdInput.value = '';
      if (data) { // Pre-populating from Audits tab
        scheduleTenantSelect.value = data.project_id;
        scheduleAuditSelect.setValue(data.audit_names);
      }
    }
    scheduleModal.show();
  }


  // --- Event Listeners ---
  createScheduleBtn.addEventListener('click', () => openScheduleModal());
  document.getElementById('schedules-tab').addEventListener('click', fetchSchedules);


  // --- Global Functions ---
  window.openScheduleModal = openScheduleModal;
  window.saveSchedule = saveSchedule;
  window.setCronValue = function(value) {
    scheduleCronInput.value = value;
  }
  
  async function testSchedule(scheduleId) {
    try {
      const response = await fetch(`/api/schedules/${scheduleId}/run`, { method: 'POST' });
      const result = await response.json();
      if (!response.ok) {
        throw new Error(result.detail || 'Failed to trigger schedule.');
      }
      showToast(result.message, 'success');
    } catch (error) {
      showToast(error.message, 'error');
    }
  }

  window.testSchedule = testSchedule;
  window.deleteSchedule = deleteSchedule;
  
  // --- Initial Load ---
  initializeScheduleModal();
});