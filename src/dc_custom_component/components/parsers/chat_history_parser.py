from haystack import component
from haystack.dataclasses import ChatMessage
from typing import List, Dict
import re
import ast


@component
class DeepsetChatHistoryParser:
    """
    Parses a string containing chat history and a current question into a list of ChatMessage objects.

    This component expects input in a specific format where chat history is presented as a JSON array
    after "Chat History: " and the current question follows "Current Question: ". If the input
    doesn't match this format, it will return the entire input as a single user message.

    Usage example:
    ```python
    from haystack.components.parsers import DeepsetChatHistoryParser

    text_input = '''Chat History: [{"role": "user", "content": "Hello"},
                                   {"role": "assistant", "content": "Hi there!"}]
                     Current Question: How are you today?'''

    parser = DeepsetChatHistoryParser()
    result = parser.run(text_input)

    # result contains:
    # {
    #   'messages': [
    #     ChatMessage(role='user', content='Hello'),
    #     ChatMessage(role='assistant', content='Hi there!'),
    #     ChatMessage(role='user', content='How are you today?')
    #   ]
    # }
    ```
    """

    @component.output_types(messages=List[ChatMessage])
    def run(self, history_and_query: str) -> Dict[str, List[ChatMessage]]:
        """
        Parse a string containing chat history and current question into a list of ChatMessage objects.

        The expected format is:
        "Chat History: [{...JSON array of messages...}] Current Question: {question text}"

        Each message in the history should be a dictionary with "role" (either "user" or "assistant")
        and "content" (the message text) keys.

        :param history_and_query:
            String containing chat history and current question in the expected format.

        :returns:
            A dictionary with the following key:
            - `messages`: A list of ChatMessage objects representing the parsed conversation.
                          If parsing fails, contains just the input string as a single user message.
        """
        try:
            # First find the Chat History line
            history_start = history_and_query.find("Chat History: ")
            if history_start == -1:
                return {"messages": [ChatMessage.from_user(history_and_query)]}

            history_start += len("Chat History: ")

            # Find the first [ after "Chat History: "
            array_start = history_and_query.find("[", history_start)
            if array_start == -1:
                return {"messages": [ChatMessage.from_user(history_and_query)]}

            # Now find where this array ends by parsing it as JSON
            # Try progressively longer substrings until we find valid JSON
            for i in range(array_start + 1, len(history_and_query)):
                try:
                    candidate = history_and_query[array_start:i]
                    if candidate.count("[") > 0 and candidate[-1] == "]":
                        # Only try to parse if we have at least one opening and closing bracket
                        ast.literal_eval(candidate)
                        # If we get here, we found valid JSON. But we need to make sure
                        # we got the full outer array, not just a nested valid JSON object
                        if candidate.strip()[-1] == "]":
                            history_json = candidate
                            break
                except (SyntaxError, ValueError):
                    continue
            else:
                # No valid JSON found
                return {"messages": [ChatMessage.from_user(history_and_query)]}

            messages = []
            try:
                chat_history = ast.literal_eval(history_json)
                # Convert each message to ChatMessage
                for msg in chat_history:
                    if msg["role"] == "user":
                        messages.append(ChatMessage.from_user(msg["content"]))
                    elif msg["role"] == "assistant":
                        messages.append(ChatMessage.from_assistant(msg["content"]))
            except (SyntaxError, ValueError, KeyError, TypeError):
                return {"messages": [ChatMessage.from_user(history_and_query)]}

            # Extract current query - everything after "Current question: "
            query_match = re.search(
                r"Current Question: (.*?)$", history_and_query, re.DOTALL
            )
            if query_match:
                current_query = query_match.group(1).strip()
                messages.append(ChatMessage.from_user(current_query))

            if messages:
                return {"messages": messages}

        except Exception:
            pass  # If any error occurs, fall back to the default case

        # Default case: return the entire string as a single user message
        return {"messages": [ChatMessage.from_user(history_and_query)]}
