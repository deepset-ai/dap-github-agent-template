import json
from unittest.mock import MagicMock, patch

import pytest
import responses
from haystack.dataclasses import Document
from haystack.utils import Secret

from dc_custom_component.components.jira import JiraIssueViewer


@pytest.fixture
def jira_issue_data():
    # Sample Jira issue data in API format
    return {
        "id": "10000",
        "key": "TEST-123", 
        "fields": {
            "summary": "Test issue",
            "description": {
                "type": "doc",
                "version": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "content": [
                            {
                                "type": "text",
                                "text": "This is a test issue description."
                            }
                        ]
                    }
                ]
            },
            "status": {"name": "Open"},
            "created": "2023-01-01T12:00:00.000Z",
            "updated": "2023-01-02T12:00:00.000Z",
            "reporter": {"displayName": "Test User"},
            "assignee": {"displayName": "Assigned User"}
        }
    }


@pytest.fixture
def jira_comments_data():
    # Sample Jira comments data in API format
    return {
        "comments": [
            {
                "id": "1001",
                "body": {
                    "type": "doc",
                    "version": 1,
                    "content": [
                        {
                            "type": "paragraph",
                            "content": [
                                {
                                    "type": "text",
                                    "text": "This is a comment."
                                }
                            ]
                        }
                    ]
                },
                "author": {"displayName": "Comment Author"},
                "created": "2023-01-03T12:00:00.000Z",
                "updated": "2023-01-03T12:00:00.000Z"
            }
        ]
    }


@responses.activate
def test_jira_issue_viewer_run(jira_issue_data, jira_comments_data):
    # Setup mocked responses
    jira_domain = "test-domain.atlassian.net"
    issue_key = "TEST-123"
    
    # Mock the issue API endpoint
    responses.add(
        responses.GET,
        f"https://{jira_domain}/rest/api/3/issue/{issue_key}",
        json=jira_issue_data,
        status=200
    )
    
    # Mock the comments API endpoint
    responses.add(
        responses.GET,
        f"https://{jira_domain}/rest/api/3/issue/{issue_key}/comment",
        json=jira_comments_data,
        status=200
    )
    
    # Create the component
    viewer = JiraIssueViewer(
        jira_token=Secret.from_token("test-token"),
        jira_email=Secret.from_token("test@example.com")
    )
    
    # Call the component
    result = viewer.run(url=f"https://{jira_domain}/browse/{issue_key}")
    
    # Assertions
    assert "documents" in result
    documents = result["documents"]
    assert len(documents) == 2
    
    # Check issue document
    issue_doc = documents[0]
    assert issue_doc.content == "This is a test issue description."
    assert issue_doc.meta["type"] == "issue"
    assert issue_doc.meta["key"] == "TEST-123"
    assert issue_doc.meta["title"] == "Test issue"
    
    # Check comment document
    comment_doc = documents[1]
    assert comment_doc.content == "This is a comment."
    assert comment_doc.meta["type"] == "comment"
    assert comment_doc.meta["issue_key"] == "TEST-123"
    assert comment_doc.meta["author"] == "Comment Author"


def test_parse_jira_url():
    viewer = JiraIssueViewer()
    base_url, issue_key = viewer._parse_jira_url("https://test-domain.atlassian.net/browse/TEST-123")
    
    assert base_url == "https://test-domain.atlassian.net"
    assert issue_key == "TEST-123"
    
    # Test invalid URL
    with pytest.raises(ValueError):
        viewer._parse_jira_url("https://invalid-url.com/wrong-format")


@responses.activate
def test_error_handling():
    # Setup a failing response
    jira_domain = "test-domain.atlassian.net"
    issue_key = "TEST-123"
    
    responses.add(
        responses.GET,
        f"https://{jira_domain}/rest/api/3/issue/{issue_key}",
        json={"error": "Not found"},
        status=404
    )
    
    # Test with raise_on_failure=False
    viewer = JiraIssueViewer(raise_on_failure=False)
    result = viewer.run(url=f"https://{jira_domain}/browse/{issue_key}")
    
    assert "documents" in result
    assert len(result["documents"]) == 1
    assert result["documents"][0].meta["error"] is True
    
    # Test with raise_on_failure=True
    viewer = JiraIssueViewer(raise_on_failure=True)
    with pytest.raises(Exception):
        viewer.run(url=f"https://{jira_domain}/browse/{issue_key}")


def test_extract_text_from_jira_content():
    viewer = JiraIssueViewer()
    
    # Test with complex ADF content
    adf_content = {
        "type": "doc",
        "version": 1,
        "content": [
            {
                "type": "paragraph",
                "content": [
                    {"type": "text", "text": "Line 1"}
                ]
            },
            {
                "type": "paragraph",
                "content": [
                    {"type": "text", "text": "Line 2"}
                ]
            }
        ]
    }
    
    extracted_text = viewer._extract_text_from_jira_content(adf_content)
    assert "Line 1\nLine 2" == extracted_text
    
    # Test with empty content
    assert viewer._extract_text_from_jira_content({}) == ""
    assert viewer._extract_text_from_jira_content(None) == ""
