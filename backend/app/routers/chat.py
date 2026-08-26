import json

from anthropic import Anthropic
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import ai_tools, models, schemas
from app.config import settings
from app.deps import get_current_user, get_db

router = APIRouter(prefix="/chat", tags=["chat"])

SYSTEM_PROMPT = (
    "You are the Chaos Assistant inside the Chaos Tracker app. You answer questions "
    "about reported-incident trends, incident category breakdowns, and county-level "
    "population migration near a location, using the tools you're given. "
    "Never invent numbers -- if a question needs data, call a tool first. "
    "If the user doesn't give coordinates and none are in the message context, ask "
    "them to search or pick a location on the map first instead of guessing one. "
    "Keep answers to 2-4 plain-language sentences, no markdown tables or headers."
)

MAX_TOOL_ROUNDS = 4


@router.post("", response_model=schemas.ChatResponse)
def chat(
    body: schemas.ChatRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not settings.anthropic_api_key:
        raise HTTPException(500, "ANTHROPIC_API_KEY is not set in .env -- the chatbot is disabled until it is.")

    client = Anthropic(api_key=settings.anthropic_api_key)

    user_text = body.message
    if body.lat is not None and body.lng is not None:
        user_text += f"\n\n(Context: the user is currently looking at lat={body.lat}, lng={body.lng} on the map.)"

    messages = [{"role": "user", "content": user_text}]
    tool_calls_made: list[schemas.ToolCallRecord] = []

    for _ in range(MAX_TOOL_ROUNDS):
        response = client.messages.create(
            model=settings.anthropic_model,
            max_tokens=600,
            system=SYSTEM_PROMPT,
            tools=ai_tools.TOOLS,
            messages=messages,
        )

        if response.stop_reason != "tool_use":
            final_text = "".join(block.text for block in response.content if block.type == "text")
            return schemas.ChatResponse(reply=final_text, tool_calls=tool_calls_made)

        # Claude asked for one or more tools -- run each, then send the results back.
        messages.append({"role": "assistant", "content": response.content})

        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            result = ai_tools.run_tool(block.name, block.input, db)
            tool_calls_made.append(schemas.ToolCallRecord(tool=block.name, input=block.input, output=result))
            tool_results.append(
                {"type": "tool_result", "tool_use_id": block.id, "content": json.dumps(result)}
            )
        messages.append({"role": "user", "content": tool_results})

    raise HTTPException(500, "The assistant got stuck calling tools repeatedly -- try rephrasing your question.")
