# Plan for Implementing Audit Diff Functionality

This document outlines the plan to implement a "diff" capability in the SecOps Inventory application. The goal is to allow users to compare the two most recent successful runs of an audit and generate an LLM-based report summarizing the changes.

---

## Phase 1: Backend Implementation (The Core Logic)

The backend will be responsible for the core logic of finding the audits, computing the difference between their results, and generating the report.

### Step 1: Create a Core Diffing Utility

-   **Action:** Create a new helper function in `utils.py` named `generate_json_diff`.
-   **Details:**
    -   This function will accept the JSON content of two audit results as input.
    -   It will pretty-print both JSON objects into formatted strings.
    -   It will use Python's built-in `difflib` library to generate a human-readable, unified diff text (showing `+` for additions and `-` for deletions).
    -   This textual diff will serve as the primary context for the LLM.

### Step 2: Develop a New Celery Task

-   **Action:** Create a new asynchronous task in `celery_worker.py` named `generate_diff_report_task`.
-   **Details:** This task will perform the following steps:
    1.  Accept a `project_id` and `audit_name` as arguments.
    2.  Query the database to find the two most recent `Audit` records with a `status` of "Success" for the given `project_id` and `audit_name`, ordered by `run_timestamp` descending.
    3.  If fewer than two successful audits are found, the task will fail gracefully and report this back to the user.
    4.  Call the `generate_json_diff` utility from Step 1, passing the `results` of the two audit records.
    5.  Create a new, specialized prompt for the LLM, instructing it to act as a security analyst and summarize the *changes* highlighted in the provided diff text.
    6.  Call the existing `generate_gemini_summary` function with the new prompt and the generated diff.
    7.  Save the final summary as a new `Report` in the database. The report name will be descriptive, such as "Diff Report: [Audit Name] - [Timestamp]".

### Step 3: Create a New API Endpoint

-   **Action:** Add a new API endpoint to `main.py`: `POST /api/tenants/{project_id}/audits/{audit_name}/diff_report`.
-   **Details:**
    -   This endpoint will be the trigger for the new functionality.
    -   When called by the frontend, it will dispatch the `generate_diff_report_task` Celery task.
    -   It will return the `task_id` to the frontend, allowing the UI to poll for the status of the report generation.

---

## Phase 2: Frontend Implementation (The User Experience)

The frontend will be updated to provide an intuitive way for users to access this new feature.

### Step 1: Enhance the "Audits" Tab UI

-   **Action:** Modify the `populateAudits` function in `static/js/audits.js` to add a "Diff Report" button next to each audit.
-   **Details:**
    -   The "Diff Report" button will be conditionally enabled. It will only become active if an audit has at least **two** successful runs.
    -   To facilitate this, the backend endpoint `/api/tenants/{project_id}/audits/status` will be updated to include a `successful_run_count` for each audit.
    -   The frontend will use this count to dynamically manage the button's state (enabled/disabled).

### Step 2: Implement the Frontend Logic

-   **Action:** Add a new JavaScript function, `generateDiffReport(auditName)`, to `audits.js`.
-   **Details:**
    -   This function will be triggered when the "Diff Report" button is clicked.
    -   It will make a `POST` request to the new API endpoint created in Backend Step 3.
    -   It will reuse the existing report generation UI pattern:
        -   Display a spinner to indicate that the process has started.
        -   Show a toast notification (e.g., "Diff Report generation started...").
        -   Poll the status endpoint using the returned `task_id`.
    -   Once the task is complete, the new diff report will be available in the "Reports" tab, just like any other generated report.
