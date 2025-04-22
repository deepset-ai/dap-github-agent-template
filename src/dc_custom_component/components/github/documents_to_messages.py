import re
from typing import Dict, List, Optional

from haystack import Document, component
from haystack.dataclasses import ChatMessage


@component
class DocumentToChatMessageConverter:
    """
    Converts Haystack Documents into ChatMessages with simple role assignment.

    The component uses a regex pattern to determine if a document's content
    should be converted into an assistant message. If the pattern matches,
    the document becomes an assistant message; otherwise, it becomes a user message.

    ### Usage example
    ```python
    from haystack import Document
    from haystack.dataclasses import ChatMessage

    # Create converter with a regex pattern for assistant messages
    converter = DocumentToChatMessageConverter(
        assistant_pattern=r"^Assistant:"
    )

    # Sample documents
    docs = [
        Document(content="Hello, I have a question"),
        Document(content="Assistant: I'll help you with that.")
    ]

    # Convert documents to chat messages
    result = converter.run(documents=docs)
    messages = result["chat_messages"]

    # Messages will be:
    # - User: "Hello, I have a question"
    # - Assistant: "I'll help you with that."
    ```
    """

    def __init__(
        self, assistant_pattern: Optional[str] = None, strip_role_prefix: bool = False
    ):
        """
        Initialize the component.

        :param assistant_pattern: Regex pattern that if matched will make the document an assistant message
        :param strip_role_prefix: If True, removes role prefixes from content (e.g., "Assistant: ")
        """

        self.assistant_pattern = assistant_pattern and re.compile(assistant_pattern)

        self.strip_role_prefix = strip_role_prefix

    def _clean_content(self, content: str) -> str:
        """
        Clean content by removing role prefixes if strip_role_prefix is enabled.

        :param content: Content string to clean
        :return: Cleaned content string
        """
        if not self.strip_role_prefix:
            return content

        # Find the first match of the pattern
        if isinstance(self.assistant_pattern, re.Pattern):
            match = self.assistant_pattern.search(content)
            if match:
                # Remove the matched prefix part
                return content[match.end() :].lstrip()

        return content

    def _create_chat_message(self, document: Document) -> ChatMessage:
        """
        Create a ChatMessage from a Document.

        :param document: Source Document
        :return: Converted ChatMessage
        """
        content = document.content or ""

        # Check if content matches the assistant pattern
        if self.assistant_pattern and self.assistant_pattern.search(content):
            cleaned_content = self._clean_content(content)
            return ChatMessage.from_assistant(cleaned_content, meta=document.meta)
        else:
            # Default to user role
            return ChatMessage.from_user(content, meta=document.meta)

    @component.output_types(messages=List[ChatMessage])
    def run(self, documents: List[Document]) -> Dict[str, List[ChatMessage]]:
        """
        Convert Documents to ChatMessages.

        :param documents: List of Documents to convert
        :return: Dictionary containing list of ChatMessages
        """
        chat_messages = [self._create_chat_message(doc) for doc in documents]
        return {"messages": chat_messages}
