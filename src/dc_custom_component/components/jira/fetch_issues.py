from typing import Any, Optional


from haystack import (
    SuperComponent,
    component,
    Pipeline,
    default_from_dict,
    default_to_dict,
)
from haystack.utils import Secret, deserialize_secrets_inplace

from dc_custom_component.components.jira.jira_issue_viewer import JiraIssueViewer
from dc_custom_component.components.github.documents_to_messages import (
    DocumentToChatMessageConverter,
)
from dc_custom_component.components.github.branch_creator import GithubBranchCreator


@component
class FetchJiraIssue(SuperComponent):
    def __init__(
        self,
        jira_token: Secret = Secret.from_env_var("JIRA_API_TOKEN", strict=False),
        jira_email: Secret = Secret.from_env_var("JIRA_EMAIL", strict=False),
        jira_base_url: Optional[str] = None,
        github_token: Secret = Secret.from_env_var("GITHUB_TOKEN", strict=False),
        assistant_pattern: Optional[str] = None,
        strip_role_prefix: bool = True,
    ):
        self.jira_token = jira_token
        self.jira_email = jira_email
        self.jira_base_url = jira_base_url
        self.github_token = github_token
        self.assistant_pattern = assistant_pattern
        self.strip_role_prefix = strip_role_prefix

        fetcher = JiraIssueViewer(
            jira_token=self.jira_token,
            jira_email=self.jira_email,
            jira_base_url=self.jira_base_url
        )
        converter = DocumentToChatMessageConverter(
            assistant_pattern=self.assistant_pattern,
            strip_role_prefix=self.strip_role_prefix,
        )
        creator = GithubBranchCreator(
            github_token=self.github_token, fail_if_exists=False
        )

        pp = Pipeline()
        pp.add_component("branch_creator", creator)
        pp.add_component("fetcher", fetcher)
        pp.add_component("converter", converter)

        pp.connect("fetcher.documents", "converter.documents")

        super(FetchJiraIssue, self).__init__(
            pipeline=pp,
            output_mapping={
                "branch_creator.branch_name": "branch",
                "converter.messages": "messages",
            },
        )

    def to_dict(self) -> dict[str, Any]:
        """
        Serialize the component to a dictionary.

        :returns: Dictionary with serialized data.
        """
        return default_to_dict(
            self,
            jira_token=self.jira_token.to_dict() if self.jira_token else None,
            jira_email=self.jira_email.to_dict() if self.jira_email else None,
            jira_base_url=self.jira_base_url,
            github_token=self.github_token.to_dict() if self.github_token else None,
            assistant_pattern=self.assistant_pattern,
            strip_role_prefix=self.strip_role_prefix,
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FetchJiraIssue":
        """
        Deserialize the component from a dictionary.

        :param data: Dictionary to deserialize from.
        :returns: Deserialized component.
        """
        init_params = data["init_parameters"]
        deserialize_secrets_inplace(init_params, keys=["jira_token", "jira_email", "github_token"])
        return default_from_dict(cls, data)
