"""Final delivery of the core's typed authority, without model synthesis."""

from langchain_core.messages import AIMessage

from rag_baseline.agent_tool import validated_result
from rag_baseline.tool_contracts import NormativeToolResult, ToolStatus


class AuthoritativeEmissionGate:
    def emit(self, result: NormativeToolResult) -> AIMessage:
        result = validated_result(result)
        if result.status == ToolStatus.ANSWER:
            content = result.answer
        elif result.status == ToolStatus.CLARIFICATION:
            content = result.clarification_question
        else:
            content = result.safe_message
        # The validated discriminated contract requires a nonempty string here.
        assert content is not None
        return AIMessage(content=content)
