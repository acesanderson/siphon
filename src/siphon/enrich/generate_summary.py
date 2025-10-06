from pathlib import Path
from conduit.sync import Model, Prompt, Conduit
from siphon.data.processed_content import ProcessedContent

dir_path = Path(__file__).parent
prompts_dir = dir_path.parent / "prompts"
title_prompt_file = prompts_dir / "enrich_summary.jinja2"


def calculate_target_summary_length(content_length: int) -> tuple[int, int]:
    """
    Calculate target summary length based on content length.
    Returns (target_words, percentage)
    """
    if content_length < 300:
        percentage = 70
        target_words = int(content_length * percentage / 100)
    elif content_length < 1000:
        percentage = 60  # Increased from 40%
        target_words = int(content_length * percentage / 100)
    elif content_length < 3000:
        percentage = 40  # Increased from 20%
        target_words = int(content_length * percentage / 100)
    elif content_length < 8000:
        percentage = 30  # Increased from 12%
        target_words = int(content_length * percentage / 100)
    else:
        # Fixed length for very long content
        target_words = 2000  # Your preferred cap
        percentage = int((target_words / content_length) * 100)

    target_words = max(50, target_words)  # Minimum 50 words
    return target_words, percentage


def generate_summary(
    processed_content: ProcessedContent, model: str = "llama3.3:latest"
) -> str:
    # Get attributes from processed content
    uri = processed_content.uri
    llm_context = processed_content.llm_context
    target_words, percentage = calculate_target_summary_length(len(llm_context.split()))
    input_variables = {
        "uri": uri,
        "llm_context": llm_context,
        "target_length": str(target_words),
        "length_percentage": str(percentage),
    }
    # Build our conduit
    prompt = Prompt(title_prompt_file.read_text())
    model_obj = Model(model)
    conduit = Conduit(prompt=prompt, model=model_obj)
    response = conduit.run(input_variables=input_variables)
    # Return the generated title
    return str(response.content)
