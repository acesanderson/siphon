from conduit.sync import Conduit, Prompt, Model, Response, Verbosity, ConduitCache
from pathlib import Path
from typing import Literal
from rich.console import Console

# Constants
TERSE_PROMPT_FILE = Path(__file__).parent / "terse_docs_prompt.jinja2"
VERBOSE_PROMPT_FILE = Path(__file__).parent / "verbose_docs_prompt.jinja2"
PREFERRED_MODEL = "gemini2.5"
VERBOSITY = Verbosity.COMPLETE
CONSOLE = Console()
# Our singleton
Model.console = CONSOLE


def generate_docs(
    xml_string: str, prompt_type: Literal["terse", "verbose"]
) -> Response:
    """
    Generate documentation from an XML string using a predefined prompt and model.
    """
    # Switch between terse and verbose prompts
    prompt_file = TERSE_PROMPT_FILE if prompt_type == "terse" else VERBOSE_PROMPT_FILE
    # Build the conduit
    prompt = Prompt(prompt_file.read_text())
    model = Model(PREFERRED_MODEL)
    conduit = Conduit(prompt=prompt, model=model)
    response = conduit.run(input_variables={"code": xml_string}, verbose=VERBOSITY)
    # Validate response type
    if not isinstance(response, Response):
        raise ValueError(
            f"Expected response to be of type Response, got {type(response)}"
        )
    return response
