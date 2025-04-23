from dc_custom_component.pipelines.github_agent.github_agent import get_agent_pipeline as get_github_agent_pipeline
from dc_custom_component.pipelines.ci_agent.ci_agent import get_agent_pipeline as get_ci_agent_pipeline


github_agent_config = {
    "name": "github-agent-claude",
    "workspace": "default",
    "query": get_github_agent_pipeline(),
}

ci_agent_config = {
    "name": "ci-agent-claude",
    "workspace": "default",
    "query": get_ci_agent_pipeline(),
}

dp_pipelines = [
    github_agent_config,
    ci_agent_config,
]
