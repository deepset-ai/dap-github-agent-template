# SPDX-FileCopyrightText: 2024-present deepset GmbH <info@deepset.ai>
#
# SPDX-License-Identifier: Apache-2.0

import re
from typing import Dict, List, Union

from haystack import component, logging
from haystack.dataclasses import ChatMessage

logger = logging.getLogger(__name__)


@component
class RegexParser:
    """
    Extracts text from input using a regex pattern.

    RegexParser parses input text or ChatMessages using a provided regular expression pattern.
    It can be configured to search through all messages or only the last message in a list of ChatMessages.

    ### Usage example

    ```python
    from haystack.components.parsers import RegexParser
    from haystack.dataclasses import ChatMessage

    # Using with a string
    parser = RegexParser(regex_pattern='<issue url=\"(.+)\">')
    result = parser.run(text_or_messages='<issue url="github.com/hahahaha">hahahah</issue>')
    # result: {"captured_text": "github.com/hahahaha"}

    # Using with ChatMessages
    messages = [ChatMessage.from_user('<issue url="github.com/hahahaha">hahahah</issue>')]
    result = parser.run(text_or_messages=messages)
    # result: {"captured_text": "github.com/hahahaha"}
    ```
    """

    def __init__(
        self,
        regex_pattern: str,
        consider_all_messages: bool = False,
        return_empty_on_no_match: bool = False,
        return_all_matches: bool = False,
    ):
        """
        Creates an instance of the RegexParser component.

        :param regex_pattern:
            The regular expression pattern used to extract text.
            The pattern should include a capture group to extract the desired text.
            Example: '<issue url=\"(.+)\">' captures 'github.com/hahahaha' from '<issue url="github.com/hahahaha">'.

        :param consider_all_messages:
            If True, the regex is applied to all messages in the list.
            If False (default), only the last message is considered.

        :param return_empty_on_no_match:
            If True, returns an empty dictionary when no match is found.
            If False (default), returns a dictionary with an empty string as the captured_text.

        :param return_all_matches:
            If True, returns a list of all matches in the text as 'captured_texts'.
            If False (default), returns only the first match as 'captured_text'.
        """
        self.regex_pattern = regex_pattern
        self.consider_all_messages = consider_all_messages
        self.return_empty_on_no_match = return_empty_on_no_match
        self.return_all_matches = return_all_matches

        # Check if the pattern has at least one capture group
        num_groups = re.compile(regex_pattern).groups
        if num_groups < 1:
            logger.warning(
                "The provided regex pattern {regex_pattern} doesn't contain any capture groups. "
                "The entire match will be returned instead.",
                regex_pattern=regex_pattern,
            )

    @component.output_types(captured_text=str, captured_texts=List[str])
    def run(self, text_or_messages: Union[str, List[ChatMessage]]) -> Dict:
        """
        Extracts text from input using the configured regex pattern.

        :param text_or_messages:
            Either a string or a list of ChatMessage objects to search through.

        :returns:
            Depending on configuration, returns one of:

            - Single match mode (default, return_all_matches=False):
              - If match found: {"captured_text": "matched text"}
              - If no match and return_empty_on_no_match=False: {"captured_text": ""}
              - If no match and return_empty_on_no_match=True: {}

            - Multiple match mode (return_all_matches=True):
              - If matches found: {"captured_texts": ["match1", "match2", ...]}
              - If no matches and return_empty_on_no_match=False: {"captured_texts": []}
              - If no matches and return_empty_on_no_match=True: {}
        """
        if isinstance(text_or_messages, str):
            result = self._extract_from_text(text_or_messages)

            if self.return_all_matches:
                if not result and self.return_empty_on_no_match:
                    return {}
                return {"captured_texts": result}
            else:
                if not result and self.return_empty_on_no_match:
                    return {}
                return {"captured_text": result}

        if not text_or_messages:
            logger.warning("Received empty list of messages")
            if self.return_empty_on_no_match:
                return {}
            if self.return_all_matches:
                return {"captured_texts": []}
            return {"captured_text": ""}

        if self.consider_all_messages:
            # Try to extract from all messages in the list
            if self.return_all_matches:
                all_matches: List[Union[List[str], str]] = []
                for message in text_or_messages:
                    if not isinstance(message, ChatMessage):
                        raise ValueError(
                            f"Expected ChatMessage object, got {type(message)}"
                        )

                    if message.text is None:
                        continue

                    matches = self._extract_from_text(message.text)
                    all_matches.extend(matches)

                if not all_matches and self.return_empty_on_no_match:
                    return {}
                return {"captured_texts": all_matches}
            else:
                for message in text_or_messages:
                    if not isinstance(message, ChatMessage):
                        raise ValueError(
                            f"Expected ChatMessage object, got {type(message)}"
                        )

                    if message.text is None:
                        continue

                    captured = self._extract_from_text(message.text)
                    if captured:
                        return {"captured_text": captured}

                # No match found in any message
                if self.return_empty_on_no_match:
                    return {}
                return {"captured_text": ""}
        else:
            # Only consider the last message
            last_message = text_or_messages[-1]
            if not isinstance(last_message, ChatMessage):
                raise ValueError(
                    f"Expected ChatMessage object, got {type(last_message)}"
                )

            if last_message.text is None:
                logger.warning("Last message has no text content")
                if self.return_empty_on_no_match:
                    return {}
                if self.return_all_matches:
                    return {"captured_texts": []}
                return {"captured_text": ""}

            result = self._extract_from_text(last_message.text)

            if self.return_all_matches:
                if not result and self.return_empty_on_no_match:
                    return {}
                return {"captured_texts": result}
            else:
                if not result and self.return_empty_on_no_match:
                    return {}
                return {"captured_text": result}

    def _extract_from_text(self, text: str) -> Union[str, List[str]]:
        """
        Extract text using the regex pattern.

        :param text:
            The text to search through.

        :returns:
            If return_all_matches=False:
                The text captured by the first capturing group in the regex pattern.
                If the pattern has no capture groups, returns the entire match.
                If no match is found, returns an empty string.

            If return_all_matches=True:
                A list of all captured texts (empty list if no matches).
        """
        if not self.return_all_matches:
            match = re.search(self.regex_pattern, text)
            if not match:
                return ""

            # If there are capturing groups, return the first one
            if match.groups():
                return match.group(1)

            # If no capturing groups, return the entire match
            return match.group(0)
        else:
            matches = re.finditer(self.regex_pattern, text)
            result = []

            for match in matches:
                if match.groups():
                    result.append(match.group(1))
                else:
                    result.append(match.group(0))

            return result
