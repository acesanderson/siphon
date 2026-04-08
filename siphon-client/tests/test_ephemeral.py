from __future__ import annotations
import pytest
from siphon_client.ephemeral import sniff_bytes, EphemeralInputError


def test_sniff_bytes_rejects_zip():
    """AC 10: bare ZIP magic bytes raise EphemeralInputError."""
    zip_header = b"PK\x03\x04" + b"\x00" * 8
    with pytest.raises(EphemeralInputError, match="ZIP files are not supported"):
        sniff_bytes(zip_header)
