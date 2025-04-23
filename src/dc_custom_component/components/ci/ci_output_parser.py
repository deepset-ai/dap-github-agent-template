import re
from typing import Any, Dict, List, Optional

from haystack import Document, component, default_from_dict, default_to_dict, logging
from haystack.utils import Secret

logger = logging.getLogger(__name__)


@component
class CIOutputParser:
    """
    Parses CI output into Haystack documents.

    The component takes CI run output text and returns a list of documents where:
    - First document contains general CI info and summary
    - Other documents contain specific failure details (tests, linting, etc.)

    ### Usage example
    ```python
    from dc_custom_component.components.ci import CIOutputParser

    parser = CIOutputParser()
    docs = parser.run(
        ci_output="Test failed: test_example.py::test_function\nSyntaxError in file.py line 10"
    )["documents"]
    ```
    """

    def __init__(
        self,
        raise_on_failure: bool = True,
    ):
        """
        Initialize the component.

        :param raise_on_failure: If True, raises exceptions on parsing errors
        """
        self.raise_on_failure = raise_on_failure

    def _create_summary_document(self, ci_output: str) -> Document:
        """
        Create a Document with the CI summary.

        :param ci_output: Full CI output
        :return: Haystack Document with summary
        """
        return Document(
            content=ci_output,
            meta={
                "type": "ci_summary",
                "title": "CI Run Output",
            },
        )

    def _parse_test_failures(self, ci_output: str) -> List[Document]:
        """
        Parse test failure information from CI output.

        :param ci_output: Full CI output
        :return: List of Documents with test failures
        """
        documents = []
        
        # Simple pattern to detect pytest failures
        # This can be expanded to be more sophisticated based on your CI output format
        test_failure_pattern = r"(FAILED|ERROR) (.+?)::(.+?)\s"
        for match in re.finditer(test_failure_pattern, ci_output, re.MULTILINE):
            result, file, test = match.groups()
            
            # Find the context of this failure (get a few lines after the match)
            start_pos = match.start()
            end_pos = ci_output.find('\n\n', start_pos)
            if end_pos == -1:
                end_pos = len(ci_output)
            context = ci_output[start_pos:end_pos].strip()
            
            documents.append(
                Document(
                    content=context,
                    meta={
                        "type": "test_failure",
                        "file": file,
                        "test": test,
                        "result": result,
                    },
                )
            )
        
        return documents

    def _parse_lint_failures(self, ci_output: str) -> List[Document]:
        """
        Parse linting failure information from CI output.

        :param ci_output: Full CI output
        :return: List of Documents with linting failures
        """
        documents = []
        
        # Simple pattern for ruff errors
        ruff_pattern = r"(.+?):([0-9]+):[0-9]+: ([A-Z][0-9]+) (.+)"
        
        # Find a block of ruff output
        ruff_blocks = re.findall(r"(ruff.+?\n(?:.+?\n)+?)[\n]{2,}", ci_output, re.DOTALL | re.IGNORECASE)
        
        for block in ruff_blocks:
            for match in re.finditer(ruff_pattern, block, re.MULTILINE):
                file, line, code, message = match.groups()
                documents.append(
                    Document(
                        content=match.group(0),
                        meta={
                            "type": "lint_failure",
                            "tool": "ruff",
                            "file": file,
                            "line": int(line),
                            "code": code,
                            "message": message,
                        },
                    )
                )
        
        # Find mypy errors
        mypy_pattern = r"(.+?):([0-9]+): error: (.+)"
        mypy_blocks = re.findall(r"(mypy.+?\n(?:.+?\n)+?)[\n]{2,}", ci_output, re.DOTALL | re.IGNORECASE)
        
        for block in mypy_blocks:
            for match in re.finditer(mypy_pattern, block, re.MULTILINE):
                file, line, message = match.groups()
                documents.append(
                    Document(
                        content=match.group(0),
                        meta={
                            "type": "lint_failure",
                            "tool": "mypy",
                            "file": file,
                            "line": int(line),
                            "message": message,
                        },
                    )
                )
        
        return documents

    def to_dict(self) -> Dict[str, Any]:
        """
        Serialize the component to a dictionary.

        :returns: Dictionary with serialized data.
        """
        return default_to_dict(
            self,
            raise_on_failure=self.raise_on_failure,
        )

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CIOutputParser":
        """
        Deserialize the component from a dictionary.

        :param data: Dictionary to deserialize from.
        :returns: Deserialized component.
        """
        return default_from_dict(cls, data)

    @component.output_types(documents=List[Document], repo=str)
    def run(self, ci_output: str, repo: str) -> dict:
        """
        Process CI output and return documents.

        :param ci_output: CI run output text
        :param repo: Repository name in format "owner/repo"
        :return: Dictionary containing list of documents and repo info
        """
        try:
            documents = [self._create_summary_document(ci_output)]
            
            # Parse test failures
            documents.extend(self._parse_test_failures(ci_output))
            
            # Parse linting failures
            documents.extend(self._parse_lint_failures(ci_output))
            
            return {"documents": documents, "repo": repo}

        except Exception as e:
            if self.raise_on_failure:
                raise

            error_message = f"Error processing CI output: {str(e)}"
            logger.warning(error_message)
            error_doc = Document(
                content=error_message,
                meta={
                    "error": True,
                    "type": "error",
                },
            )
            return {"documents": [error_doc], "repo": repo}
