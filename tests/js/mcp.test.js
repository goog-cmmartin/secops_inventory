QUnit.module('MCP Assistant', function(hooks) {
  hooks.beforeEach(function() {
    // Mock global dependencies
    window.showToast = sinon.spy();
    window.escapeHtml = (unsafe) => unsafe; // Simple mock for testing
    window.marked = { parse: (text) => text }; // Simple mock
    window.DOMPurify = { sanitize: (html) => html }; // Simple mock
    window.TOOL_REGISTRY = ['list_tenants', 'list_audits'];

    // Create mock DOM elements
    const fixture = document.getElementById('qunit-fixture');
    fixture.innerHTML = `
      <div id="chat-messages"></div>
      <form id="mcp-chat-form">
        <input id="chat-input" type="text">
      </form>
      <div id="mcp-loading-indicator" class="hidden">
        <span id="mcp-loading-saying"></span>
      </div>
      <div id="slash-command-menu" class="hidden">
        <ul id="slash-command-list"></ul>
      </div>
    `;
  });

  QUnit.test('handleChatSubmit sends regular chat message', async function(assert) {
    const fetchStub = sinon.stub(window, 'fetch');
    fetchStub.withArgs('/api/mcp/chat').resolves(new Response(JSON.stringify({ response: 'Hello back' })));

    const input = document.getElementById('chat-input');
    input.value = 'Hello';

    await handleChatSubmit({ preventDefault: () => {} });

    assert.ok(fetchStub.calledWith('/api/mcp/chat'), 'Fetch should be called for a regular message');
    const chatMessages = document.getElementById('chat-messages').textContent;
    assert.ok(chatMessages.includes('Hello'), 'User message should be appended');
    // Using a small delay to allow the async fetch to complete and append the response
    await new Promise(resolve => setTimeout(resolve, 100));
    assert.ok(document.getElementById('chat-messages').textContent.includes('Hello back'), 'Assistant response should be appended');

    fetchStub.restore();
  });

  QUnit.test('handleChatSubmit sends slash command', async function(assert) {
    const fetchStub = sinon.stub(window, 'fetch');
    fetchStub.withArgs('/api/mcp/run_tool').resolves(new Response(JSON.stringify({ response: 'Tool output' })));

    const input = document.getElementById('chat-input');
    input.value = '/list_tenants';

    await handleChatSubmit({ preventDefault: () => {} });

    assert.ok(fetchStub.calledWith('/api/mcp/run_tool'), 'Fetch should be called for a slash command');
    const requestBody = JSON.parse(fetchStub.getCall(0).args[1].body);
    assert.equal(requestBody.command, 'list_tenants', 'Request body should contain the correct command');

    fetchStub.restore();
  });

  QUnit.test('handleChatInput shows and populates slash command menu', function(assert) {
    const input = document.getElementById('chat-input');
    const menu = document.getElementById('slash-command-menu');
    const list = document.getElementById('slash-command-list');
    
    input.value = '/list';
    // Manually trigger the event
    input.dispatchEvent(new Event('input'));

    assert.notOk(menu.classList.contains('hidden'), 'Slash command menu should be visible');
    assert.equal(list.children.length, 2, 'Menu should be populated with matching tools');
    assert.ok(list.textContent.includes('/list_tenants'), 'Menu should contain list_tenants');
    assert.ok(list.textContent.includes('/list_audits'), 'Menu should contain list_audits');
  });
});
