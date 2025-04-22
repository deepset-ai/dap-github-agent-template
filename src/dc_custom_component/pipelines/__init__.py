from dc_custom_component.pipelines.github_agent.github_agent import get_agent_pipeline


github_agent_config = {
    "name": "github-agent-claude",
    "workspace": "default",
    "query": get_agent_pipeline(),
}

dp_pipelines = [
    github_agent_config,
]
