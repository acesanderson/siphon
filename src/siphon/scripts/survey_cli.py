"""
Research CLI - Multi-document synthesis and analysis tool.

Performs focused research across a collection of documents by:
1. Extracting content relevant to a specific research question from each document
2. Synthesizing findings into a unified strategic analysis

Perfect for competitive intelligence, market research, or strategic analysis
where you have multiple sources (transcripts, articles, reports, etc.) and
need to understand what they collectively say about a specific topic.

Usage:
   research_cli.py "Company's AI strategy and competitive positioning"
   research_cli.py "Product roadmap priorities" --dir ./q3_meetings/
   research_cli.py "Market expansion plans" --pattern "*.md,*.pdf,*.txt"

The tool uses async processing for speed and provides structured output
suitable for strategic decision-making. Requires documents to be in
text-readable format (.md, .txt, or other plain text files).

TBD: have this use Siphon to arbitrarily convert multiple document formats; for the moment it's only .txt and .md files, so you need to manually create the set of resources.
NOTE: we exclude Python and Jinja2 files by default, as they are not relevant to the research synthesis. The jinja2 file is where we might define a more complex prompt template for the contextual focus.
"""

from pathlib import Path
from conduit.sync import Conduit, Model, Prompt, Verbosity, ConduitCache
from conduit.batch import AsyncConduit, ModelAsync
import argparse

Model._conduit_cache = ConduitCache()
ModelAsync._conduit_cache = ConduitCache()

prompt1 = """
Extract all content relevant to the following contextual focus:

<contextual_focus>
{{contextual_focus}}
</contextual_focus>

From the provided document, identify and extract:
1. Direct statements, quotes, or claims related to this topic
2. Supporting data, metrics, or evidence  
3. Strategic decisions, initiatives, or plans
4. Customer use cases, examples, or case studies
5. Competitive positioning or market analysis
6. Future roadmap items or announced developments

For each extracted item:
- Provide the specific text or paraphrase
- Note the source context (e.g., "CEO statement", "product demo", "Q2 earnings call")
- Indicate confidence level: Direct quote, Clear inference, or Implied from context

Group extractions by category and prioritize recent information and authoritative sources.

Exclude general company background, tangential mentions, and purely historical information unless strategically relevant.

If no relevant content is found, state "No relevant content identified."

Here's the document content:
<document_content>
{{document_content}}
</document_content>

Return ONLY your summary.
"""


prompt2 = """
Based on the following extracted summaries from multiple sources, create a unified analysis of:
<contextual_focus>
{{contextual_focus}}
</contextual_focus>

EXTRACTED SUMMARIES:
<summaries>
{{summaries}}
</summaries>

Synthesize this information into a coherent summary that addresses:
- Key themes and strategic direction
- Supporting evidence and data points
- Notable contradictions or gaps between sources
- Actionable insights and implications

Structure your response with clear sections. Prioritize information from authoritative sources and recent developments. Where sources conflict or information is uncertain, note this explicitly.

Focus on providing a comprehensive yet concise understanding suitable for strategic decision-making.
"""


def research_directory(contextual_focus: str, paths: list[Path | str]) -> str:
    """
    Research synthesis across multiple documents in a directory.

    Args:
        contextual_focus (str): The research focus or question to guide the synthesis.
        paths (list[Path | str]): List of document paths to analyze. Can be strings or Path objects.

    Returns:
        str: A synthesized summary of the research findings across the documents.
    """
    # Coerce paths to Path objects if they are strings
    paths = [Path(p) if isinstance(p, str) else p for p in paths]

    # First conduit
    prompt = Prompt(prompt1)

    # generate async input variables
    input_variables_list = []
    for p in paths:
        document_content = Path(p).read_text()
        input_variables_list.append(
            {
                "contextual_focus": contextual_focus,
                "document_content": document_content,
            }
        )

    # Second conduit
    model = ModelAsync("gemini")
    conduit = AsyncConduit(
        model=model,
        prompt=prompt,
    )
    responses = conduit.run(
        input_variables_list=input_variables_list,
        verbose=Verbosity.SUMMARY,
    )

    # Combine responses into a single summary
    model = Model("gemini2.5")
    prompt = Prompt(prompt2)
    conduit = Conduit(model=model, prompt=prompt)
    response = conduit.run(
        input_variables={
            "contextual_focus": contextual_focus,
            "summaries": "\n\n".join([str(r.content) for r in responses]),
        },
        verbose=Verbosity.SUMMARY,
    )

    return str(response.content)


def main():
    parser = argparse.ArgumentParser(description="Research synthesis across documents")
    parser.add_argument("focus", help="Research focus/question")
    parser.add_argument("--dir", default=".", help="Directory containing documents")
    parser.add_argument(
        "--pattern", default="*.md,*.txt", help="File patterns to include"
    )
    parser.add_argument(
        "--exclude", default="*.py,*.jinja2", help="File patterns to exclude"
    )

    args = parser.parse_args()

    # Your existing logic but with args.focus instead of hardcoded contextual_focus
    contextual_focus = args.focus
    patterns = args.pattern.split(",")

    paths = []

    # Handle include patterns
    for pattern in patterns:
        paths.extend(Path(args.dir).glob(pattern.strip()))

    # Handle exclude patterns
    exclude_patterns = args.exclude.split(",") if args.exclude else []
    for exclude_pattern in exclude_patterns:
        paths = [p for p in paths if not p.match(exclude_pattern.strip())]

    if not paths:
        print(
            "No documents found matching the specified inclusion / exclusion patterns."
        )
        return

    print(f"Researching focus: {contextual_focus}")
    print(f"Found {len(paths)} documents to analyze.")
    summary = research_directory(contextual_focus, paths)
    print("\nSynthesis Summary:")
    print(summary)


if __name__ == "__main__":
    main()
