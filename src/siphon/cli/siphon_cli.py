"""
This is the CLI entry point for siphon.

Think of this as `cat` for LLMs. A simple command-line interface to convert files or URLs into context for LLMs.

Users can either provide a file path or a URL to retrieve the context.
Usage:
    python siphon_cli.py <file_or_url>

This script will determine if the input is a file path or a URL,
and then retrieve the context + store it from the specified source.
"""

from siphon.main.siphon import siphon
from siphon.cli.cli_params import CLIParams
from siphon.cli.implicit_input import ImplicitInput
from siphon.logs.logging_config import configure_logging
import argparse, logging, sys
from typing import TYPE_CHECKING

logger = configure_logging(
    level=logging.ERROR,
    console=True,
)


if TYPE_CHECKING:
    from conduit.message.imagemessage import ImageMessage


def grab_image_from_clipboard() -> tuple | None:
    """
    Attempt to grab image from clipboard; return tuple of mime_type and base64.
    """
    import os

    if "SSH_CLIENT" in os.environ or "SSH_TTY" in os.environ:
        print("Image paste not available over SSH.")
        return

    import warnings
    from PIL import ImageGrab
    import base64, io, sys

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # Suppress PIL warnings
        image = ImageGrab.grabclipboard()

    if image:
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")  # type: ignore[reportCallIssue]
        img_base64 = base64.b64encode(buffer.getvalue()).decode()
        # Save for next query
        print("Image captured!")
        # Build our ImageMessage
        image_content = img_base64
        mime_type = "image/png"
        return mime_type, image_content
    else:
        print("No image detected.")
        sys.exit()


def create_image_message(
    combined_query: str, mime_type: str, image_content: str
) -> "ImageMessage | None":
    if not image_content or not mime_type:
        return
    role = "user"
    text_content = combined_query

    from conduit.message.imagemessage import ImageMessage

    imagemessage = ImageMessage(
        role=role,
        text_content=text_content,
        image_content=image_content,
        mime_type=mime_type,
    )
    return imagemessage


def parse_tags(tags: str) -> list[str]:
    """
    Parse a comma-delimited string of tags into a list.
    """
    if not tags:
        return []
    return [tag.strip() for tag in tags.split(",") if tag.strip()]


def main():
    # If script was run with no arguments, attempt to grab implicit input.
    if len(sys.argv) == 1:
        logger.info(
            "No arguments provided. Attempting to grab from stdin or clipboard."
        )
        implicit_input = ImplicitInput.from_environment()
        if implicit_input:
            implicit_input.print()
            sys.exit()

    # Parse command-line arguments
    parser = argparse.ArgumentParser(description="siphon file to LLM context")
    parser.add_argument(
        "source", type=str, nargs="?", help="Path to the file to convert"
    )
    parser.add_argument(
        "-C",
        "--cloud",
        action="store_true",
        help="Use cloud LLMs for synthetic data if applicable",
    )
    parser.add_argument(
        "-r",
        "--return_type",
        type=str,
        choices=["c", "s", "u"],
        default="s",
        help="Type of data to return: 'c' (context), 's' (synthetic data), or 'u' (URI). Defaults to 'synthetic_data', i.e. a summary.",
    )
    parser.add_argument(
        "-c",
        "--cache-options",
        type=str,
        choices=["u", "r", "c"],
        default="c",
        help="Special cache flags: 'u' (uncached, do not save), 'r' (recache, save again), or 'c' (cached, use existing cache if available). Defaults to 'c'.",
    )
    parser.add_argument(
        "-i",
        "--image",
        action="store_true",
        help="Grab an image from the clipboard and use it as context.",
    )
    parser.add_argument(
        "-t",
        "--tags",
        type=str,
        help="Comma-delimited list of tags. Useful for organizing content.",
    )
    parser.add_argument(
        "-p",
        "--pretty",
        action="store_true",
        help="Pretty print the output.",
    )
    parser.add_argument(
        "--raw",
        action="store_true",
        help="Output raw markdown without formatting.",
    )
    parser.add_argument(
        "--last",
        "-l",
        action="store_true",
        help="Load the last processed content from the cache.",
    )
    args = parser.parse_args()
    args_dict = vars(args)
    query = CLIParams(
        source=args_dict["source"],
        cache_options=args_dict["cache_options"],
        cloud=args_dict["cloud"],
        tags=parse_tags(args_dict["tags"]),
    )
    # Detect if no input; just print help and exit.
    if len(sys.argv) == 1:
        parser.print_help(sys.stderr)
        sys.exit(1)

    # Get ProcessedContent, by various means.
    ## If we just want the last siphon:
    if args.last:
        from siphon.database.postgres.PGRES_processed_content import get_last_siphon

        processed_content = get_last_siphon()
        if not processed_content:
            logger.error("No last processed content found in cache.")
            sys.exit(1)

        if args.pretty:
            output = f"# {processed_content.title}: {processed_content.id}\n\n{processed_content.summary}"
            from rich.markdown import Markdown
            from rich.console import Console

            console = Console()
            markdown = Markdown(output)
            console.print(markdown)
            sys.exit()
        else:
            print(processed_content.summary)
            sys.exit()

    ## If we want to grab an image from the clipboard and process it:
    if args.image:
        raise NotImplementedError(
            "Image context is not yet implemented. Please use a file or URL."
        )

    ## If we want to process a Source:
    if query:
        processed_content = siphon(query)
        output = f"# {processed_content.title}: {processed_content.id}\n\n{processed_content.summary}"
        if args.pretty:
            output = processed_content.summary
            from rich.markdown import Markdown
            from rich.console import Console

            console = Console()
            markdown = Markdown(output)
            console.print(markdown)
            sys.exit()
        if args.return_type:
            match args.return_type:
                case "c":
                    output = processed_content.context
                    print(output)
                    sys.exit()
                case "s":
                    output = processed_content.summary
                    print(output)
                    sys.exit()
                case "u":
                    output = processed_content.uri
                    print(output)
                    sys.exit()
                case _:
                    logger.error("Invalid return type specified.")
                    sys.exit(1)
        if args.raw:
            print(output)
            sys.exit()
        else:
            from rich.markdown import Markdown
            from rich.console import Console

            console = Console()
            markdown = Markdown(output)
            console.print(markdown)
            sys.exit()


if __name__ == "__main__":
    main()
