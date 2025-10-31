"""
Unit tests for JobManager REST API responses.
"""
from contextlib import contextmanager
import os
import sys

from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from jobmanager.api import app, state, JobStatus


@contextmanager
def api_client():
    """
    Context manager to provide a TestClient with a clean JobManager state.
    """
    # Reset mutable state before each test
    state.jobs.clear()
    state.execution_graphs.clear()
    state.checkpoint_coordinators.clear()
    state.resource_manager.task_managers.clear()

    with TestClient(app) as client:
        yield client

    # Ensure background threads don't leak state between tests
    state.resource_manager.task_managers.clear()
    state.jobs.clear()


def test_list_jobs_returns_array():
    """Ensure /jobs returns an array payload even when empty."""
    with api_client() as client:
        response = client.get("/jobs")
        assert response.status_code == 200
        assert response.json() == []


def test_job_status_response_contains_expected_fields():
    """Verify job status endpoint returns frontend-compatible payload."""
    job_id = "job_test"
    job_info = {
        "job_id": job_id,
        "job_name": "Test Job",
        "status": JobStatus.RUNNING,
        "start_time": 1700000000000,
        "end_time": None,
        "job_graph": None,
        "parallelism": 2,
        "vertices": [
            {
                "vertex_id": "v1",
                "operator_name": "Source",
                "operator_type": "CollectionSourceOperator",
                "parallelism": 1,
            }
        ],
    }

    with api_client() as client:
        # Register job after state reset performed by api_client
        state.jobs[job_id] = job_info

        response = client.get(f"/jobs/{job_id}/status")
        assert response.status_code == 200
        payload = response.json()

        assert payload["job_id"] == job_id
        assert payload["job_name"] == "Test Job"
        assert payload["parallelism"] == 2
        assert isinstance(payload["vertices"], list)
        assert payload["vertices"][0]["vertex_id"] == "v1"


def test_task_manager_listing_matches_frontend_shape():
    """Ensure task manager listing aligns with frontend expectations."""
    with api_client() as client:
        # Register a TaskManager via API state
        state.resource_manager.register_task_manager(
            task_manager_id="tm-test",
            host="localhost",
            port=6123,
            task_slots=4,
        )

        response = client.get("/taskmanagers")
        assert response.status_code == 200
        payload = response.json()

        assert isinstance(payload, list)
        assert len(payload) == 1
        tm_payload = payload[0]

        assert tm_payload["task_manager_id"] == "tm-test"
        assert tm_payload["total_slots"] == 4
        assert tm_payload["available_slots"] == 4
        # last_heartbeat should be an integer timestamp in milliseconds
        assert isinstance(tm_payload["last_heartbeat"], int)
        assert tm_payload["status"] in {"ACTIVE", "LOST", "DISCONNECTED"}
