"""
Siphon pipeline through iterative development;
First just did URIs, then context generation, now synthetic data + completed ProcessedContent.
"""

from siphon.data.type_definitions.source_type import SourceType
from siphon.data.processed_content import ProcessedContent
from siphon.cli.cli_params import CLIParams
from siphon.main.siphon import siphon
from siphon.tests.fixtures.assets import sample_assets
import pytest

# Import Conduit so we can set a cache.
from conduit.sync import Model, ConduitCache

Model._conduit_cache = ConduitCache(db_path=".test_minimal_cache.db")

# Create our list of source types
immediately_usable_types = """
Text
Doc
Audio
Image
GitHub
YouTube
Article
""".strip().split("\n")

immediately_usable_types = [SourceType(x) for x in immediately_usable_types]
sourcetype_assets = sample_assets["sourcetypes"]

# Just text for now
immediate_usable_types = [immediately_usable_types[0]]  # Text


@pytest.mark.parametrize("source_type", immediately_usable_types)
def test_minimal_siphon(source_type):
    """
    Test the minimal siphon pipeline for a subset of source types.
    """
    # Get the sample source for the given source type
    source = sourcetype_assets[source_type]

    # Create CLI parameters
    cli_params = CLIParams(source=str(source))

    # Run siphon and get the context
    processed_content = siphon(cli_params)

    # Display
    processed_content.pretty_print()

    assert isinstance(processed_content, ProcessedContent)
    assert processed_content.synthetic_data is not None
