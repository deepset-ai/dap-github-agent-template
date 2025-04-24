import re
from typing import Any, Dict, List, Optional

import requests
from haystack import Document, component, default_from_dict, default_to_dict, logging
from haystack.utils import deserialize_secrets_inplace
from haystack.utils.auth import Secret

logger = logging.getLogger(__name__)


@component
class JiraIssueViewer:
    """
    Fetches and parses Jira issues into Haystack documents.

    The component takes a Jira issue URL and returns a list of documents where:
    - First document contains the main issue content
    - Subsequent documents contain the issue comments

    ### Usage example
    ```python
    from dc_custom_component.components.jira import JiraIssueViewer

    viewer = JiraIssueViewer(jira_token=Secret.from_env_var("JIRA_API_TOKEN"), jira_email=Secret.from_token("user@example.com"))
    docs = viewer.run(
        url="https://your-domain.atlassian.net/browse/PROJECT-123"
    )["documents"]

    assert len(docs) >= 1  # At least the main issue
    assert docs[0].meta["type"] == "issue"
    ```
    """

    def __init__(
        self,
        jira_token: Optional[Secret] = None,
        jira_email: Optional[Secret] = None,
        jira_base_url: Optional[str] = None,
        raise_on_failure: bool = True,
        retry_attempts: int = 2,
    ):
        """
        Initialize the component.

        :param jira_token: Jira API token for authentication as a Secret
        :param jira_email: Jira account email for authentication as a Secret
        :param jira_base_url: Base URL for Jira API (optional, extracted from issue URL if not provided)
        :param raise_on_failure: If True, raises exceptions on API errors
        :param retry_attempts: Number of retry attempts for failed requests
        """
        self.jira_token = jira_token
        self.jira_email = jira_email
        self.jira_base_url = jira_base_url
        self.raise_on_failure = raise_on_failure
        self.retry_attempts = retry_attempts

        # Only set the basic headers during initialization
        self.headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def _get_request_auth(self) -> Optional[tuple]:
        """
        Get authentication tuple for the request.

        :return: Tuple of (email, token) if credentials are provided, None otherwise
        """
        if self.jira_email and self.jira_token:
            return (self.jira_email.resolve_value(), self.jira_token.resolve_value())
        return None

    def _parse_jira_url(self, url: str) -> tuple[str, str]:
        """
        Parse Jira URL into base URL and issue key.

        :param url: Jira issue URL
        :return: Tuple of (base_url, issue_key)
        :raises ValueError: If URL format is invalid
        """
        # Pattern for Jira Cloud URL: https://your-domain.atlassian.net/browse/PROJECT-123
        pattern = r"https?://([^/]+)/browse/([^/]+)"
        match = re.match(pattern, url)
        if not match:
            raise ValueError(f"Invalid Jira issue URL format: {url}")

        domain, issue_key = match.groups()
        base_url = f"https://{domain}"
        
        return base_url, issue_key

    def _fetch_issue(self, base_url: str, issue_key: str) -> Any:
        """
        Fetch issue data from Jira API.

        :param base_url: Jira instance base URL
        :param issue_key: Issue key (e.g., PROJECT-123)
        :return: Issue data dictionary
        """
        url = f"{base_url}/rest/api/3/issue/{issue_key}"
        response = requests.get(url, auth=self._get_request_auth(), headers=self.headers)
        response.raise_for_status()
        return response.json()

    def _fetch_comments(self, base_url: str, issue_key: str) -> Any:
        """
        Fetch issue comments from Jira API.

        :param base_url: Jira instance base URL
        :param issue_key: Issue key (e.g., PROJECT-123)
        :return: List of comment dictionaries
        """
        url = f"{base_url}/rest/api/3/issue/{issue_key}/comment"
        response = requests.get(url, auth=self._get_request_auth(), headers=self.headers)
        response.raise_for_status()
        return response.json().get("comments", [])

    def _extract_text_from_jira_content(self, content_obj: Any) -> str:
        """
        Extract plain text from Jira's Atlassian Document Format (ADF).
        
        This is a simplified extractor that tries to get text content from
        Jira's complex document format.
        
        :param content_obj: The content object from Jira API
        :return: Extracted plain text
        """
        if not content_obj or "content" not in content_obj:
            return ""
            
        text_parts = []
        
        def extract_text(node):
            if isinstance(node, dict):
                if node.get("type") == "text" and "text" in node:
                    text_parts.append(node["text"])
                    
                # Handle paragraphs, headings, lists, etc.
                if "content" in node and isinstance(node["content"], list):
                    for item in node["content"]:
                        extract_text(item)
            elif isinstance(node, list):
                for item in node:
                    extract_text(item)
        
        extract_text(content_obj)
        return "\n".join(text_parts)

    def _create_issue_document(self, issue_data: dict, base_url: str) -> Document:
        """
        Create a Document from issue data.

        :param issue_data: Issue data from Jira API
        :param base_url: Jira instance base URL
        :return: Haystack Document
        """
        # Extract description - handle both string and ADF formats
        description = issue_data.get("fields", {}).get("description", "")
        if isinstance(description, dict):
            description = self._extract_text_from_jira_content(description)
            
        issue_key = issue_data.get("key")
        issue_fields = issue_data.get("fields", {})
        
        return Document(
            content=description,
            meta={
                "type": "issue",
                "key": issue_key,
                "title": issue_fields.get("summary", ""),
                "status": issue_fields.get("status", {}).get("name", ""),
                "created_at": issue_fields.get("created", ""),
                "updated_at": issue_fields.get("updated", ""),
                "author": issue_fields.get("reporter", {}).get("displayName", ""),
                "assignee": issue_fields.get("assignee", {}).get("displayName", ""),
                "url": f"{base_url}/browse/{issue_key}",
            },
        )

    def _create_comment_document(
        self, comment_data: dict, issue_key: str, base_url: str
    ) -> Document:
        """
        Create a Document from comment data.

        :param comment_data: Comment data from Jira API
        :param issue_key: Parent issue key
        :param base_url: Jira instance base URL
        :return: Haystack Document
        """
        # Extract body - handle both string and ADF formats
        body = comment_data.get("body", "")
        if isinstance(body, dict):
            body = self._extract_text_from_jira_content(body)
            
        return Document(
            content=body,
            meta={
                "type": "comment",
                "issue_key": issue_key,
                "created_at": comment_data.get("created", ""),
                "updated_at": comment_data.get("updated", ""),
                "author": comment_data.get("author", {}).get("displayName", ""),
                "url": f"{base_url}/browse/{issue_key}?focusedCommentId={comment_data.get('id', '')}",
            },
        )

    def to_dict(self) -> Dict[str, Any]:
        """
        Serialize the component to a dictionary.

        :returns: Dictionary with serialized data.
        """
        return default_to_dict(
            self,
            jira_token=self.jira_token.to_dict() if self.jira_token else None,
            jira_email=self.jira_email.to_dict() if self.jira_email else None,
            jira_base_url=self.jira_base_url,
            raise_on_failure=self.raise_on_failure,
            retry_attempts=self.retry_attempts,
        )

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "JiraIssueViewer":
        """
        Deserialize the component from a dictionary.

        :param data: Dictionary to deserialize from.
        :returns: Deserialized component.
        """
        init_params = data["init_parameters"]
        deserialize_secrets_inplace(init_params, keys=["jira_token", "jira_email"])
        return default_from_dict(cls, data)

    @component.output_types(documents=List[Document])
    def run(self, url: str) -> dict:
        """
        Process a Jira issue URL and return documents.

        :param url: Jira issue URL
        :return: Dictionary containing list of documents
        """
        try:
            # Extract base URL and issue key from URL
            base_url, issue_key = self._parse_jira_url(url)
            
            # Use provided base URL if available
            base_url = self.jira_base_url or base_url

            # Fetch issue data
            issue_data = self._fetch_issue(base_url, issue_key)
            documents = [self._create_issue_document(issue_data, base_url)]

            # Fetch and process comments
            comments = self._fetch_comments(base_url, issue_key)
            documents.extend(
                self._create_comment_document(comment, issue_key, base_url)
                for comment in comments
            )

            return {"documents": documents}

        except Exception as e:
            if self.raise_on_failure:
                raise

            error_message = f"Error processing Jira issue {url}: {str(e)}"
            logger.warning(error_message)
            error_doc = Document(
                content=error_message,
                meta={
                    "error": True,
                    "type": "error",
                    "url": url,
                },
            )
            return {"documents": [error_doc]}
