from conduit.sync import Model, Verbosity
from conduit.domain.message.message import AudioContent, TextContent, UserMessage
from conduit.core.model.models.modelstore import ModelStore
from pathlib import Path

audio_file = Path(__file__).parent / "audio.mp3"
ms = ModelStore()
model_name = "gpt-5"

model = Model(model_name)

audio_content = AudioContent.from_file(audio_file)
text_content = TextContent(text="Please summarize the following podcast.")
user_message = UserMessage(content=[text_content, audio_content])
messages = [user_message]

response = model.query(messages, verbosity=Verbosity.COMPLETE)
print(str(response.content))
