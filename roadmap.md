# Roadmap

This document outlines the development history and potential future enhancements for the SecOps Inventory Platform.

---

## Completed Features (Version 2.x)

*   **Full MCP Agent Integration:** ✅ **Done.** The application is now fully integrated with a Gemini-powered agent. The agent has a dedicated chat interface and is equipped with a toolset to interact with the application's data using both natural language and direct slash-commands.

*   **Generic API Auditing:** ✅ **Done.** The audit engine has been refactored to be fully dynamic. The `make_api_request` function is now generic, and the `AuditType` model supports defining different authentication methods and target URLs, allowing the platform to audit any API (e.g., Chronicle, SOAR, BindPlane) through the "Configurable Audits" interface.

---

## Future Roadmap

### Core Functionality

*   **Scheduled Audits & Diff Reporting:**
    *   **Goal:** Allow users to schedule audits to run automatically on a recurring basis (e.g., daily, weekly).
    *   **Enhancement:** Building on scheduling, create a "diff check" feature that compares the results of the latest audit run with the previous one and generates a report highlighting only what has changed.

*   **Multi-Tenant Operations:**
    *   **Goal:** Enable users to select multiple tenants and run actions (like audits or report generation) across all of them simultaneously, instead of one by one.

*   **User Authentication:**
    *   **Goal:** Implement a user login system to secure access to the platform and potentially provide role-based access controls.

### User Experience & Usability

*   **Usability Enhancements:**
    *   **Goal:** Improve the user experience by adding more inline help, such as tooltips on buttons and form fields.
    *   **Enhancement:** Create a dedicated "Help" page or section with more detailed documentation on how to use the application's features.

*   **Advanced Export Options:**
    *   **Goal:** Allow users to select multiple generated reports from the "Reports" tab and export them into a single, combined Markdown file for easier distribution.

*   **Data Visualization:**
    *   **Goal:** Integrate a charting library (e.g., Chart.js) to create visual dashboards from audit data, providing a more intuitive way to understand the results.

### MCP Agent Enhancements

*   **Local File System Tool:**
    *   **Goal:** Add a new tool to the MCP Assistant that allows it to read the content of local files (within the project directory). This would enable it to answer questions based on documentation (`.md`), configuration (`.ini`), or other text-based files.
