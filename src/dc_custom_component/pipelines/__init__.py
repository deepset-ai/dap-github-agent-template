from dc_custom_component.pipelines.hn_deep_research.query_gpt4o import (
    query_pipeline as gpt4o_query_pipeline,
)
from dc_custom_component.pipelines.hn_deep_research.query_anthropic import (
    query_pipeline as anthropic_query_pipeline,
)
from dc_custom_component.pipelines.github_issue_resolver.issue_resolver import (
    query_pipeline as issue_resolver_pipeline,
)
from dc_custom_component.pipelines.webinar_agent.webinar_agent import get_agent_pipeline


hn_gpt_config = {
    "name": "deep-research-hackernews-GPT-4o",
    "workspace": "agents",
    "query": gpt4o_query_pipeline,
}

hn_anthropic_config = {
    "name": "deep-research-hackernews-Sonnet-37",
    "workspace": "agents",
    "query": anthropic_query_pipeline,
}

issue_resolver_config = {
    "name": "github-issue-resolver",
    "workspace": "agents",
    "query": issue_resolver_pipeline,
}

webinar_config = {
    "name": "react-github-bot",
    "workspace": "agents",
    "query": get_agent_pipeline(),
}

dp_pipelines = [
    hn_gpt_config,
    hn_anthropic_config,
    issue_resolver_config,
    webinar_config,
]
