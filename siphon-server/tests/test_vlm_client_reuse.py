from __future__ import annotations

import httpx


def test_vlm_client_is_module_level_singleton():
    """VLMClient must reuse a single httpx.Client, not create one per call."""
    import siphon_server.sources.doc.vlm_client as vlm_module
    assert hasattr(vlm_module, "_shared_client")
    assert isinstance(vlm_module._shared_client, httpx.Client)


def test_describe_method_uses_shared_client(tmp_path):
    """VLMClient.describe() must use _shared_client, not create a new httpx.Client."""
    import siphon_server.sources.doc.vlm_client as vlm_module
    from unittest.mock import MagicMock, patch

    # Verify no NEW httpx.Client instances are created during describe()
    new_client_calls = []
    original_init = httpx.Client.__init__

    def tracking_init(self, *args, **kwargs):
        new_client_calls.append(1)
        original_init(self, *args, **kwargs)

    vlm = vlm_module.VLMClient(url="http://localhost", model="test-model")

    with patch.object(httpx.Client, "__init__", tracking_init):
        with patch.object(vlm_module._shared_client, "post") as mock_post:
            mock_resp = MagicMock()
            mock_resp.json.return_value = {
                "choices": [{"message": {"content": "description"}}]
            }
            mock_resp.raise_for_status = MagicMock()
            mock_post.return_value = mock_resp
            result = vlm.describe(b"fake_image_bytes", "describe this")

    assert new_client_calls == [], "describe() created a new httpx.Client — should use _shared_client"
    assert result == "description"
