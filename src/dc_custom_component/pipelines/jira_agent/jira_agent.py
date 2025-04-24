from haystack import Pipeline

from haystack.components.agents import Agent
from haystack.components.builders import AnswerBuilder
from haystack.components.converters import OutputAdapter
from haystack.tools import ComponentTool
from haystack.utils import Secret

from haystack_integrations.components.generators.anthropic.chat.chat_generator import (
    AnthropicChatGenerator,
)

from dc_custom_component.components.jira.fetch_issues import FetchJiraIssue
from dc_custom_component.components.github.read_contents import GithubContentViewer
from dc_custom_component.components.github.file_editor import GithubFileEditor
from dc_custom_component.components.github.pr_creator import GitHubPRCreator

from dc_custom_component.pipelines.github_agent.system_prompt import system_prompt


def get_agent_pipeline() -> Pipeline:
    view_repo_tool = ComponentTool(
        component=GithubContentViewer(raise_on_failure=False),
        name="view_repository",
        description="Use to explore the contents of the repository.",
        parameters={
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "The path to the directory or file to view (empty string for root)",
                }
            },
            "required": ["path"],
        },
    )

    file_editor_tool = ComponentTool(
        component=GithubFileEditor(raise_on_failure=False),
        name="file_editor",
        description="Use the file editor to edit an existing file in the repository.",
        parameters={
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The action to perform. One of: 'edit', 'create', 'delete', or 'undo'",
                    "enum": ["edit", "create", "delete", "undo"],
                },
                "payload": {
                    "type": "object",
                    "description": "The details for the command",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "The full path to the file (required for edit, create, and delete commands)",
                        },
                        "original": {
                            "type": "string",
                            "description": "The exact text to replace (minimum 2 consecutive lines; required for edit command)",
                        },
                        "replacement": {
                            "type": "string",
                            "description": "The new text to insert (required for edit command)",
                        },
                        "content": {
                            "type": "string",
                            "description": "The content of the file (required for create command)",
                        },
                        "message": {
                            "type": "string",
                            "description": "A descriptive commit message using conventional commit style (required for all commands)",
                        },
                    },
                    "required": ["message"],
                },
            },
            "required": ["command", "payload"],
        },
    )

    create_pr_tool = ComponentTool(
        component=GitHubPRCreator(),
        name="create_pr",
        description="Creates a pull request with your changes after you've completed your implementation.",
        inputs_from_state={
            "branch": "head_branch",
            "repo": "repo",
            "issue_url": "issue_url",
        },
        parameters={
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "A concise, descriptive title for the pull request following conventional commit style",
                },
                "body": {
                    "type": "string",
                    "description": "A detailed description of the changes made, explaining the approach and implementation details",
                },
            },
            "required": ["title", "body"],
        },
    )

    chat_generator = AnthropicChatGenerator(
        model="claude-3-7-sonnet-latest",
        generation_kwargs={"max_tokens": 8000},
        api_key=Secret.from_env_var("ANTHROPIC_API_KEY", strict=False),
    )
    agent = Agent(
        chat_generator=chat_generator,
        tools=[view_repo_tool, file_editor_tool, create_pr_tool],
        system_prompt=system_prompt,
        exit_conditions=["text", "create_pr"],
        state_schema={
            "branch": {"type": str},
            "repo": {"type": str},
            "issue_url": {"type": str},
        },
    )

    issue_fetcher = FetchJiraIssue(
        assistant_pattern="@agent-message", strip_role_prefix=True
    )

    adapter = OutputAdapter(
        template="{{['successfully finished in ' ~ messages|length ~ ' steps']}}",
        output_type=list[str],
    )

    builder = AnswerBuilder()

    pp = Pipeline(
        metadata={
            "inputs": {
                "query": ["builder.query", "issue_fetcher.url", "agent.issue_url"],
            },
            "outputs": {"answers": "builder.answers"},
        }
    )

    pp.add_component("agent", agent)
    pp.add_component("issue_fetcher", issue_fetcher)
    pp.add_component("adapter", adapter)
    pp.add_component("builder", builder)

    pp.connect("issue_fetcher.messages", "agent.messages")
    pp.connect("issue_fetcher.branch", "agent.branch")
    pp.connect("agent.messages", "adapter.messages")
    pp.connect("adapter.output", "builder.replies")

    return pp