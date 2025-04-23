# deepset Github Agent
_Template repository showcasing an Agent that can work with GitHub repositories and runs on the deepset AI platform_

## What can I use this for?

The deepset GitHub Agent can independently write code to resolve GitHub issues and create a PR so that a human can
review the changes before they are merged into the main branch.

The Agent can perform the following actions:
- it is triggered by a GitHub actions workflow and receives a GitHub issue as an input
- it extracts the issue body and all issue comments from the issue that triggered it
- it explores directories and files in the repository to build up relevant complex that is needed to resolve the issue
- it creates a feature branch for the issue
- it creates, updates or deletes files as needed to resolve the issue
- it commits any changes to the feature branch that it created
- it creates a PR upon completion that describes the changes made

This repository also allows developers to manage custom components and pipelines for the [deepset AI platform](https://www.deepset.ai/products-and-services/deepset-ai-platform)
directly from GitHub.

Using this template, you can:
- create custom components and push them to the deepset AI platform
- create pipelines in Python; auto-serialize for deployment
- create or update pipelines on the deepset AI platform

Benefits:
- one code base as the single-source of truth for all of your deepset AI platform artifacts
- work in the comfort and speed of your local IDE; deploy to deepset's production-grade infrastructure via GitHub
- versioning for your pipelines and custom components
- roll-back changes to your pipelines through git-based workflows


## Setup

### 1. Create a new repository from this template

<img src="https://docs.github.com/assets/cb-76823/mw-1440/images/help/repository/use-this-template-button.webp" width="350">

See detailed documentation for [creating repositories from a template](https://docs.github.com/en/repositories/creating-and-managing-repositories/creating-a-repository-from-a-template).

### 2. Configure your repository

1. Go to the deepset AI platform and [create an API-key](https://docs.cloud.deepset.ai/docs/generate-api-key).
2. Add the API-key as a secret named `DP_API_KEY` [to your repository](https://docs.github.com/en/actions/security-for-github-actions/security-guides/using-secrets-in-github-actions).
(To add a secret, go to your repository and choose _Settings > Secrets and variables > Actions > New repository secret_.)
3. Enable workflows for your repository by going to _Actions > Enable workflows_.
4. (Optional) Adjust the workflow files in `.github/workflows/` as needed.


### 3. Install dependencies (locally on your machine)

_requires Python>=3.11_

```bash
git clone <your-repository>
cd <your-repository>
pip install hatch
```

Create a virtual environment

```bash
hatch shell
```

This installs all the necessary packages. You can reference this virtual environment in your IDE.

For more information on `hatch`, please refer to the [official Hatch documentation](https://hatch.pypa.io/).


## Getting Started

### Creating Pipelines

Go to `src/pipelines` to view some example pipelines.
To make your own pipeline:
- create and checkout a new branch
- create a new directory under `src/dc_custom_component/pipelines`

We recommend to use the pipeline name as the name of the directory.

Create your pipelines just as you would create any normal Haystack pipelines.
The only addition is that you need to add an `inputs` and `outputs` key to the pipeline's metadata.
This is because the deepset AI platform needs to map API inputs and outputs to your pipeline.

```python
from haystack import Pipeline
from haystack.components.generators.openai import OpenAIGenerator
from haystack.components.builders import PromptBuilder, AnswerBuilder
from haystack.utils import Secret

from haystack_integrations.document_stores.opensearch import OpenSearchDocumentStore
from haystack_integrations.components.retrievers.opensearch.bm25_retriever import (
    OpenSearchBM25Retriever,
)


def get_pipeline() -> Pipeline:
    retriever = OpenSearchBM25Retriever(document_store=OpenSearchDocumentStore())
    builder_template = """
{% for doc in documents %}
{{ doc.content }}
{% endfor %}

Answer the question based on the documents.

Question: {{query}}
    """
    builder = PromptBuilder(template=builder_template)
    llm = OpenAIGenerator(api_key=Secret.from_env_var(["OPENAI_API_KEY"], strict=False))
    answer_builder = AnswerBuilder()

    pp = Pipeline(
        metadata={
            "inputs": {
                "query": [
                    "retriever.query",
                    "builder.query",
                    "answer_builder.query",
                ],
                "filters": ["retriever.filters"],
            },
            "outputs": {"answers": "answer_builder.answers"},
        }
    )

    pp.add_component("retriever", retriever)
    pp.add_component("builder", builder)
    pp.add_component("llm", llm)
    pp.add_component("answer_builder", answer_builder)

    pp.connect("retriever.documents", "builder.documents")
    pp.connect("builder.prompt", "llm.prompt")
    pp.connect("llm.replies", "answer_builder.replies")

    return pp


query_pipeline = get_pipeline()

```


To prepare your pipeline for upload to the deepset AI platform, you have to add it to `pipelines/__init__.py`.

```python
from dc_custom_component.pipelines.hn_deep_research.query_gpt4o import query_pipeline
from dc_custom_component.pipelines.hn_deep_research.indexing import indexing_pipeline

simple_rag = {
    "name": "simple-rag-v2",
    "workspace": "test-workspace",
    "query": query_pipeline,
    "indexing": indexing_pipeline,
}

# Any pipeline configuration added to this list will be uploaded to the deepset AI platform
dp_pipelines = [simple_rag]
```

Each pipeline configuration added to `dp_pipelines` will be uploaded to the deepset AI platform.
`name`, `workspace`, and `query` are mandatory fields in the configuration dictionary.
`indexing` is optional.


### Uploading Pipelines

1. Git commit all your local changes. Make sure you have added all pipelines that you want to create or update to
`pipelines/__init__.py`.
2. Push your changes to a GitHub repository.
3. Go to the GitHub UI and create a Pull Request.

Once you created your pull request, the CI-workflow will run.
The CI runs code-quality checks and tests. For pull requests, it validates that your pipeline definitions can be serialized, but it doesn't actually write the serialized files.
When you merge your pull request to the main branch, the CI will then serialize your pipelines and save them to the `dist/pipelines` directory.
You will see a commit from the GitHub-Actions Bot that places these serialized pipelines into the `dist/pipelines` directory.
If no pipelines were added or existing pipelines haven't changed, the Bot will skip serialization.
Once all checks pass, merge your pull request.

To sync your changes to the deepset AI platform:
1. Go to the releases tab in GitHub and [create a new release](https://docs.github.com/en/repositories/releasing-projects-on-github/managing-releases-in-a-repository#creating-a-release).
2. Create a new tag following this schema: `pipelines-*.*.*` (e.g. `pipelines-1.0.0` for version one).
3. Name the release, then publish it.


Publishing the release will automatically tag the latest commit on the main-branch.
The tag triggers the `.github/workflows/publish_pipelines_on_tag.yaml`-workflow.
The workflow will scan your `dist/pipelines` directory and for each pipeline, it will check against the deepset API if the pipeline is new or was updated.
If the pipeline does not exist yet or the version in your repository differs from the version running in the deepset platform,
the workflow will create or update the pipeline.

Once the workflow finished, log in to the deepset AI platform and verify that your pipelines have been created or updated.



### Creating Custom Components

For more information about custom components, see [Custom Components](https://docs.cloud.deepset.ai/docs/custom-components). 

For a step-by-step guide on creating custom components, see [Create a Custom Component](https://docs.cloud.deepset.ai/docs/create-a-custom-component).

See also our tutorial for [creating a custom RegexBooster component](https://docs.cloud.deepset.ai/docs/tutorial-creating-a-custom-component).

**Directory Structure**


| File | Description |
|------|-------------|
| `/src/dc_custom_component/components` | Directory for implementing custom components. You can logically group custom components in sub-directories. See how sample components are grouped by type. |
| `/src/dc_custom_component/__about__.py` | Your custom components' version. Bump the version every time you update your component before uploading it to deepset Cloud. This is not needed if you are using the GitHub action workflow (in this case the version will be determined by the GitHub release tag). |
| `/pyproject.toml` | Information about the project. If needed, add your components' dependencies in this file in the `dependencies` section. |

The directory where your custom component is stored determines the name of the component group in Pipeline Builder. For example, the `CharacterSplitter` component would appear in the `Preprocessors` group, while the `KeywordBooster` component would be listed in the `Rankers` group. You can drag these components onto the canvas to use them.

When working with YAML, the location of your custom component implementation defines your component's `type`. For example, the sample components have the following types because of their location:
  - `dc_custom_component.components.example_components.preprocessors.character_splitter.CharacterSplitter`
  - `dc_custom_component.components.example_components.rankers.keyword_booster.KeywordBooster`

Here is how you would add them to a pipeline:
```yaml
components:
  splitter:
    type: dc_custom_component.example_components.preprocessors.character_splitter.CharacterSplitter
    init_parameters: {}
  ...
    
```

When working with Python, you can just import your custom components.
Here is how you would use a custom component in your pipeline:

```python
from dc_custom_component.components.example_components.rankers.keyword_booster import KeywordBooster

from haystack import Pipeline

pp = Pipeline()

pp.add_component("booster", KeywordBooster({"deepset": 2.0}))
```

### Uploading Custom Components

1. Git commit your local changes.
2. Push the changes to a GitHub repository. 
3. Create a pull request, wait for the CI-workflow to pass and merge your changes. 
4. Once your pull request is merged, [create a new release](https://docs.github.com/en/repositories/releasing-projects-on-github/managing-releases-in-a-repository#creating-a-release) with a new tag following this schema:
`components-*.*.*` (e.g. `components-1.0.0` for version one).
5. Name and publish the release.

Publishing the release will automatically tag the latest commit on the main-branch.
The tag triggers the `.github/workflows/publish_components_on_tag.yaml`-workflow.
The workflow will upload all Haystack components in  the `src/dc_custom_component/components`-directory.
A few minutes after the components were uploaded, the components should be available in the deepset AI platform.



### Developer tools

We provide a suite of tools for your development workflow with this template.

Linting and formatting:

```bash
hatch run code-quality:all
```

Testing:

```bash
hatch run tests
```

All provided tools are defined as scripts in the `pyproject.toml`.


### Troubleshooting

To debug the installation of custom components on the deepset platform, you can run:

- On Linux and macOS: `hatch run dc:logs` 
- On Windows: `hatch run dc:logs-windows`

This will print the installation logs of the latest version of your custom components.
