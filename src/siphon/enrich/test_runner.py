"""
Early testing suggests cogito:32b and qwen2.5:32b are the best models for this use case.
"""

from siphon.enrich.enrich import enrich_content
from siphon.tests.fixtures.example_ProcessedContent import dummy_content
from time import time

models = """
gemma3:27b
cogito:32b
cogito:14b
phi4:14b
qwen2.5:32b
qwen2.5:14b
qwen3:30b
llama3.1:latest
llama4:16x17b
llama3.2:latest
deepseek-r1:32b
mistral:latest
mistral-nemo:12b
""".strip().split("\n")


output = {}
for index, model in enumerate(models):
    print(f"Processing model {index + 1}/{len(models)}: {model}")
    try:
        start_time = time()
        syntheticdata = enrich_content(content, model=model)
        end_time = time()
        duration = end_time - start_time
        print(f"Model {model} processed in {duration:.2f} seconds")
        output[model] = {
            "llm_output": syntheticdata.model_dump_json(indent=2),
            "duration": duration,
        }
    except:
        print(f"Error processing model {model}")

prompt_str = """
I've asked a set of Ollama models to generate synthetic data based on a given content.
In particular, a title, a description, and a summary.

Here's the context I provided:
<content>
{{content}}
</content>

Here's all the generated data from the models:
<model_outputs>
{{model_outputs}}
</model_outputs>

Please provide an assesment of the quality of the generated data, reviewing each model's output individually and identifying the best and worst models.
"""


def analyze_output(output: dict, content, model: str = "gemini2.5") -> str:
    from conduit.sync import Prompt, Model, Conduit
    import json

    model_outputs = json.dumps(output, indent=2)
    content_str = content.model_dump_json(indent=2)
    input_variables = {"model_outputs": model_outputs, "content": content_str}
    model_obj = Model(model)
    prompt = Prompt(prompt_str)
    conduit = Conduit(model=model_obj, prompt=prompt)
    response = conduit.run(input_variables=input_variables)
    return str(response.content)


analysis = analyze_output(output, dummy_content, model="o4-mini")
print(analysis)
