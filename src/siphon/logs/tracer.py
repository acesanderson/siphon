# src/siphon/debug/pipeline_tracer.py
from rich.console import Console
from rich.markdown import Markdown
import json
import os
from typing import Any


class PipelineTracer:
    def __init__(self, enabled: bool | None = None):
        if enabled is None:
            enabled = os.getenv("SIPHON_DEBUG_PIPELINE", "").lower() in (
                "1",
                "true",
                "yes",
            )

        self.enabled = enabled
        self.console = Console(stderr=True)
        self.step_count = 0

    def trace_step(self, step_name: str, obj: Any, obj_type: str = None):
        if not self.enabled:
            return

        self.step_count += 1

        # Create JSON content
        if hasattr(obj, "model_dump"):
            content = json.dumps(
                obj.model_dump(), indent=2, default=str, ensure_ascii=False
            )
        elif hasattr(obj, "__dict__"):
            content = json.dumps(
                obj.__dict__, indent=2, default=str, ensure_ascii=False
            )
        else:
            content = str(obj)

        # Create markdown with code block
        obj_type_str = obj_type or type(obj).__name__
        markdown_content = f"""
# Step {self.step_count}: {step_name}
*{obj_type_str}*
```json
{content}
```
"""

        markdown = Markdown(markdown_content)
        self.console.print(markdown)
        self.console.print()  # Add spacing

    def trace_error(self, step_name: str, error: Exception):
        if not self.enabled:
            return

        self.step_count += 1

        markdown_content = f"""
# Step {self.step_count}: {step_name} FAILED
*Error: {type(error).__name__}*
```
{str(error)}
```
"""

        markdown = Markdown(markdown_content)
        self.console.print(markdown)
        self.console.print()


# Global tracer instance
tracer = PipelineTracer()
