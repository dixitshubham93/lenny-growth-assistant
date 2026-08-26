import json
from datetime import datetime
from pydantic import BaseModel

class MessageSchema(BaseModel):
    id: str
    session_id: str
    role: str
    content: str
    created_at: datetime
    # NO sources explicitly defined!

class MockMessage:
    def __init__(self):
        self.id = "123"
        self.session_id = "abc"
        self.role = "user"
        self.content = "hi"
        self.created_at = datetime.now()
        self.sources = ["abc"]

def _message_to_schema(msg) -> MessageSchema:
    # We pass sources=msg.sources to the Pydantic schema constructor
    return MessageSchema(
        id=str(msg.id),
        session_id=str(msg.session_id),
        role=msg.role,
        content=msg.content,
        created_at=msg.created_at,
        sources=msg.sources,
    )

try:
    print(_message_to_schema(MockMessage()).model_dump())
except Exception as e:
    print("ERROR:", e)
