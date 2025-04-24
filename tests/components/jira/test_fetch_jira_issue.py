from unittest.mock import MagicMock, patch

import pytest
from haystack import Pipeline
from haystack.dataclasses import ChatMessage
from haystack.utils import Secret

from dc_custom_component.components.jira import FetchJiraIssue
from dc_custom_component.components.jira.jira_issue_viewer import JiraIssueViewer
from dc_custom_component.components.github.documents_to_messages import DocumentToChatMessageConverter
from dc_custom_component.components.github.branch_creator import GithubBranchCreator


@pytest.fixture
def mock_components():
    # Create mocks for the individual components
    mock_jira_viewer = MagicMock()
    mock_converter = MagicMock()
    mock_branch_creator = MagicMock()
    
    # Configure the mocks
    documents = [MagicMock(), MagicMock()]  # Mock documents
    messages = [ChatMessage.from_user("Test message")]  # Sample messages
    
    mock_jira_viewer.run.return_value = {"documents": documents}
    mock_converter.run.return_value = {"messages": messages}
    mock_branch_creator.run.return_value = {"branch_name": "test-branch"}
    
    return {
        "jira_viewer": mock_jira_viewer,
        "converter": mock_converter,
        "branch_creator": mock_branch_creator,
        "expected_documents": documents,
        "expected_messages": messages
    }


@patch("dc_custom_component.components.jira.fetch_issues.JiraIssueViewer")
@patch("dc_custom_component.components.jira.fetch_issues.DocumentToChatMessageConverter")
@patch("dc_custom_component.components.jira.fetch_issues.GithubBranchCreator")
@patch("dc_custom_component.components.jira.fetch_issues.Pipeline")
def test_fetch_jira_issue_init(mock_pipeline_class, mock_branch_creator_class, 
                              mock_converter_class, mock_jira_viewer_class):
    # Setup mocks
    mock_pipeline = MagicMock()
    mock_pipeline_class.return_value = mock_pipeline
    
    # Create the component
    fetcher = FetchJiraIssue(
        jira_token=Secret.from_token("test-jira-token"),
        jira_email=Secret.from_token("test@example.com"),
        jira_base_url="https://test.atlassian.net",
        github_token=Secret.from_token("test-github-token"),
        assistant_pattern="test-pattern",
        strip_role_prefix=True
    )
    
    # Assertions
    assert mock_jira_viewer_class.called
    jira_viewer_call = mock_jira_viewer_class.call_args[1]
    assert jira_viewer_call["jira_token"].resolve_value() == "test-jira-token"
    assert jira_viewer_call["jira_email"].resolve_value() == "test@example.com"
    assert jira_viewer_call["jira_base_url"] == "https://test.atlassian.net"
    
    assert mock_converter_class.called
    converter_call = mock_converter_class.call_args[1]
    assert converter_call["assistant_pattern"] == "test-pattern"
    assert converter_call["strip_role_prefix"] is True
    
    assert mock_branch_creator_class.called
    branch_creator_call = mock_branch_creator_class.call_args[1]
    assert branch_creator_call["github_token"].resolve_value() == "test-github-token"
    assert branch_creator_call["fail_if_exists"] is False
    
    # Check pipeline setup
    assert mock_pipeline.add_component.call_count == 3
    assert mock_pipeline.connect.called


def test_fetch_jira_issue_run(mock_components):
    # Create a real Pipeline with mocked components
    pp = Pipeline()
    
    pp.add_component("branch_creator", mock_components["branch_creator"])
    pp.add_component("fetcher", mock_components["jira_viewer"])
    pp.add_component("converter", mock_components["converter"])
    
    pp.connect("fetcher.documents", "converter.documents")
    
    # Create FetchJiraIssue instance with our pipeline
    fetcher = FetchJiraIssue()
    fetcher._wrapped_pipeline = pp
    
    # Run the component
    result = fetcher.run(url="https://test.atlassian.net/browse/TEST-123")
    
    # Check results
    assert "branch" in result
    assert "messages" in result
    assert result["branch"] == "test-branch"
    assert result["messages"] == mock_components["expected_messages"]
    
    # Verify component calls
    mock_components["jira_viewer"].run.assert_called_once()
    mock_components["converter"].run.assert_called_once_with(
        documents=mock_components["expected_documents"]
    )


def test_fetch_jira_issue_serialization():
    # Test serialization/deserialization
    original = FetchJiraIssue(
        jira_token=Secret.from_token("test-jira-token"),
        jira_email=Secret.from_token("test@example.com"),
        jira_base_url="https://test.atlassian.net",
        github_token=Secret.from_token("test-github-token"),
        assistant_pattern="test-pattern",
        strip_role_prefix=True
    )
    
    # Convert to dict and back
    serialized = original.to_dict()
    deserialized = FetchJiraIssue.from_dict(serialized)
    
    # Check that attributes are preserved
    assert deserialized.jira_token.resolve_value() == "test-jira-token"
    assert deserialized.jira_email.resolve_value() == "test@example.com"
    assert deserialized.jira_base_url == "https://test.atlassian.net"
    assert deserialized.github_token.resolve_value() == "test-github-token"
    assert deserialized.assistant_pattern == "test-pattern"
    assert deserialized.strip_role_prefix is True