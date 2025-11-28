// --- MCP Assistant Functions ---
let chatSessionId = null;

const loadingSayings = [
  "Analyzing data streams...",
  "Consulting with the Chronicle mothership...",
  "Reticulating splines...",
  "Engaging security protocols...",
  "Cross-referencing threat intelligence...",
];

document.addEventListener('DOMContentLoaded', function() {
    renderSuggestionChips();
});

function renderSuggestionChips() {
    const container = document.getElementById('mcp-suggestion-chips');
    if (!container) return;

    const activeTenantId = getActiveTenant();
    let suggestions = [];

    if (activeTenantId && tenantData) {
        const activeTenant = tenantData.find(t => t.project_id === activeTenantId);
        if (activeTenant) {
            suggestions.push(`Set the active tenant to ${activeTenant.project_id} (${activeTenant.project_name})`);
        }
    }
    
    suggestions.push('List available tenants');

    container.innerHTML = suggestions.map(text => 
        `<button 
            type="button" 
            onclick="submitSuggestion('${text}')"
            class="text-sm font-medium px-3 py-1 rounded-full bg-gray-200 text-gray-700 hover:bg-gray-300 dark:bg-gray-600 dark:text-gray-200 dark:hover:bg-gray-500"
         >
            ${text}
         </button>`
    ).join('');
}

function submitSuggestion(text) {
    const input = document.getElementById('chat-input');
    const form = document.getElementById('mcp-chat-form');
    input.value = text;
    form.requestSubmit();
}

async function startNewChatSession() {
  try {
    const response = await fetch("/api/mcp/new_session", {
      method: "POST",
    });
    if (!response.ok) throw new Error("Failed to start new session.");
    const data = await response.json();
    document.getElementById("chat-messages").innerHTML = `
    <div class="flex items-start gap-2.5 mb-4">
        <img class="w-8 h-8 rounded-full" src="/static/icons/security.svg" alt="MCP Assistant">
        <div class="flex flex-col gap-1 w-full max-w-[620px]">
            <div class="flex items-center space-x-2 rtl:space-x-reverse">
                <span class="text-sm font-semibold text-gray-900 dark:text-white">MCP Assistant</span>
            </div>
            <div class="flex flex-col leading-1.5 p-4 border-gray-200 bg-gray-100 rounded-e-xl rounded-es-xl dark:bg-gray-700 prose dark:prose-invert max-w-none">
                <p class="text-sm font-normal">
                    Session reset. How can I help you today?
                </p>
            </div>
             <div id="mcp-suggestion-chips" class="flex flex-wrap gap-2 mt-2">
                <!-- Chips will be dynamically inserted here -->
             </div>
        </div>
    </div>`;
    renderSuggestionChips(); // Re-render suggestions for the new session
    showToast(data.message, "success");
  } catch (error) {
    showToast(error.message, "error");
  }
}

async function handleChatSubmit(event) {
  event.preventDefault();
  const input = document.getElementById("chat-input");
  const message = input.value.trim();
  if (!message) return;

  appendMessage(message, "user");
  input.value = "";
  toggleSlashMenu(false);
  showLoadingIndicator();

  // Check if it's a slash command and run directly
  if (message.startsWith("/")) {
    try {
      const response = await fetch("/api/mcp/run_tool", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ command: message.substring(1) }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Tool execution failed.");
      appendMessage(data.response, "assistant", true); // Render as preformatted
    } catch (error) {
      appendMessage(`Error: ${error.message}`, "assistant");
    } finally {
      hideLoadingIndicator();
    }
  } else {
    // Regular chat message
    try {
      const response = await fetch("/api/mcp/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: message }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Chat failed.");
      appendMessage(data.response, "assistant");
    } catch (error) {
      appendMessage(`Error: ${error.message}`, "assistant");
    } finally {
      hideLoadingIndicator();
    }
  }
}

function appendMessage(content, sender, isPreformatted = false) {
  const messagesContainer = document.getElementById("chat-messages");
  const messageDiv = document.createElement("div");
  const isUser = sender === "user";

  let formattedContent = isPreformatted
    ? `<pre class="text-sm font-normal text-gray-900 dark:text-white whitespace-pre-wrap">${escapeHtml(
        content
      )}</pre>`
    : DOMPurify.sanitize(marked.parse(content));

  messageDiv.className = `flex items-start gap-2.5 mb-4 ${
    isUser ? "justify-end" : ""
  }`;
  messageDiv.innerHTML = `
    ${
      !isUser
        ? '<img class="w-8 h-8 rounded-full" src="/static/icons/security.svg" alt="MCP Assistant">'
        : ""
    }
    <div class="flex flex-col gap-1 w-full max-w-[${isUser ? '620px' : 'none'}]">
        <div class="flex items-center space-x-2 ${
          isUser ? "justify-end" : "rtl:space-x-reverse"
        }">
            <span class="text-sm font-semibold text-gray-900 dark:text-white">${
              isUser ? "You" : "MCP Assistant"
            }</span>
        </div>
        <div class="flex flex-col leading-1.5 p-4 ${
          isUser
            ? "bg-blue-600 rounded-s-xl rounded-ee-xl"
            : "bg-gray-100 dark:bg-gray-700 rounded-e-xl rounded-es-xl"
        }">
           <div class="prose dark:prose-invert max-w-none">
            ${formattedContent}
            </div>
        </div>
    </div>
     ${
       isUser
         ? '<img class="w-8 h-8 rounded-full" src="/static/icons/code.svg" alt="User">'
         : ""
     }
`;
  messagesContainer.appendChild(messageDiv);
  messagesContainer.scrollTop = messagesContainer.scrollHeight;
}

function showLoadingIndicator() {
  const messagesContainer = document.getElementById("chat-messages");
  const saying = loadingSayings[Math.floor(Math.random() * loadingSayings.length)];
  const indicatorHtml = `
    <div id="mcp-loading-indicator" class="flex items-start gap-2.5 mb-4">
      <img class="w-8 h-8 rounded-full" src="/static/icons/security.svg" alt="MCP Assistant">
      <div class="flex flex-col gap-1 w-full">
        <div class="flex items-center space-x-2 rtl:space-x-reverse">
          <span class="text-sm font-semibold text-gray-900 dark:text-white">MCP Assistant</span>
        </div>
        <div class="flex flex-col leading-1.5 p-4 dark:bg-transparent">
          <div class="flex items-center space-x-2">
            <svg aria-hidden="true" class="w-5 h-5 text-gray-400 animate-spin" viewBox="0 0 100 101" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path d="M100 50.5908C100 78.2051 77.6142 100.591 50 100.591C22.3858 100.591 0 78.2051 0 50.5908C0 22.9766 22.3858 0.59082 50 0.59082C77.6142 0.59082 100 22.9766 100 50.5908ZM9.08144 50.5908C9.08144 73.1895 27.4013 91.5094 50 91.5094C72.5987 91.5094 90.9186 73.1895 90.9186 50.5908C90.9186 27.9921 72.5987 9.67226 50 9.67226C27.4013 9.67226 9.08144 27.9921 9.08144 50.5908Z" fill="currentColor"/>
              <path d="M93.9676 39.0409C96.393 38.4038 97.8624 35.9116 97.0079 33.5539C95.2932 28.8227 92.871 24.3692 89.8167 20.348C85.8452 15.1192 80.8826 10.7238 75.2124 7.41289C69.5422 4.10194 63.2754 1.94025 56.7698 1.05124C51.7666 0.367541 46.6976 0.446843 41.7345 1.27873C39.2613 1.69328 37.813 4.19778 38.4501 6.62326C39.0873 9.04874 41.5694 10.4717 44.0505 10.1071C47.8511 9.54855 51.7191 9.52689 55.5402 10.0492C60.8642 10.7766 65.9928 12.5457 70.6331 15.2552C75.2735 17.9648 79.3347 21.5619 82.5849 25.841C84.9175 28.9121 86.7997 32.2913 88.1811 35.8758C89.083 38.2158 91.5421 39.6781 93.9676 39.0409Z" fill="currentFill"/>
            </svg>
            <p class="text-sm font-normal italic text-gray-900 dark:text-white ml-2">${saying}</p>
          </div>
        </div>
      </div>
    </div>
  `;
  messagesContainer.insertAdjacentHTML('beforeend', indicatorHtml);
  messagesContainer.scrollTop = messagesContainer.scrollHeight;
}

function hideLoadingIndicator() {
  const indicator = document.getElementById("mcp-loading-indicator");
  if (indicator) {
    indicator.remove();
  }
}

function handleChatInput(event) {
  const text = event.target.value;
  if (text.startsWith("/")) {
    const searchTerm = text.substring(1).toLowerCase();
    const matchingTools = Object.keys(TOOL_REGISTRY).filter((tool) =>
      tool.toLowerCase().includes(searchTerm)
    );
    populateSlashMenu(matchingTools);
    toggleSlashMenu(matchingTools.length > 0);
  } else {
    toggleSlashMenu(false);
  }
}

function toggleSlashMenu(show) {
  const menu = document.getElementById("slash-command-menu");
  if (show) {
    menu.classList.remove("hidden");
  } else {
    menu.classList.add("hidden");
  }
}

function populateSlashMenu(tools) {
  const list = document.getElementById("slash-command-list");
  list.innerHTML = "";
  tools.forEach((tool) => {
    const item = document.createElement("li");
    item.className =
      "p-2 hover:bg-gray-100 dark:hover:bg-gray-600 cursor-pointer";
    item.textContent = `/${tool}`;
    item.onclick = () => {
      document.getElementById("chat-input").value = `/${tool} `;
      document.getElementById("chat-input").focus();
      toggleSlashMenu(false);
    };
    list.appendChild(item);
  });
}

// Close slash command menu if clicked outside
document.addEventListener("click", function (event) {
  const chatInput = document.getElementById("chat-input");
  const slashMenu = document.getElementById("slash-command-menu");
  if (chatInput && !chatInput.contains(event.target) && slashMenu && !slashMenu.contains(event.target)) {
    toggleSlashMenu(false);
  }
});