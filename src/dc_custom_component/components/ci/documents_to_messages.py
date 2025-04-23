from typing import Dict, List, Any, Optional

from haystack import component, Document, default_from_dict, default_to_dict
from haystack.dataclasses import ChatMessage


@component
class CIDocumentToChatMessageConverter:
    """
    Converts Haystack Documents from CI output to ChatMessages.

    This component is used to transform CI output documents into a format
    suitable for chat-based agents. It creates a structured message that
    summarizes the CI failures and provides details for fixing them.

    ### Usage example
    ```python
    from dc_custom_component.components.ci import CIDocumentToChatMessageConverter
    from haystack import Document

    converter = CIDocumentToChatMessageConverter()
    messages = converter.run(
        documents=[Document(content="Test failed", meta={"type": "test_failure"})]
    )["messages"]
    ```
    """

    def __init__(
        self,
        strip_role_prefix: bool = True,
    ):
        """
        Initialize the component.

        :param strip_role_prefix: If True, strips role prefix like "Human:" from message content
        """
        self.strip_role_prefix = strip_role_prefix

    def to_dict(self) -> Dict[str, Any]:
        """
        Serialize the component to a dictionary.

        :returns: Dictionary with serialized data.
        """
        return default_to_dict(
            self,
            strip_role_prefix=self.strip_role_prefix,
        )

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CIDocumentToChatMessageConverter":
        """
        Deserialize the component from a dictionary.

        :param data: Dictionary to deserialize from.
        :returns: Deserialized component.
        """
        return default_from_dict(cls, data)

    @component.output_types(messages=List[ChatMessage])
    def run(self, documents: List[Document]) -> Dict[str, List[ChatMessage]]:
        """
        Convert list of CI output documents to ChatMessages.

        :param documents: List of Document objects containing CI output
        :return: Dictionary with list of ChatMessage objects
        """
        # Group documents by type
        summary_docs = [doc for doc in documents if doc.meta.get("type") == "ci_summary"]
        test_failure_docs = [doc for doc in documents if doc.meta.get("type") == "test_failure"]
        lint_failure_docs = [doc for doc in documents if doc.meta.get("type") == "lint_failure"]
        error_docs = [doc for doc in documents if doc.meta.get("error", False)]
        
        # Create the message content
        message_content = """# CI Failures Fix Request

The CI pipeline has identified the following issues that need to be fixed:
"""
        
        # Add test failures section if any
        if test_failure_docs:
            message_content += "\n## Test Failures\n\n"
            for doc in test_failure_docs:
                file = doc.meta.get("file", "Unknown file")
                test = doc.meta.get("test", "Unknown test")
                message_content += f"- **{file}::{test}**\n```\n{doc.content}\n```\n\n"
        
        # Add lint failures section if any
        if lint_failure_docs:
            message_content += "\n## Linting Issues\n\n"
            by_tool = {}
            for doc in lint_failure_docs:
                tool = doc.meta.get("tool", "Unknown")
                if tool not in by_tool:
                    by_tool[tool] = []
                by_tool[tool].append(doc)
            
            for tool, docs in by_tool.items():
                message_content += f"### {tool.upper()} Issues\n\n"
                for doc in docs:
                    file = doc.meta.get("file", "Unknown file")
                    line = doc.meta.get("line", "?")
                    code = doc.meta.get("code", "")
                    msg = doc.meta.get("message", "")
                    message_content += f"- **{file}:{line}** {code} {msg}\n```\n{doc.content}\n```\n\n"
        
        # Add error section if any
        if error_docs:
            message_content += "\n## Errors Processing CI Output\n\n"
            for doc in error_docs:
                message_content += f"- {doc.content}\n"
        
        # Add the instructions for the AI
        message_content += "\n## Instructions\n\nPlease fix the issues above by making the necessary code changes. Make sure to:\n\n"
        message_content += "1. Address all failing tests and make them pass\n"
        message_content += "2. Fix all linting and type checking issues\n"
        message_content += "3. Create a pull request with your changes when done\n"
        
        # Convert to chat message
        messages = [ChatMessage.from_user(message_content)]
        
        return {"messages": messages}
