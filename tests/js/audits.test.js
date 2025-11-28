QUnit.module('Audits', function(hooks) {
  hooks.beforeEach(function() {
    window.showToast = sinon.spy();
    window.tenantData = [{ project_id: 'test-project', project_name: 'Test Project', is_configured: true }];
    window.configurableAuditModal = { show: sinon.spy() };
  });

  QUnit.test('fetchConfigurableAudits success', async function(assert) {
    const mockAudits = [
      { id: 1, name: 'Test Audit', category: 'Test', audit_type_icon: 'code', audit_type_name: 'API' }
    ];
    const fetchStub = sinon.stub(window, 'fetch');
    fetchStub.withArgs('/api/configurable_audits').resolves(new Response(JSON.stringify(mockAudits)));

    const table = document.createElement('tbody');
    table.id = 'configurable-audits-table';
    document.getElementById('qunit-fixture').append(table);

    await fetchConfigurableAudits();

    assert.ok(table.innerHTML.includes('Test Audit'), 'Audit name should be in the table');
    assert.ok(table.innerHTML.includes('Test'), 'Audit category should be in the table');

    fetchStub.restore();
  });
});
