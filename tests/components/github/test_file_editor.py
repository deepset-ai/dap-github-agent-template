import json
from base64 import b64encode
from unittest.mock import Mock, patch

import pytest
from requests import RequestException

from dc_custom_component.components.github.file_editor import Command, GithubFileEditor
from haystack.utils import Secret


class TestGithubFileEditor:
    @pytest.fixture
    def mock_responses(self) -> dict:
        """Setup mock responses for API calls"""
        # Mock file content response
        file_content_response = Mock()
        file_content_response.json.return_value = {
            "content": b64encode(b"def old_function():\n    return 'old'").decode("utf-8"),
            "sha": "abc123",
        }
        file_content_response.raise_for_status = Mock()

        # Mock update file response
        update_file_response = Mock()
        update_file_response.raise_for_status = Mock()
        update_file_response.json.return_value = {"commit": {"sha": "def456"}}

        # Mock commits response
        commits_response = Mock()
        commits_response.json.return_value = [
            {"sha": "current_sha", "author": {"login": "current_user"}},
            {"sha": "previous_sha", "author": {"login": "different_user"}},
        ]
        commits_response.raise_for_status = Mock()

        # Mock user response
        user_response = Mock()
        user_response.json.return_value = {"login": "current_user"}
        user_response.raise_for_status = Mock()

        # Mock branch update response
        branch_update_response = Mock()
        branch_update_response.raise_for_status = Mock()

        # Mock create file response
        create_file_response = Mock()
        create_file_response.raise_for_status = Mock()

        # Mock delete file response
        delete_file_response = Mock()
        delete_file_response.raise_for_status = Mock()

        return {
            "file_content": file_content_response,
            "update_file": update_file_response,
            "commits": commits_response,
            "user": user_response,
            "branch_update": branch_update_response,
            "create_file": create_file_response,
            "delete_file": delete_file_response,
        }

    @pytest.fixture
    def editor(self) -> GithubFileEditor:
        """Create a GithubFileEditor instance for testing"""
        return GithubFileEditor(
            github_token=Secret.from_token("dummy_token"),
            repo="owner/repo",
            branch="main",
        )

    def test_init_with_defaults(self) -> None:
        """Test initialization with default values"""
        editor = GithubFileEditor(github_token=Secret.from_token("dummy_token"))
        assert editor.default_repo is None
        assert editor.default_branch == "main"
        assert editor.raise_on_failure is True
        assert editor.headers["Authorization"] == "Bearer dummy_token"

    def test_init_with_custom_values(self) -> None:
        """Test initialization with custom values"""
        editor = GithubFileEditor(
            github_token=Secret.from_token("custom_token"),
            repo="custom/repo",
            branch="develop",
            raise_on_failure=False,
        )
        assert editor.default_repo == "custom/repo"
        assert editor.default_branch == "develop"
        assert editor.raise_on_failure is False
        assert editor.headers["Authorization"] == "Bearer custom_token"

    def test_init_with_invalid_token_type(self) -> None:
        """Test initialization with invalid token type"""
        with pytest.raises(TypeError, match="github_token must be a Secret"):
            GithubFileEditor(github_token="not_a_secret")

    @patch("requests.get")
    def test_get_file_content(self, mock_get, editor, mock_responses):
        """Test retrieving file content from GitHub"""
        mock_get.return_value = mock_responses["file_content"]

        content, sha = editor._get_file_content("owner", "repo", "path/to/file.py", "main")

        assert content == "def old_function():\n    return 'old'"
        assert sha == "abc123"
        mock_get.assert_called_once_with(
            "https://api.github.com/repos/owner/repo/contents/path/to/file.py",
            headers=editor.headers,
            params={"ref": "main"},
        )

    @patch("requests.put")
    def test_update_file(self, mock_put, editor, mock_responses):
        """Test updating file content on GitHub"""
        mock_put.return_value = mock_responses["update_file"]

        result = editor._update_file(
            "owner",
            "repo",
            "path/to/file.py",
            "new content",
            "Update message",
            "abc123",
            "main",
        )

        assert result is True
        mock_put.assert_called_once()
        # Check that the correct URL and headers were used
        args, kwargs = mock_put.call_args
        assert args[0] == "https://api.github.com/repos/owner/repo/contents/path/to/file.py"
        assert kwargs["headers"] == editor.headers
        # Check payload
        payload = kwargs["json"]
        assert payload["message"] == "Update message"
        assert payload["sha"] == "abc123"
        assert payload["branch"] == "main"
        # Verify content is base64 encoded
        assert payload["content"] == b64encode(b"new content").decode("utf-8")

    @patch("requests.get")
    def test_check_last_commit_same_user(self, mock_get, editor, mock_responses):
        """Test checking if last commit was made by current user (success case)"""
        # Setup mocks to return responses in the correct order
        mock_get.side_effect = [mock_responses["commits"], mock_responses["user"]]

        result = editor._check_last_commit("owner", "repo", "main")

        assert result is True
        assert mock_get.call_count == 2
        # Check first call for commits
        args1, kwargs1 = mock_get.call_args_list[0]
        assert args1[0] == "https://api.github.com/repos/owner/repo/commits"
        assert kwargs1["params"] == {"per_page": 1, "sha": "main"}
        # Check second call for user
        args2, kwargs2 = mock_get.call_args_list[1]
        assert args2[0] == "https://api.github.com/user"

    @patch("requests.get")
    def test_check_last_commit_different_user(self, mock_get, editor, mock_responses):
        """Test checking if last commit was made by different user"""
        # First response for commits
        commits_response = Mock()
        commits_response.json.return_value = [
            {"author": {"login": "different_user"}, "sha": "abc123"}
        ]
        commits_response.raise_for_status = Mock()

        # Second response for user
        user_response = Mock()
        user_response.json.return_value = {"login": "current_user"}
        user_response.raise_for_status = Mock()

        mock_get.side_effect = [commits_response, user_response]

        result = editor._check_last_commit("owner", "repo", "main")

        assert result is False
        assert mock_get.call_count == 2

    @patch("dc_custom_component.components.github.file_editor.GithubFileEditor._get_file_content")
    @patch("dc_custom_component.components.github.file_editor.GithubFileEditor._update_file")
    def test_edit_file_success(self, mock_update, mock_get_content, editor):
        """Test successful file editing"""
        # Setup mocks
        mock_get_content.return_value = ("def old_function():\n    return 'old'", "abc123")
        mock_update.return_value = True

        payload = {
            "path": "path/to/file.py",
            "original": "def old_function():\n    return 'old'",
            "replacement": "def new_function():\n    return 'new'",
            "message": "Updated function",
        }

        result = editor._edit_file("owner", "repo", payload, "main")

        assert result == "Edit successful"
        mock_get_content.assert_called_once_with("owner", "repo", "path/to/file.py", "main")
        mock_update.assert_called_once_with(
            "owner",
            "repo",
            "path/to/file.py",
            "def new_function():\n    return 'new'",
            "Updated function",
            "abc123",
            "main",
        )

    @patch("dc_custom_component.components.github.file_editor.GithubFileEditor._get_file_content")
    def test_edit_file_original_not_found(self, mock_get_content, editor):
        """Test file editing when original content is not found"""
        mock_get_content.return_value = ("def different_function():\n    pass", "abc123")

        payload = {
            "path": "path/to/file.py",
            "original": "def old_function():\n    return 'old'",
            "replacement": "def new_function():\n    return 'new'",
            "message": "Updated function",
        }

        result = editor._edit_file("owner", "repo", payload, "main")

        assert result == "Error: Original string not found in file"
        mock_get_content.assert_called_once()

    @patch("dc_custom_component.components.github.file_editor.GithubFileEditor._get_file_content")
    def test_edit_file_multiple_occurrences(self, mock_get_content, editor):
        """Test file editing when original content appears multiple times"""
        content = "def old_function():\n    return 'old'\n\ndef something_else():\n    pass\n\ndef old_function():\n    return 'old'"
        mock_get_content.return_value = (content, "abc123")

        payload = {
            "path": "path/to/file.py",
            "original": "def old_function():\n    return 'old'",
            "replacement": "def new_function():\n    return 'new'",
            "message": "Updated function",
        }

        result = editor._edit_file("owner", "repo", payload, "main")

        assert result == "Error: Original string appears multiple times. Please provide more context"
        mock_get_content.assert_called_once()

    @patch("dc_custom_component.components.github.file_editor.GithubFileEditor._get_file_content")
    @patch("requests.put")
    def test_edit_file_request_exception(self, mock_put, mock_get_content, editor):
        """Test file editing with request exception"""
        mock_get_content.return_value = ("def old_function():\n    return 'old'", "abc123")
        mock_put.side_effect = RequestException("API error")

        payload = {
            "path": "path/to/file.py",
            "original": "def old_function():\n    return 'old'",
            "replacement": "def new_function():\n    return 'new'",
            "message": "Updated function",
        }

        # Test with raise_on_failure = True
        editor.raise_on_failure = True
        with pytest.raises(RequestException):
            editor._edit_file("owner", "repo", payload, "main")

        # Test with raise_on_failure = False
        editor.raise_on_failure = False
        result = editor._edit_file("owner", "repo", payload, "main")
        assert result == "Error: API error"

    @patch("dc_custom_component.components.github.file_editor.GithubFileEditor._check_last_commit")
    @patch("requests.get")
    @patch("requests.patch")
    def test_undo_changes_success(self, mock_patch, mock_get, mock_check_commit, editor, mock_responses):
        """Test successful undoing of changes"""
        mock_check_commit.return_value = True
        mock_get.return_value = mock_responses["commits"]
        mock_patch.return_value = mock_responses["branch_update"]

        payload = {"message": "Undo last change"}

        result = editor._undo_changes("owner", "repo", payload, "main")

        assert result == "Successfully undid last change"
        mock_check_commit.assert_called_once_with("owner", "repo", "main")
        mock_get.assert_called_once()
        mock_patch.assert_called_once()
        # Verify patch call args
        args, kwargs = mock_patch.call_args
        assert args[0] == "https://api.github.com/repos/owner/repo/git/refs/heads/main"
        assert kwargs["headers"] == editor.headers
        assert kwargs["json"]["sha"] == "previous_sha"
        assert kwargs["json"]["force"] is True

    @patch("dc_custom_component.components.github.file_editor.GithubFileEditor._check_last_commit")
    def test_undo_changes_not_same_user(self, mock_check_commit, editor):
        """Test undo when last commit was not from same user"""
        mock_check_commit.return_value = False

        payload = {"message": "Undo last change"}

        result = editor._undo_changes("owner", "repo", payload, "main")

        assert result == "Error: Last commit was not made by the current user"
        mock_check_commit.assert_called_once()

    @patch("dc_custom_component.components.github.file_editor.GithubFileEditor._check_last_commit")
    @patch("requests.get")
    def test_undo_changes_request_exception(self, mock_get, mock_check_commit, editor):
        """Test undo with request exception"""
        mock_check_commit.return_value = True
        mock_get.side_effect = RequestException("API error")

        payload = {"message": "Undo last change"}

        # Test with raise_on_failure = True
        editor.raise_on_failure = True
        with pytest.raises(RequestException):
            editor._undo_changes("owner", "repo", payload, "main")

        # Test with raise_on_failure = False
        editor.raise_on_failure = False
        result = editor._undo_changes("owner", "repo", payload, "main")
        assert result == "Error: API error"

    @patch("requests.put")
    def test_create_file_success(self, mock_put, editor, mock_responses):
        """Test successful file creation"""
        mock_put.return_value = mock_responses["create_file"]

        payload = {
            "path": "path/to/new_file.py",
            "content": "def new_function():\n    return 'new'",
            "message": "Add new file",
        }

        result = editor._create_file("owner", "repo", payload, "main")

        assert result == "File created successfully"
        mock_put.assert_called_once()
        # Verify put call args
        args, kwargs = mock_put.call_args
        assert args[0] == "https://api.github.com/repos/owner/repo/contents/path/to/new_file.py"
        assert kwargs["headers"] == editor.headers
        assert kwargs["json"]["message"] == "Add new file"
        assert kwargs["json"]["branch"] == "main"
        # Verify content is base64 encoded
        expected_content = b64encode(b"def new_function():\n    return 'new'").decode("utf-8")
        assert kwargs["json"]["content"] == expected_content

    @patch("requests.put")
    def test_create_file_request_exception(self, mock_put, editor):
        """Test file creation with request exception"""
        mock_put.side_effect = RequestException("API error")

        payload = {
            "path": "path/to/new_file.py",
            "content": "def new_function():\n    return 'new'",
            "message": "Add new file",
        }

        # Test with raise_on_failure = True
        editor.raise_on_failure = True
        with pytest.raises(RequestException):
            editor._create_file("owner", "repo", payload, "main")

        # Test with raise_on_failure = False
        editor.raise_on_failure = False
        result = editor._create_file("owner", "repo", payload, "main")
        assert result == "Error: API error"

    @patch("dc_custom_component.components.github.file_editor.GithubFileEditor._get_file_content")
    @patch("requests.delete")
    def test_delete_file_success(self, mock_delete, mock_get_content, editor, mock_responses):
        """Test successful file deletion"""
        mock_get_content.return_value = ("file content", "abc123")
        mock_delete.return_value = mock_responses["delete_file"]

        payload = {"path": "path/to/file.py", "message": "Delete file"}

        result = editor._delete_file("owner", "repo", payload, "main")

        assert result == "File deleted successfully"
        mock_get_content.assert_called_once_with("owner", "repo", "path/to/file.py", "main")
        mock_delete.assert_called_once()
        # Verify delete call args
        args, kwargs = mock_delete.call_args
        assert args[0] == "https://api.github.com/repos/owner/repo/contents/path/to/file.py"
        assert kwargs["headers"] == editor.headers
        assert kwargs["json"]["message"] == "Delete file"
        assert kwargs["json"]["sha"] == "abc123"
        assert kwargs["json"]["branch"] == "main"

    @patch("dc_custom_component.components.github.file_editor.GithubFileEditor._get_file_content")
    @patch("requests.delete")
    def test_delete_file_request_exception(self, mock_delete, mock_get_content, editor):
        """Test file deletion with request exception"""
        mock_get_content.return_value = ("file content", "abc123")
        mock_delete.side_effect = RequestException("API error")

        payload = {"path": "path/to/file.py", "message": "Delete file"}

        # Test with raise_on_failure = True
        editor.raise_on_failure = True
        with pytest.raises(RequestException):
            editor._delete_file("owner", "repo", payload, "main")

        # Test with raise_on_failure = False
        editor.raise_on_failure = False
        result = editor._delete_file("owner", "repo", payload, "main")
        assert result == "Error: API error"

    @patch("dc_custom_component.components.github.file_editor.GithubFileEditor._edit_file")
    def test_run_edit_command(self, mock_edit, editor):
        """Test run method with edit command"""
        mock_edit.return_value = "Edit successful"

        payload = {
            "path": "path/to/file.py",
            "original": "def old_function():",
            "replacement": "def new_function():",
            "message": "Updated function",
        }

        # Test with Command enum
        result = editor.run(Command.EDIT, payload)
        assert result["result"] == "Edit successful"
        mock_edit.assert_called_once_with("owner", "repo", payload, "main")

        # Test with string command
        mock_edit.reset_mock()
        result = editor.run("edit", payload)
        assert result["result"] == "Edit successful"
        mock_edit.assert_called_once_with("owner", "repo", payload, "main")

    @patch("dc_custom_component.components.github.file_editor.GithubFileEditor._undo_changes")
    def test_run_undo_command(self, mock_undo, editor):
        """Test run method with undo command"""
        mock_undo.return_value = "Successfully undid last change"

        payload = {"message": "Undo last change"}

        result = editor.run(Command.UNDO, payload)
        assert result["result"] == "Successfully undid last change"
        mock_undo.assert_called_once_with("owner", "repo", payload, "main")

    @patch("dc_custom_component.components.github.file_editor.GithubFileEditor._create_file")
    def test_run_create_command(self, mock_create, editor):
        """Test run method with create command"""
        mock_create.return_value = "File created successfully"

        payload = {
            "path": "path/to/new_file.py",
            "content": "def new_function():\n    return 'new'",
            "message": "Add new file",
        }

        result = editor.run(Command.CREATE, payload)
        assert result["result"] == "File created successfully"
        mock_create.assert_called_once_with("owner", "repo", payload, "main")

    @patch("dc_custom_component.components.github.file_editor.GithubFileEditor._delete_file")
    def test_run_delete_command(self, mock_delete, editor):
        """Test run method with delete command"""
        mock_delete.return_value = "File deleted successfully"

        payload = {"path": "path/to/file.py", "message": "Delete file"}

        result = editor.run(Command.DELETE, payload)
        assert result["result"] == "File deleted successfully"
        mock_delete.assert_called_once_with("owner", "repo", payload, "main")

    def test_run_unknown_command(self, editor):
        """Test run method with unknown command"""
        result = editor.run("unknown", {})
        assert "Error: Unknown command" in result["result"]

    def test_run_no_repo_specified(self, editor):
        """Test run method with no repository specified"""
        editor.default_repo = None
        result = editor.run(Command.EDIT, {})
        assert "Error: No repository specified" in result["result"]

    def test_run_with_custom_repo_branch(self, editor):
        """Test run method with custom repo and branch"""
        with patch.object(editor, "_edit_file", return_value="Edit successful") as mock_edit:
            payload = {
                "path": "path/to/file.py",
                "original": "old",
                "replacement": "new",
                "message": "Updated content",
            }
            result = editor.run(
                Command.EDIT, payload, repo="custom/repo", branch="feature"
            )
            assert result["result"] == "Edit successful"
            mock_edit.assert_called_once_with("custom", "repo", payload, "feature")

    def test_to_dict(self, editor):
        """Test serialization to dictionary"""
        # Mock the to_dict method on the Secret object to prevent serialization error
        with patch.object(Secret, 'to_dict', return_value={'type': 'env', 'value': 'GITHUB_TOKEN'}):
            data = editor.to_dict()
            assert "init_parameters" in data
            assert data["init_parameters"]["repo"] == "owner/repo"
            assert data["init_parameters"]["branch"] == "main"
            assert data["init_parameters"]["raise_on_failure"] is True
            assert "github_token" in data["init_parameters"]

    def test_from_dict(self):
        """Test deserialization from dictionary"""
        data = {
            "type": "dc_custom_component.components.github.file_editor.GithubFileEditor",
            "init_parameters": {
                "repo": "owner/repo",
                "branch": "main",
                "raise_on_failure": True,
            }
        }
            
        editor = GithubFileEditor.from_dict(data)
        assert editor.default_repo == "owner/repo"
        assert editor.default_branch == "main"
        assert editor.raise_on_failure is True
