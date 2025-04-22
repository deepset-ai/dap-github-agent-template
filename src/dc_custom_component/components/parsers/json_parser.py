from typing import Dict, Any, List
import json
import re
import logging

from haystack import component

logger = logging.getLogger(__name__)


@component
class JsonParser:
    """
    A Haystack component that extracts and parses JSON from text input.
    Handles JSON both with and without markdown code blocks.

    Example:
        ```python
        from haystack import Pipeline

        pipe = Pipeline()
        pipe.add_component("json_parser", JsonParser())

        # Parse plain JSON
        result = pipe.run(data={"text": '{"name": "John", "age": 30}'})
        parsed = result["parsed_json"]

        # Parse JSON in markdown
        result = pipe.run(data={"text": '```json\\n{"name": "John"}\\n```'})
        parsed = result["parsed_json"]
        ```
    """

    @component.output_types(parsed_json=dict[str, Any])
    def run(self, text: str) -> Dict[str, Any]:
        """
        Extract and parse JSON from input text.

        Args:
            text: Input string that may contain JSON

        Returns:
            Dictionary with 'parsed_json' key containing the parsed JSON object
            or empty dict if no valid JSON found
        """
        # Try to find JSON within markdown code blocks
        logger.warning(f"Type is: {type(text)}.")
        if isinstance(text, dict):
            return {"parsed_json": text}

        code_block_pattern = r"```(?:json)?\n(.*?)\n```"
        code_block_match = re.search(code_block_pattern, text, re.DOTALL)

        if code_block_match:
            try:
                return {"parsed_json": json.loads(code_block_match.group(1).strip())}
            except json.JSONDecodeError:
                pass

        # Try to find JSON between curly braces
        json_candidates = self.find_matching_braces(text)

        for candidate in json_candidates:
            try:
                return {"parsed_json": json.loads(candidate)}
            except json.JSONDecodeError:
                continue

        # Try to parse the entire string as JSON
        try:
            return {"parsed_json": json.loads(text.strip())}
        except json.JSONDecodeError:
            logger.warning("Could not parse JSON from text: %s", text)
            return {"parsed_json": {}}

    @staticmethod
    def find_matching_braces(text: str) -> List[str]:
        """
        Finds all matching pairs of curly braces in the input text, handling nested structures.

        :param text: The input text to search for matching brace pairs.
        :return: A list of strings, each containing a complete matched brace structure.

        Example:
            >>> text = "outer{inner{nested}}other{simple}"
            >>> JsonParser.find_matching_braces(text)
            ['outer{inner{nested}}', 'other{simple}']
        """
        results = []
        stack: List[str] = []
        start = -1

        for i, char in enumerate(text):
            if char == "{":
                if not stack:
                    start = i
                stack.append(char)
            elif char == "}":
                if stack:
                    stack.pop()
                    if not stack:  # We've found a complete matching pair
                        results.append(text[start : i + 1])

        return results
