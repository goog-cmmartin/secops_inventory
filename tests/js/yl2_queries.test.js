QUnit.module('YL2 Queries', function(hooks) {
  hooks.beforeEach(function() {
    // Mock the showToast function
    window.showToast = sinon.spy();
    window.confirm = () => true; // Always confirm deletion
  });

  QUnit.test('fetchCustomYl2Queries success', async function(assert) {
    const mockQueries = [
      { id: 1, name: 'Test Query', query: 'SELECT * FROM table' }
    ];
    const fetchStub = sinon.stub(window, 'fetch');
    fetchStub.withArgs('/api/yl2_queries').resolves(new Response(JSON.stringify(mockQueries)));

    const table = document.createElement('tbody');
    table.id = 'yl2-queries-table';
    document.getElementById('qunit-fixture').append(table);

    await fetchCustomYl2Queries();

    assert.ok(table.innerHTML.includes('Test Query'), 'Query name should be in the table');
    assert.ok(table.innerHTML.includes('SELECT * FROM table'), 'Query text should be in the table');

    fetchStub.restore();
  });

  QUnit.test('saveYl2Query create', async function(assert) {
    const fetchStub = sinon.stub(window, 'fetch');
    fetchStub.withArgs('/api/yl2_queries').resolves(new Response(null, { status: 200 }));

    const form = document.createElement('form');
    form.innerHTML = `
      <input id="yl2-query-id" value="">
      <input id="yl2-query-name" value="New Query">
      <input id="yl2-query-text" value="SELECT 1">
    `;
    document.getElementById('qunit-fixture').append(form);
    
    // Mock the modal
    window.yl2QueryModal = { hide: sinon.spy() };

    await saveYl2Query();

    assert.ok(window.showToast.calledWith('Query saved successfully!', 'success'), 'Success toast should be shown');
    assert.ok(yl2QueryModal.hide.calledOnce, 'Modal should be hidden');

    fetchStub.restore();
  });

  QUnit.test('deleteYl2Query success', async function(assert) {
    const fetchStub = sinon.stub(window, 'fetch');
    fetchStub.withArgs('/api/yl2_queries/1').resolves(new Response(null, { status: 200 }));
    fetchStub.withArgs('/api/yl2_queries').resolves(new Response(JSON.stringify([]))); // For the refetch

    await deleteYl2Query(1);

    assert.ok(window.showToast.calledWith('Query deleted successfully.', 'success'), 'Success toast should be shown');

    fetchStub.restore();
  });
});
