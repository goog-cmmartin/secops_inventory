QUnit.module('LLM Settings', function(hooks) {
  hooks.beforeEach(function() {
    // Mock the showToast function
    window.showToast = sinon.spy();
  });

  QUnit.test('populateLlmSettings success', async function(assert) {
    // Mock the fetch call
    const mockSettings = {
      llm_provider: 'openai',
      llm_model_name: 'gpt-4',
      llm_api_key: 'test-key',
      llm_gcp_project: 'test-project'
    };
    const fetchStub = sinon.stub(window, 'fetch');
    fetchStub.withArgs('/api/settings/llm').resolves(new Response(JSON.stringify(mockSettings), { status: 200 }));

    // Create mock DOM elements
    const provider = document.createElement('select');
    provider.id = 'llm-provider';
    provider.innerHTML = '<option value="vertex_ai"></option><option value="openai"></option>';
    const model = document.createElement('input');
    model.id = 'llm-model-name';
    const key = document.createElement('input');
    key.id = 'llm-api-key';
    const project = document.createElement('input');
    project.id = 'llm-gcp-project';
    document.getElementById('qunit-fixture').append(provider, model, key, project);

    await populateLlmSettings();

    assert.equal(provider.value, 'openai', 'Provider should be set');
    assert.equal(model.value, 'gpt-4', 'Model should be set');
    assert.equal(key.value, 'test-key', 'API key should be set');
    assert.equal(project.value, 'test-project', 'GCP project should be set');

    fetchStub.restore();
  });

  QUnit.test('saveLlmSettings success', async function(assert) {
    const fetchStub = sinon.stub(window, 'fetch');
    fetchStub.withArgs('/api/settings/llm').resolves(new Response(null, { status: 200 }));

    const form = document.createElement('form');
    form.innerHTML = `
      <input name="llm_provider" value="vertex_ai">
      <input name="llm_model_name" value="gemini-pro">
    `;
    
    const event = new Event('submit');
    sinon.stub(event, 'preventDefault');
    
    await saveLlmSettings(event, form);

    assert.ok(window.showToast.calledWith('LLM settings saved successfully!', 'success'), 'Success toast should be shown');

    fetchStub.restore();
  });
});
