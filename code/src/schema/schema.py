from typing import Any, Literal, NotRequired

from pydantic import BaseModel, Field, SerializeAsAny, field_validator, model_validator
from typing_extensions import TypedDict

from rag_baseline.calculator_contracts import CalculatorToolResult
from rag_baseline.conversation_contracts import GroundedFollowUpResult
from rag_baseline.tool_contracts import NormativeToolResult, ToolStatus
from schema.models import AllModelEnum, AnthropicModelName, OpenAIModelName


class AgentInfo(BaseModel):
    """Info about an available agent."""

    experimental: bool = False
    available: bool = True
    unavailable_reason: str | None = None

    key: str = Field(
        description="Agent key.",
        examples=["research-assistant"],
    )
    description: str = Field(
        description="Description of the agent.",
        examples=["A research assistant for generating research papers."],
    )


class ServiceMetadata(BaseModel):
    """Metadata about the service including available agents and models."""

    agents: list[AgentInfo] = Field(
        description="List of available agents.",
    )
    models: list[AllModelEnum] = Field(
        description="List of available LLMs.",
    )
    default_agent: str = Field(
        description="Default agent used when none is specified.",
        examples=["research-assistant"],
    )
    default_model: AllModelEnum = Field(
        description="Default model used when none is specified.",
    )


class UserInput(BaseModel):
    """Basic user input for the agent."""

    message: str = Field(
        description="User input to the agent.",
        examples=["What is the weather in Tokyo?"],
    )
    model: SerializeAsAny[AllModelEnum] | None = Field(
        title="Model",
        description="LLM Model to use for the agent.",
        default=OpenAIModelName.GPT_4O_MINI,
        examples=[OpenAIModelName.GPT_4O_MINI, AnthropicModelName.HAIKU_35],
    )
    thread_id: str | None = Field(
        description="Thread ID to persist and continue a multi-turn conversation.",
        default=None,
        examples=["847c6285-8fc9-4560-a83f-4e6285809254"],
    )
    user_id: str | None = Field(
        description="User ID to persist and continue a conversation across multiple threads.",
        default=None,
        examples=["847c6285-8fc9-4560-a83f-4e6285809254"],
    )
    agent_config: dict[str, Any] = Field(
        description="Additional configuration to pass through to the agent",
        default={},
        examples=[{"spicy_level": 0.8}],
    )


class StreamInput(UserInput):
    """User input for streaming the agent's response."""

    stream_tokens: bool = Field(
        description="Whether to stream LLM tokens to the client.",
        default=True,
    )


class ToolCall(TypedDict):
    """Represents a request to call a tool."""

    name: str
    """The name of the tool to be called."""
    args: dict[str, Any]
    """The arguments to the tool call."""
    id: str | None
    """An identifier associated with the tool call."""
    type: NotRequired[Literal["tool_call"]]


class ChatMessage(BaseModel):
    """Message in a chat."""

    type: Literal["human", "ai", "tool", "custom"] = Field(
        description="Role of the message.",
        examples=["human", "ai", "tool", "custom"],
    )
    content: str = Field(
        description="Content of the message.",
        examples=["Hello, world!"],
    )
    normative_result: NormativeToolResult | None = Field(
        default=None,
        description="Public typed result for the current normative turn; absent for conversation.",
    )
    grounded_followup_result: GroundedFollowUpResult | None = None
    calculator_result: CalculatorToolResult | None = None

    @field_validator("normative_result", mode="before")
    @classmethod
    def public_normative_result(cls, value):
        if isinstance(value, NormativeToolResult):
            # Never retain private generation diagnostics in the transport object.
            return value.model_dump()
        if isinstance(value, dict) and "internal_audit" in value:
            raise ValueError("Private audit is not accepted by the public transport.")
        return value

    @model_validator(mode="after")
    def authoritative_content(self):
        if (
            sum(
                result is not None
                for result in (
                    self.normative_result,
                    self.grounded_followup_result,
                    self.calculator_result,
                )
            )
            > 1
        ):
            raise ValueError("A message must contain at most one typed result.")
        if self.calculator_result is not None:
            if self.type != "ai" or self.content != self.calculator_result.content:
                raise ValueError("Calculator transport must preserve its content exactly.")
        if self.grounded_followup_result is not None:
            if self.normative_result is not None:
                raise ValueError("A message cannot contain normative and derived results together.")
            if self.type != "ai" or self.content != self.grounded_followup_result.content:
                raise ValueError(
                    "Derived transport must preserve its presentation content exactly."
                )
        if self.normative_result is not None:
            result = self.normative_result
            expected = {
                ToolStatus.ANSWER: result.answer,
                ToolStatus.CLARIFICATION: result.clarification_question,
                ToolStatus.ERROR: result.safe_message,
            }[result.status]
            if self.type != "ai" or self.content != expected:
                raise ValueError("Normative transport must preserve authoritative content exactly.")
        return self

    tool_calls: list[ToolCall] = Field(
        description="Tool calls in the message.",
        default=[],
    )
    tool_call_id: str | None = Field(
        description="Tool call that this message is responding to.",
        default=None,
        examples=["call_Jja7J89XsjrOLA5r!MEOW!SL"],
    )
    run_id: str | None = Field(
        description="Run ID of the message.",
        default=None,
        examples=["847c6285-8fc9-4560-a83f-4e6285809254"],
    )
    response_metadata: dict[str, Any] = Field(
        description="Response metadata. For example: response headers, logprobs, token counts.",
        default={},
    )
    custom_data: dict[str, Any] = Field(
        description="Custom message data.",
        default={},
    )

    def pretty_repr(self) -> str:
        """Get a pretty representation of the message."""
        base_title = self.type.title() + " Message"
        padded = " " + base_title + " "
        sep_len = (80 - len(padded)) // 2
        sep = "=" * sep_len
        second_sep = sep + "=" if len(padded) % 2 else sep
        title = f"{sep}{padded}{second_sep}"
        return f"{title}\n\n{self.content}"

    def pretty_print(self) -> None:
        print(self.pretty_repr())  # noqa: T201


class Feedback(BaseModel):  # type: ignore[no-redef]
    """Feedback for a run, to record to LangSmith."""

    run_id: str = Field(
        description="Run ID to record feedback for.",
        examples=["847c6285-8fc9-4560-a83f-4e6285809254"],
    )
    key: str = Field(
        description="Feedback key.",
        examples=["human-feedback-stars"],
    )
    score: float = Field(
        description="Feedback score.",
        examples=[0.8],
    )
    kwargs: dict[str, Any] = Field(
        description="Additional feedback kwargs, passed to LangSmith.",
        default={},
        examples=[{"comment": "In-line human feedback"}],
    )


class FeedbackResponse(BaseModel):
    status: Literal["success"] = "success"


class ChatHistoryInput(BaseModel):
    """Input for retrieving chat history."""

    thread_id: str = Field(
        description="Thread ID to persist and continue a multi-turn conversation.",
        examples=["847c6285-8fc9-4560-a83f-4e6285809254"],
    )


class ChatHistory(BaseModel):
    messages: list[ChatMessage]
