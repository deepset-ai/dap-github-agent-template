from dc_custom_component.pipelines.github_agent.github_agent import get_agent_pipeline as get_github_agent_pipeline
from dc_custom_component.pipelines.jira_agent.jira_agent import get_agent_pipeline as get_jira_agent_pipeline


github_agent_config = {
    "name": "github-agent-claude",
    "workspace": "default",
    "query": get_github_agent_pipeline(),
}

jira_agent_config = {
    "name": "jira-agent-claude",
    "workspace": "default",
    "query": get_jira_agent_pipeline(),
}

dp_pipelines = [
    github_agent_config,
    jira_agent_config,
]
