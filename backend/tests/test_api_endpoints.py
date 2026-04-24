"""
Tests for the FastAPI endpoints in app.py.

Covers:
  POST /api/query  — request/response shape, session handling, error propagation
  GET  /api/courses — analytics response shape, error propagation

The root path (/) is a StaticFiles mount and is not tested here.

All infrastructure (RAGSystem, StaticFiles) is mocked via the `api_client`
fixture in conftest.py so no real ChromaDB or Anthropic calls are made.
"""

import pytest


# ---------------------------------------------------------------------------
# POST /api/query
# ---------------------------------------------------------------------------

class TestQueryEndpoint:

    def test_successful_query_returns_200(self, api_client):
        client, _ = api_client
        resp = client.post("/api/query", json={"query": "What is Python?"})
        assert resp.status_code == 200

    def test_response_body_has_required_fields(self, api_client):
        client, _ = api_client
        resp = client.post("/api/query", json={"query": "test"})
        body = resp.json()
        assert "answer" in body
        assert "sources" in body
        assert "session_id" in body

    def test_answer_matches_rag_system_output(self, api_client):
        client, mock_rag = api_client
        mock_rag.query.return_value = ("Python is a language.", [])
        resp = client.post("/api/query", json={"query": "What is Python?"})
        assert resp.json()["answer"] == "Python is a language."

    def test_sources_list_passed_through_from_rag_system(self, api_client):
        client, mock_rag = api_client
        mock_rag.query.return_value = ("Answer.", ["Course A - Lesson 1"])
        resp = client.post("/api/query", json={"query": "test"})
        assert resp.json()["sources"] == ["Course A - Lesson 1"]

    def test_empty_sources_list_is_valid(self, api_client):
        client, mock_rag = api_client
        mock_rag.query.return_value = ("Answer.", [])
        resp = client.post("/api/query", json={"query": "test"})
        assert resp.json()["sources"] == []

    # --- session handling ---

    def test_auto_creates_session_when_none_provided(self, api_client):
        client, mock_rag = api_client
        mock_rag.session_manager.create_session.return_value = "session_auto"
        resp = client.post("/api/query", json={"query": "test"})
        mock_rag.session_manager.create_session.assert_called_once()
        assert resp.json()["session_id"] == "session_auto"

    def test_uses_provided_session_id_without_creating_new_one(self, api_client):
        client, mock_rag = api_client
        resp = client.post(
            "/api/query",
            json={"query": "test", "session_id": "session_42"},
        )
        mock_rag.session_manager.create_session.assert_not_called()
        assert resp.json()["session_id"] == "session_42"

    def test_provided_session_id_forwarded_to_rag_query(self, api_client):
        client, mock_rag = api_client
        client.post("/api/query", json={"query": "test", "session_id": "sess_7"})
        _, call_session_id = mock_rag.query.call_args[0]
        assert call_session_id == "sess_7"

    def test_query_text_forwarded_to_rag_system(self, api_client):
        client, mock_rag = api_client
        client.post("/api/query", json={"query": "What is ML?"})
        forwarded_query = mock_rag.query.call_args[0][0]
        assert "What is ML?" in forwarded_query

    # --- error handling ---

    def test_rag_exception_returns_500(self, api_client):
        client, mock_rag = api_client
        mock_rag.query.side_effect = Exception("ChromaDB unavailable")
        resp = client.post("/api/query", json={"query": "test"})
        assert resp.status_code == 500

    def test_rag_exception_message_in_response_detail(self, api_client):
        client, mock_rag = api_client
        mock_rag.query.side_effect = Exception("ChromaDB unavailable")
        resp = client.post("/api/query", json={"query": "test"})
        assert "ChromaDB unavailable" in resp.json()["detail"]

    def test_session_create_exception_returns_500(self, api_client):
        client, mock_rag = api_client
        mock_rag.session_manager.create_session.side_effect = Exception("session store full")
        resp = client.post("/api/query", json={"query": "test"})
        assert resp.status_code == 500

    # --- request validation ---

    def test_missing_query_field_returns_422(self, api_client):
        client, _ = api_client
        resp = client.post("/api/query", json={"session_id": "s1"})
        assert resp.status_code == 422

    def test_empty_body_returns_422(self, api_client):
        client, _ = api_client
        resp = client.post("/api/query", json={})
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# GET /api/courses
# ---------------------------------------------------------------------------

class TestCoursesEndpoint:

    def test_successful_request_returns_200(self, api_client):
        client, _ = api_client
        resp = client.get("/api/courses")
        assert resp.status_code == 200

    def test_response_body_has_required_fields(self, api_client):
        client, _ = api_client
        resp = client.get("/api/courses")
        body = resp.json()
        assert "total_courses" in body
        assert "course_titles" in body

    def test_total_courses_matches_analytics_output(self, api_client):
        client, mock_rag = api_client
        mock_rag.get_course_analytics.return_value = {
            "total_courses": 3,
            "course_titles": ["A", "B", "C"],
        }
        resp = client.get("/api/courses")
        assert resp.json()["total_courses"] == 3

    def test_course_titles_match_analytics_output(self, api_client):
        client, mock_rag = api_client
        mock_rag.get_course_analytics.return_value = {
            "total_courses": 2,
            "course_titles": ["Python Basics", "ML Intro"],
        }
        resp = client.get("/api/courses")
        assert resp.json()["course_titles"] == ["Python Basics", "ML Intro"]

    def test_empty_catalog_returns_zero_total(self, api_client):
        client, mock_rag = api_client
        mock_rag.get_course_analytics.return_value = {
            "total_courses": 0,
            "course_titles": [],
        }
        resp = client.get("/api/courses")
        data = resp.json()
        assert data["total_courses"] == 0
        assert data["course_titles"] == []

    def test_analytics_exception_returns_500(self, api_client):
        client, mock_rag = api_client
        mock_rag.get_course_analytics.side_effect = Exception("DB connection lost")
        resp = client.get("/api/courses")
        assert resp.status_code == 500

    def test_analytics_exception_message_in_response_detail(self, api_client):
        client, mock_rag = api_client
        mock_rag.get_course_analytics.side_effect = Exception("DB connection lost")
        resp = client.get("/api/courses")
        assert "DB connection lost" in resp.json()["detail"]
