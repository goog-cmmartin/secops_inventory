"""
This file contains the core logic for the Fast MCP agent. It initializes the
Generative AI model, provides it with the available tools from mcp_tools.py,
and exposes a function to run a chat session with the agent.
"""

import google.generativeai as genai
import mcp_tools

# --- Agent Configuration ---

# Configure the Generative AI model
# Note: The API key is already configured in main.py, so we don't need to do it here.
model = genai.GenerativeModel(
    model_name='gemini-2.5-pro',
    # We can add a system prompt to give the agent a persona and instructions.
    system_instruction=(
        "You are a SecOps Inventory Assistant. Your role is to help users query "
        "the status and results of their SecOps tenants and audits. "
        "Use the available tools to answer user questions. "
        "You can set a default tenant for the current session using the 'set_session_tenant' tool; "
        "once set, you don't need to ask for the tenant_project_id for other tools. "
        "When presenting data, format it clearly using Markdown. "
        "If you don't know the answer or a tool fails, say so clearly. "
        "Do not make up information."
    )
)

# Define the set of tools that the agent can use.
# The AI will automatically understand the function signatures and docstrings.
TOOLSET = [
    mcp_tools.list_tenants,
    mcp_tools.list_audits,
    mcp_tools.get_latest_audit_results,
    mcp_tools.set_session_tenant,
    mcp_tools.read_local_file,
]

# --- Agent Execution ---

def start_chat_session():
    """
    Starts a new chat session with the AI agent, equipped with our toolset.
    """
    # Enable function calling with our defined tools
    chat = model.start_chat(enable_automatic_function_calling=True)
    return chat

def run_chat_message(chat_session, user_message: str) -> str:
    """
    Sends a user's message to the chat session and gets the agent's response.

    Args:
        chat_session: An active chat session started with start_chat_session.
        user_message: The user's natural language query.

    Returns:
        The agent's final, text-based response after any tool calls.
    """
    try:
        response = chat_session.send_message(user_message, tools=TOOLSET)
        return response.text
    except Exception as e:
        print(f"--- MCP Agent Error: {e} ---")
        return "An error occurred while processing your request. Please check the backend logs for details."
