from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field

class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = ""

class TaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    status: str | None = Field(default=None, pattern="^(new|in_progress|done)$")

class TaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    title: str
    description: str
    status: str
    created_at: datetime
