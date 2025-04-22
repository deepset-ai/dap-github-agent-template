from typing import Any, Optional


from haystack import (
    SuperComponent,
    component,
    Pipeline,
    default_from_dict,
    default_to_dict,
)
from haystack.utils import Secret, deserialize_secrets_inplace

from dc_custom_component.components.github.issue_viewer import GithubIssueViewer
from dc_custom_component.components.github.documents_to_messages import (
    DocumentToChatMessageConverter,
)
from dc_custom_component.components.github.branch_creator import GithubBranchCreator


@component
class FetchIssue(SuperComponent):
    def __init__(
        self,
        github_token: Secret = Secret.from_env_var("GITHUB_TOKEN", strict=False),
        assistant_pattern: Optional[str] = None,
        strip_role_prefix: bool = True,
    ):
        self.github_token = github_token
        self.assistant_pattern = assistant_pattern
        self.strip_role_prefix = strip_role_prefix

        fetcher = GithubIssueViewer(github_token=self.github_token)
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

        super(FetchIssue, self).__init__(
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
        return default_to_dict(  # type: ignore
            self,
            github_token=self.github_token.to_dict(),
            assistant_pattern=self.assistant_pattern,
            strip_role_prefix=self.strip_role_prefix,
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FetchIssue":
        """
        Deserialize the component from a dictionary.

        :param data: Dictionary to deserialize from.
        :returns: Deserialized component.
        """
        init_params = data["init_parameters"]
        deserialize_secrets_inplace(init_params, keys=["github_token"])
        return default_from_dict(cls, data)  # type: ignore


# url > fetch issue / create branch > branch, messages > Agent > messages, branch > create PR
