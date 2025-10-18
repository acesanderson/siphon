#!/usr/bin/env python3
"""
Flatten - CLI tool for converting GitHub repositories and local directories
into LLM-friendly XML format.

Usage:
    python Flatten.py .                                    # Flatten current directory
    python Flatten.py /path/to/directory                   # Flatten specific directory
    python Flatten.py https://github.com/owner/repo        # Flatten GitHub repository

Options:
    -l, --last        Retrieve and display the last stored response
    -d, --docs        Generate project README documentation
    -p, --pretty      Pretty-print the output XML
    -v, --verbose     Enable verbose readme generation (default is terse)
"""

import argparse
import sys
import json
from pathlib import Path
from rich.console import Console
from rich.markdown import Markdown


from siphon.ingestion.github.flatten_directory import flatten_directory
from siphon.ingestion.github.flatten_url import flatten_github_repo
from conduit.sync import Response


PREVIOUS_RESPONSE_FILE = Path(__file__).parent / "flatten" / "previous_response.json"


def store_response(response: Response) -> None:
    cache_dict = response.to_cache_dict()
    with PREVIOUS_RESPONSE_FILE.open("w", encoding="utf-8") as f:
        json.dump(cache_dict, f, indent=2)


def retrieve_response() -> Response | None:
    if not PREVIOUS_RESPONSE_FILE.exists():
        return None
    with PREVIOUS_RESPONSE_FILE.open("r", encoding="utf-8") as f:
        cache_dict = json.load(f)
    return Response.from_cache_dict(cache_dict)


def main():
    """Main CLI entry point for the Flatten tool."""
    parser = argparse.ArgumentParser(
        description="Flatten a GitHub repo or local directory into LLM-friendly XML format",
    )
    # Basic use case: generate XML as LLM context
    parser.add_argument(
        "target",
        type=str,
        help="GitHub URL, directory path, or '.' for current directory",
    )
    # Docs generation args
    parser.add_argument(
        "-l",
        "--last",
        action="store_true",
        help="Retrieve and display the last stored response",
    )
    parser.add_argument(
        "-d",
        "--docs",
        action="store_true",
        help="Generate project README.",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose readme. Default is terse.",
    )
    parser.add_argument(
        "-p",
        "--pretty",
        action="store_true",
        help="Pretty-print the output XML",
    )

    args = parser.parse_args()
    target = args.target

    # Detect no input, if no args provided, show help
    # If no args provided, show help and exit
    if len(sys.argv) == 1:
        parser.print_help(sys.stderr)
        sys.exit(1)

    try:
        if target.startswith("https://github.com/"):
            # Process GitHub repository
            output = flatten_github_repo(target)
        else:
            # Process local directory (including ".")
            output = flatten_directory(target)

    except Exception as e:
        print(f"Error processing target '{target}': {e}", file=sys.stderr)
        sys.exit(1)

    assert output is not None, "No output generated from the target."

    # Handle --last flag to retrieve previous response
    if args.last:
        previous_response = retrieve_response()
        if previous_response is not None:
            if args.pretty:
                console = Console()
                md = Markdown(previous_response.content)
                console.print(md)
                exit(0)
            else:
                print(previous_response.content)
                exit(0)
        else:
            print("No previous response found.", file=sys.stderr)
        return
    # Handle --docs flag to generate README
    if args.docs:
        from siphon.scripts.flatten.generate_docs import generate_docs

        prompt_type = "verbose" if args.verbose else "terse"
        response = generate_docs(xml_string=output, prompt_type=prompt_type)
        assert isinstance(response, Response), (
            f"Expected Response object from generate_docs, got {type(response)}"
        )
        store_response(response)
        if args.pretty:
            console = Console()
            md = Markdown(response.content)
            console.print(md)
        else:
            print(response.content)

    # Finally, print output.
    else:
        print(output)


if __name__ == "__main__":
    main()
