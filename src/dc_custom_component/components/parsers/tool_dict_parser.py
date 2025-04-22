from typing import Any


def parse_tool_input(**kwargs: Any) -> dict[str, Any]:
    """parses the kwargs to a dictionary."""
    return {**kwargs}
