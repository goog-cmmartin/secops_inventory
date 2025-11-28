# Error Analysis and Fix for Audit Execution

## Summary of the Error

The application crashes with a `500 Internal Server Error` when running an audit from the UI, and the Celery worker fails to generate reports. This is due to a conflict between the `synchronous` context of the Celery worker and the `asynchronous` context of the FastAPI web server when they both try to use the same core function.

The specific error, `RuntimeError: asyncio.run() cannot be called from a running event loop`, happens because the code attempts to use `asyncio.run()` to execute an async task from within the FastAPI endpoint. This is not allowed, as FastAPI is already managing an active `async` event loop.

## The Comprehensive Fix

The correct solution is to make the shared code (`_run_audit_logic`) fully `async`-aware and then have each caller use the appropriate method to run it.

1.  **Make `_run_audit_logic` fully asynchronous:**
    *   Change its definition in `main.py` from `def _run_audit_logic(...)` to `async def _run_audit_logic(...)`.
    *   Inside this function, change the call from `asyncio.run(list_available_audits())` to `await list_available_audits()`.

2.  **Update the FastAPI Endpoint:**
    *   The `run_audit` endpoint in `main.py` is already `async`, so it must `await` the call to the newly-async `_run_audit_logic`. The line should be `return await _run_audit_logic(project_id, request)`.

3.  **Update the Celery Worker:**
    *   The `run_scheduled_report` task in `celery_worker.py` is synchronous. It must now use `asyncio.run()` to call the `async` `_run_audit_logic` function. The call should be `asyncio.run(_run_audit_logic(project_id, {"audit_name": audit_name}))`.

This ensures that the shared logic is consistently `async`, and each environment (FastAPI and Celery) calls it in the way it expects, resolving all conflicts.
