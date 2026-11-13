"""The only place where an experimental condition becomes concrete providers.

Graph nodes receive a `ConversationInterpreter`; they never import a provider SDK, a chat
model class or an HTTP client. Mode `none` reproduces A' exactly (no interpreter node
logic runs); `rules` routes the unchanged A' grammar through the common contract.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from rag_baseline.conversation_interpretation.base import ConversationInterpreter

InterpreterMode = Literal["none", "rules", "jev", "structured_llm", "hybrid"]


class InterpreterConfig(BaseModel):
    """Reproducible condition. Secrets are passed separately and never described."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    mode: InterpreterMode = "none"
    jev_model: str = "typesafe/jev-1.14"
    jev_choice_threshold: float = Field(default=0.6, ge=0, le=1)
    jev_noul_threshold: float = Field(default=0.5, ge=0, le=1)
    llm_model: str = "qwen/qwen3-30b-a3b-instruct-2507"
    llm_method: Literal["json_schema", "function_calling", "json_mode"] = "json_schema"
    llm_max_tokens: int = Field(default=400, ge=50)
    timeout_seconds: float = Field(default=20.0, gt=0)
    base_url: str = "https://openrouter.ai/api/v1"
    # OpenRouter routing preferences, e.g. {"order": ["nebius"], "allow_fallbacks": False}.
    provider: dict = Field(default_factory=dict)
    app_name: str | None = None
    # Stage 7: which deterministic transition policy applies the interpretation.
    transition_policy: Literal["v1", "v2"] = "v1"


def chat_model(config: InterpreterConfig, api_key: str):
    """LangChain BaseChatModel for the interpreter (OpenAI-compatible OpenRouter endpoint,
    the same class `core.llm` already uses for OpenRouter models)."""
    from langchain_openai import ChatOpenAI

    extra_body = {"usage": {"include": True}}
    if config.provider:
        extra_body["provider"] = dict(config.provider)
    headers = {"X-OpenRouter-Title": config.app_name} if config.app_name else None
    return ChatOpenAI(
        model=config.llm_model,
        api_key=api_key,
        base_url=config.base_url,
        temperature=0,
        max_tokens=config.llm_max_tokens,
        timeout=config.timeout_seconds,
        max_retries=0,  # a retry would hide provider failures from the benchmark
        extra_body=extra_body,
        default_headers=headers,
    )


def build_conversation_interpreter(
    config: InterpreterConfig, *, api_key: str | None = None, model=None
) -> ConversationInterpreter | None:
    """`model` lets tests (or another provider) inject any BaseChatModel."""
    if config.mode == "none":
        return None
    if config.mode == "rules":
        from rag_baseline.conversation_interpretation.rules import RuleBasedInterpreter

        return RuleBasedInterpreter()

    def jev():
        from rag_baseline.conversation_interpretation.jev import (
            JevDecisionInterpreter,
            JevSettings,
        )

        return JevDecisionInterpreter(
            JevSettings(
                api_key=api_key,
                model=config.jev_model,
                timeout_seconds=config.timeout_seconds,
                choice_threshold=config.jev_choice_threshold,
                noul_threshold=config.jev_noul_threshold,
                app_name=config.app_name,
                # Jev is served only by TypeSafe; chat routing preferences do not apply.
                provider={},
            )
        )

    def llm():
        from rag_baseline.conversation_interpretation.structured_llm import (
            StructuredLLMInterpreter,
        )

        if model is None and not api_key:
            raise ValueError("The structured interpreter requires an API key or a model.")
        return StructuredLLMInterpreter(
            model if model is not None else chat_model(config, api_key),
            method=config.llm_method,
            model_name=config.llm_model,
            provider_settings=dict(config.provider),
        )

    if config.mode == "jev":
        return jev()
    if config.mode == "structured_llm":
        return llm()
    from rag_baseline.conversation_interpretation.hybrid import HybridInterpreter

    return HybridInterpreter(jev(), llm())


def build_transition_policy(config: InterpreterConfig):
    if config.transition_policy == "v2":
        from rag_baseline.conversation_interpretation.transition_v2 import TransitionPolicyV2

        return TransitionPolicyV2()
    from rag_baseline.conversation_interpretation.transition import (
        ConversationTransitionPolicy,
    )

    return ConversationTransitionPolicy()
