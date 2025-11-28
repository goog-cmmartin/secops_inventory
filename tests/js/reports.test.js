QUnit.module('Reports Tab', function(hooks) {
  // Store the original fetch function
  let originalFetch;

  hooks.beforeEach(function() {
    // Replace the global fetch with a mock function before each test
    originalFetch = window.fetch;
  });

  hooks.afterEach(function() {
    // Restore the original fetch function after each test
    window.fetch = originalFetch;
  });

  QUnit.test('fetchReports function populates the table', async function(assert) {
    // Arrange
    const mockReports = [
      { id: 1, report_name: 'Test Report 1', project_name: 'Project A', generation_timestamp: new Date().toISOString() },
      { id: 2, report_name: 'Test Report 2', project_name: 'Project B', generation_timestamp: new Date().toISOString() }
    ];

    // Mock the fetch call to return our fake data
    window.fetch = async function(url) {
      return new Response(JSON.stringify(mockReports), {
        status: 200,
        headers: { 'Content-Type': 'application/json' }
      });
    };

    // Set up the necessary HTML structure in the fixture
    const fixture = document.getElementById('qunit-fixture');
    fixture.innerHTML = `
      <select id="report-tenant-filter"></select>
      <table id="reports-table"></table>
    `;

    // Act
    await fetchReports();

    // Assert
    const tableRows = fixture.querySelectorAll('#reports-table tr');
    assert.equal(tableRows.length, 2, 'Table should have 2 rows after fetching reports.');

    const firstRowContent = tableRows[0].textContent;
    assert.ok(firstRowContent.includes('Test Report 1'), 'First row contains the name of the first report.');
    assert.ok(firstRowContent.includes('Project A'), 'First row contains the project name of the first report.');
  });
});
