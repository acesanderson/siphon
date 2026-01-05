For Siphon -- this is the new implementation for enrichment (once we actually build the strategies in Conduit).

```python
from conduit.extensions.summarization.strategies import (
    one_shot_summarizer,
    map_reduce_summarizer,
    hierarchical_summarizer,
)
from conduit.extensions.summarization.chunkers import naive_chunker

# Option A: explicit in caller
if token_count(text) <= SAFE_WINDOW:
    summary = one_shot_summarizer(...)
elif estimated_output(text) <= SAFE_WINDOW:
    condensed = map_reduce_summarizer(...)
    summary = one_shot_summarizer(...)
else:
    condensed = hierarchical_summarizer(...)
    summary = one_shot_summarizer(...)

# Option B: router function
condensed = condense(text, chunker=naive_chunker(n=14000))  # internally picks strategy
summary = one_shot_summarizer(prompt=obsidian_prompt, text=condensed)
```
