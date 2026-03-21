import httpx
import base64
from typing import Optional


class VLMClient:
    """OpenAI-compatible chat completion client for image description."""

    def __init__(self, url: str, model: str, timeout: float = 60.0):
        self.url = url
        self.model = model
        self.timeout = timeout

    def describe(self, image_data: bytes, prompt: str) -> str:
        """
        Call VLM with image and prompt.

        Args:
            image_data: Image bytes
            prompt: Text prompt for VLM

        Returns:
            VLM response text

        Raises:
            TimeoutError: If VLM call times out
            ValueError: If VLM returns empty response
        """
        image_b64 = base64.b64encode(image_data).decode('utf-8')

        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{image_b64}"
                            }
                        }
                    ]
                }
            ],
            "temperature": 0.2,
            "max_tokens": 500,
        }

        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(self.url, json=payload)
                response.raise_for_status()
                data = response.json()

                description = data["choices"][0]["message"]["content"]

                if not description or not description.strip():
                    raise ValueError("VLM returned empty response")

                return description

        except (httpx.TimeoutException, httpx.ConnectTimeout, httpx.ReadTimeout, httpx.WriteTimeout, httpx.PoolTimeout) as e:
            raise TimeoutError(f"VLM request timed out after {self.timeout}s") from e
        except Exception as e:
            raise ValueError(f"VLM request failed: {e}")
