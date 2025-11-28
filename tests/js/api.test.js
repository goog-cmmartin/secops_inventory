QUnit.module('Chronicle API', function(hooks) {
  hooks.beforeEach(function() {
    // Mock global dependencies
    window.showToast = sinon.spy();
    
    // Create mock DOM elements in the QUnit fixture
    const fixture = document.getElementById('qunit-fixture');
    fixture.innerHTML = `
      <select id="tenant-select">
        <option value="test-project">Test Project</option>
      </select>
      <select id="api-method">
        <option value="GET">GET</option>
      </select>
      <input type="text" id="api-path" value="v1alpha/feeds">
      <textarea id="api-json"></textarea>
      <div id="api-response"><code></code></div>
    `;
    // Make sure the global tenantSelect is pointing to our mock element
    window.tenantSelect = document.getElementById('tenant-select');
  });

  QUnit.test('handleApiRequest success', async function(assert) {
    const fetchStub = sinon.stub(window, 'fetch');
    const mockApiResponse = { feeds: ["feed1"] };
    fetchStub.withArgs('/api/tenants/test-project/chronicle_api').resolves(new Response(JSON.stringify(mockApiResponse)));

    await handleApiRequest();

    const responseEl = document.getElementById('api-response').querySelector('code');
    assert.equal(responseEl.textContent, JSON.stringify(mockApiResponse, null, 2), 'Response element should be populated with formatted JSON');
    assert.ok(fetchStub.calledOnce, 'Fetch should be called once');

    fetchStub.restore();
  });

  QUnit.test('handleApiRequest shows warning if no tenant is selected', async function(assert) {
    document.getElementById('tenant-select').value = "Choose a tenant";
    
    await handleApiRequest();

    assert.ok(window.showToast.calledWith('Please select a tenant.', 'warning'), 'Warning toast should be shown');
  });

  QUnit.test('handleApiRequest handles fetch failure', async function(assert) {
    const fetchStub = sinon.stub(window, 'fetch');
    fetchStub.resolves(new Response(JSON.stringify({ detail: 'API request failed.' }), { status: 400, statusText: 'Bad Request' }));

    await handleApiRequest();

    const responseEl = document.getElementById('api-response').querySelector('code');
    assert.ok(responseEl.textContent.includes('Error: API request failed.'), 'Error message should be displayed in response element');
    assert.ok(window.showToast.calledWith('API request failed.', 'error'), 'Error toast should be shown');

    fetchStub.restore();
  });
});
