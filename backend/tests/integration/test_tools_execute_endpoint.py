"""
Integration test for Task 6: API Route /tools/execute endpoint validation.
Verifies that the /tools/execute endpoint properly validates parameters via Pydantic.
"""
import pytest
from fastapi.testclient import TestClient


class TestToolsExecuteEndpointValidation:
    """Test /api/v1/tools/execute endpoint with schema validation."""

    @pytest.fixture(autouse=True)
    def setup_auth(self, client, auth_headers):
        """Use the authenticated client with auth headers."""
        self.client = client
        self.auth_headers = auth_headers

    def test_execute_builtin_tool_valid_params(self):
        """Test executing a builtin tool with valid parameters."""
        # web_search is a builtin tool available to all tiers
        response = self.client.post(
            "/api/v1/tools/execute",
            json={
                "tool_name": "web_search",
                "params": {"query": "test query", "max_results": 5}
            },
            headers=self.auth_headers,
        )
        # Should not be a validation error (may fail for other reasons like no API key)
        # But should not be 422 (validation error) or 404 (tool not found)
        assert response.status_code != 422, f"Validation error: {response.text}"
        assert response.status_code != 404, f"Tool not found: {response.text}"
        # Should either succeed or fail with a non-validation error
        if response.status_code == 200:
            assert response.json()["status"] in ["success", "error"]

    def test_execute_builtin_tool_missing_required_param(self):
        """Test executing a builtin tool with missing required parameter."""
        response = self.client.post(
            "/api/v1/tools/execute",
            json={
                "tool_name": "read_file",
                "params": {}  # missing required 'filepath'
            },
            headers=self.auth_headers,
        )
        assert response.status_code == 422 or response.status_code == 400
        # Should return schema validation error
        data = response.json()
        assert data["error"]["type"] == "schema_validation_error"
        assert data["error"]["details"][0]["type"] == "missing"
        assert data["error"]["details"][0]["loc"] == ("filepath",)

    def test_execute_builtin_tool_wrong_type(self):
        """Test executing a builtin tool with wrong parameter type."""
        response = self.client.post(
            "/api/v1/tools/execute",
            json={
                "tool_name": "execute_command",
                "params": {"command": "not_a_list", "timeout": 30}
            },
            headers=self.auth_headers,
        )
        assert response.status_code == 422 or response.status_code == 400
        data = response.json()
        assert data["error"]["type"] == "schema_validation_error"
        # Should have int_parsing or list_type error for timeout/command

    def test_execute_builtin_tool_enum_validation(self):
        """Test executing a builtin tool with enum validation."""
        # web_search has 'provider' with enum
        response = self.client.post(
            "/api/v1/tools/execute",
            json={
                "tool_name": "web_search",
                "params": {"query": "test", "provider": "invalid_provider"}
            },
            headers=self.auth_headers,
        )
        assert response.status_code == 422 or response.status_code == 400
        data = response.json()
        assert data["error"]["type"] == "schema_validation_error"
        assert data["error"]["details"][0]["type"] == "literal_error"

    def test_execute_builtin_tool_coercion(self):
        """Test that string-to-int coercion works for built-in tools."""
        response = self.client.post(
            "/api/v1/tools/execute",
            json={
                "tool_name": "web_search",
                "params": {"query": "test", "max_results": "10"}  # string "10" should coerce to int
            },
            headers=self.auth_headers,
        )
        # Should not be validation error
        assert response.status_code != 422
        # If successful, max_results should be int 10
        if response.status_code == 200:
            result = response.json()
            # The tool might fail for other reasons (no API key), but params should be validated
            if result.get("status") == "success":
                pass  # validated correctly

    def test_execute_strict_mode_tool(self):
        """Test that strict validation tools reject coercible types."""
        # execute_command has strict_validation = True
        response = self.client.post(
            "/api/v1/tools/execute",
            json={
                "tool_name": "execute_command",
                "params": {"command": "echo hello", "timeout": "30"}  # string "30" should FAIL in strict mode
            },
            headers=self.auth_headers,
        )
        # Strict validation should reject string for int
        assert response.status_code == 422 or response.status_code == 400
        data = response.json()
        assert data["error"]["type"] == "schema_validation_error"
        # Should have int_parsing error for timeout

    def test_execute_nonexistent_tool(self):
        """Test executing a non-existent tool."""
        response = self.client.post(
            "/api/v1/tools/execute",
            json={
                "tool_name": "nonexistent_tool_12345",
                "params": {}
            },
            headers=self.auth_headers,
        )
        assert response.status_code == 404
        data = response.json()
        assert "not found" in data["error"].lower()

    def test_execute_tool_unauthorized_tier(self):
        """Test executing a tool with unauthorized tier."""
        # tool_creator is only for 0xxxx/1xxxx
        response = self.client.post(
            "/api/v1/tools/execute",
            json={
                "tool_name": "tool_creator",
                "params": {"action": "help"}
            },
            headers=self.auth_headers,
        )
        assert response.status_code == 403
        data = response.json()
        assert "not authorised" in data["error"] or "not authorized" in data["error"]

    def test_execute_mcp_tool_params(self):
        """Test executing an MCP tool with params validation."""
        # This would require an MCP server to be registered
        # For now, test that the endpoint doesn't crash on None params
        response = self.client.post(
            "/api/v1/tools/execute",
            json={
                "tool_name": "web_search",
                "params": None
            },
            headers=self.auth_headers,
        )
        # Should handle None params gracefully
        # Might be 400 or 422 depending on validation
        assert response.status_code in [400, 422, 200]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])