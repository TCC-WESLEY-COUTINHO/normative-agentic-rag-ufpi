"""Validate public messages against the unchanged shared schema inside the image."""

import json
import sys
from schema import ChatMessage

messages = json.load(sys.stdin)
for message in messages:
    restored = ChatMessage.model_validate(message).model_dump(mode="json")
    assert restored == message
print(json.dumps({"typed_roundtrips": [len(messages), len(messages)]}))
