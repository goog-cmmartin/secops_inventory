QUnit.module("Tenants", function (hooks) {
  hooks.beforeEach(function () {
    // Mock the fetch function
    this.fetchStub = sinon.stub(window, "fetch");

    // Set up the DOM elements needed for the tests
    document.getElementById(
      "qunit-fixture"
    ).innerHTML = `
      <div id="db-status"></div>
      <select id="tenant-select"></select>
      <select id="audit-tenant-select"></select>
      <select id="insight-tenant-select"></select>
      <select id="report-tenant-filter"></select>
      <table id="tenants-table"></table>
      <div id="myTab" class=""></div>
      <div id="myTabContent" class=""></div>
    `;
  });

  hooks.afterEach(function () {
    // Restore the original fetch function
    this.fetchStub.restore();
  });

  QUnit.test("fetchTenants populates the tenants table", async function (
    assert
  ) {
    // Arrange
    const tenantsResponse = [
      {
        project_name: "Test Project 1",
        project_id: "test-project-1",
        is_configured: true,
      },
      {
        project_name: "Test Project 2",
        project_id: "test-project-2",
        is_configured: false,
      },
    ];

    this.fetchStub.withArgs("/api/tenants").resolves(
      new Response(JSON.stringify(tenantsResponse), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      })
    );
    // Mock other calls made by fetchTenants
    this.fetchStub.resolves(new Response("[]", { status: 200 }));

    // Act
    await fetchTenants();

    // Assert
    const rows = document.querySelectorAll("#tenants-table tr");
    assert.equal(rows.length, 2, "Two rows should be created in the table");

    const firstRow = rows[0];
    assert.ok(
      firstRow.textContent.includes("Test Project 1"),
      "First row contains project name"
    );
    assert.ok(
      firstRow.textContent.includes("test-project-1"),
      "First row contains project ID"
    );
    assert.ok(
      firstRow.innerHTML.includes("Configured"),
      "First row shows 'Configured' status"
    );
    assert.ok(
      firstRow.innerHTML.includes("Test"),
      "First row includes a 'Test' button"
    );

    const secondRow = rows[1];
    assert.ok(
      secondRow.textContent.includes("Test Project 2"),
      "Second row contains project name"
    );
    assert.ok(
      secondRow.innerHTML.includes("Not Configured"),
      "Second row shows 'Not Configured' status"
    );
    assert.notOk(
      secondRow.innerHTML.includes("Test"),
      "Second row does not include a 'Test' button"
    );
  });
});
