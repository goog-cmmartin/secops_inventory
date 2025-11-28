## SecOps Inventory & Intelligence Platform - Product Requirements Document

*   **Author:** Gemini CLI Agent
*   **Status:** Version 2.2
*   **Date:** October 10, 2025

### 1. Introduction

The SecOps Inventory & Intelligence Platform is a web-based application designed to streamline the management, auditing, and analysis of multi-platform SecOps environments, including Google SecOps (Chronicle), SecOps SOAR, and BindPlane. The platform provides a centralized inventory, a dynamic and extensible audit engine, a powerful AI-driven reporting system, and an interactive AI assistant.

The core value proposition is to transform raw configuration data from multiple, disparate APIs into actionable intelligence, enabling security professionals to quickly assess security posture, identify misconfigurations, and generate executive-ready reports through a seamless, GUI-driven experience.

### 2. Goals and Objectives

*   **Primary Goal:** To simplify and automate the process of auditing and reporting on SecOps tenant configurations across multiple platforms.
*   **Objectives:**
    *   Provide a centralized, single-pane-of-glass view of all managed tenants.
    *   Offer a seamless, GUI-driven setup wizard for initial application and tenant onboarding.
    *   Support flexible authentication methods (GCP ADC, Service Accounts) to adapt to different security environments.
    *   Provide a fully dynamic and user-configurable audit engine that can target any API.
    *   Automate the execution of configuration audits against configured APIs (Chronicle, SOAR, BindPlane, etc.).
    *   Automate the generation of focused diff reports, highlighting only configuration changes between audit runs.
    *   Leverage a powerful Generative AI model (Gemini 2.5 Pro) to create intelligent, human-readable summaries from raw API data.
    *   Enable the correlation of data from multiple audit sources to uncover complex insights.
    *   Offer an interactive, conversational AI assistant to query application data using natural language.
    *   Provide a comprehensive "Home" dashboard for at-a-glance visibility into system status, recent reports, and key metrics.
    *   Offer easy-to-use export and copy functionality for sharing and archiving reports and templates.

### 3. User Personas

*   **Security Analyst / Engineer:** The primary user. They use the platform to run audits, verify configurations, generate detailed reports, and interact with the MCP Assistant to quickly query data.
*   **Security Manager / Team Lead:** This user oversees the security posture of multiple environments. They use the generated reports, high-level Insights, and the MCP assistant to quickly understand risks and track configuration drift.
*   **Platform Administrator:** This user is responsible for the initial setup and configuration of the application, including authentication and tenant onboarding.

### 4. Core Features

#### 4.1. First-Time Setup Wizard
*   **Automated Onboarding:** On first launch, the application presents a GUI-driven wizard that guides the administrator through the entire setup process.
*   **Database Initialization:** The first step of the wizard initializes the application's SQLite database with a single click.
*   **Tenant Discovery & Creation:**
    *   **Automatic Discovery:** Users can provide a GCP Organization ID to trigger a background task that automatically discovers all projects with the Chronicle API enabled.
    *   **Manual Entry:** Users can manually add individual tenants by providing a Project ID and Display Name.
    *   **Status Polling:** The UI provides real-time feedback on the status of the background discovery task.

#### 4.2. Tenant & Audit Configuration (`Setup` & `Settings` Tabs)
*   **Centralized Inventory:** The main `Setup` tab lists all discovered or manually added tenants.
*   **Multi-API Credential Management:** The "Configure Tenant" modal allows users to configure credentials for multiple services linked to a single tenant (Google SecOps, SecOps SOAR, BindPlane).
*   **Dynamic Audit Management:** The "Configurable Audits" section under `Settings` provides full CRUD functionality for all audits, allowing users to define the target API, method, response format, and more.
*   **In-Modal Testing:** When creating or editing an audit, a "Test Audit" button allows the user to immediately execute it against a selected tenant and view the raw results.

#### 4.3. Audit Engine & AI Reporting (`Audits`, `Insights`, `Reports` Tabs)
*   **Unified Audit Execution:** The `Audits` tab provides a single interface to run any configured audit against a selected tenant.
*   **UI Enhancements:** Includes live filtering and a "Select All" checkbox for ease of use.
*   **AI-Powered Reports & Insights:** The core reporting functionality is powered by a dynamic audit engine, allowing reports and insights to be generated from any configured API source.
*   **Scheduled Diff Reports:** Users can schedule diff reports to automatically highlight only significant configuration changes between audit runs, reducing noise and focusing on actionable intelligence.
*   **Multi-API Correlation:** The `Insights` feature can correlate data from different platforms (e.g., combine data from a Chronicle audit and a SOAR audit) into a single analysis.

#### 4.4. MCP Assistant (Conversational Interface)
*   **Natural Language Interaction:** A new "MCP Assistant" tab provides a chat-based interface for interacting with the application's data using natural language (e.g., "Hello! I am the SecOps Inventory MCP Assistant...").
*   **Direct Tool Execution:** For power users, typing `/` as the first character in the chat input reveals a menu of available tools. Selecting a tool allows for direct execution, bypassing the natural language model for faster, more predictable actions (e.g., `/list_tenants`).
*   **Tool-Enabled Agent:** The assistant is powered by a Gemini large language model equipped with tools to query the application's backend, allowing it to answer questions about tenants, audits, and results (e.g., "what tenants are available?", "show me the latest results for the 'Rules' audit").
*   **Session Context:** The assistant can maintain context within a session. Users can set a default tenant (e.g., "set tenant to project-123"), and all subsequent commands in that session will automatically target that tenant.
*   **Conversation Management:** The interface supports starting new sessions to clear the conversation history and reset the agent's context.
*   **Markdown Rendering:** The assistant's responses are rendered as Markdown, allowing for clear and structured formatting of data like tables and lists.

#### 4.5. Home / Dashboard
*   **Centralized Overview:** A default landing page provides a high-level summary of the application's state.
*   **Key Metrics:** Displays real-time counts for configured Tenants, available Audit definitions, active Insights, and scheduled jobs.
*   **Recent Activity:** Lists the most recently generated reports for quick access.
*   **Configuration Stats:** Shows the number of custom settings (LLM Prompts, YL2 Queries) to help administrators track customization levels.
*   **Interactive Widgets:** Each dashboard widget serves as a deep link to its respective section, improving navigation efficiency.

### 5. Technical Architecture
*   **Frontend:** A single-page application built with vanilla JavaScript, HTML, and styled with **Tailwind CSS** and the **Flowbite** component library.
*   **Backend:** A Python-based API built with the **FastAPI** framework.
*   **Database:** A local **SQLite** database that stores all application data, including associations for scheduled audit, report, and diff generation.
*   **Authentication:** A flexible system that reads a `config.ini` file to determine the authentication method for Google Cloud (ADC or Service Account). API key authentication for other services is handled on a per-request basis.
*   **Asynchronous Task Processing:** **Celery** and **Redis** are used to run long-running tasks (AI report generation, tenant discovery, diff report generation) in the background.
*   **Generic API Client:** A central `make_api_request` function handles different authentication methods and response formats.
*   **AI Integration:** The backend communicates with the Google Gemini API (`gemini-2.5-pro`) via the official Python SDK for both report generation and the MCP Assistant.