import json

import httpx
import pytest

from rag_baseline.citation_contracts import CitedAnswer
from rag_baseline.citation_verifier import PARTIAL_NOTICE
from rag_baseline.content_locators import ContentLocatorPolicy
from rag_baseline.grounding import (
    EvidenceState,
    GenerationConstraints,
    KnownRelation,
    TemporalGroundingContext,
)
from rag_baseline.normative_output import FALLBACK_BODY
from rag_baseline.openrouter import OpenRouterClient, OpenRouterError
from rag_baseline.service import RagService
from tests.rag_baseline.test_citation_verifier import ROOT, claim
from tests.rag_baseline.test_evidence_spans import chunk


def grounding(c):
    return TemporalGroundingContext(
        temporal_intent="indeterminate",
        requested_time_context={},
        known_relations=[],
        evidence_states=[
            EvidenceState(
                chunk_id=c.id,
                source_norm="ufpi-177-2012",
                source_article=c.article_number,
                temporal_action="kept",
                normative_status="desconhecida",
                temporal_role="eligible",
            )
        ],
        generation_constraints=GenerationConstraints(
            **{
                name: True
                for name, field in GenerationConstraints.model_fields.items()
                if field.annotation is bool
            },
            citation_granularity_ceiling="article",
        ),
    )


def payload(*claims, answer_type="answer", missing_user_fact=None):
    return CitedAnswer(
        answer_type=answer_type, claims=list(claims), missing_user_fact=missing_user_fact
    ).model_dump_json()


class Client:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    async def structured_chat(self, **kwargs):
        self.calls.append(kwargs)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    async def chat(self, **kwargs):
        self.calls.append(kwargs)
        return "Texto livre antigo."


def service(client, **kwargs):
    return RagService(
        openrouter=client,
        vector_store=None,
        top_k=3,
        embedding_model="embed",
        llm_model="llm",
        **kwargs,
    )


async def generate(client, c=None, temporal=None, **kwargs):
    c = c or chunk("Art. 68. O recurso deve ser apresentado em 10 dias úteis.")
    return await service(client, generation_mode="cited_v3").generate(
        "Como apresentar recurso?", [c], temporal_grounding=temporal or grounding(c), **kwargs
    )


@pytest.mark.asyncio
async def test_accepted_first_call_and_schema_name():
    client = Client(payload(claim()))
    result = await generate(client, context_notice="Aviso do contexto.")
    assert result.citation_audit["action"] == "accepted"
    assert result.generation_attempts == len(client.calls) == 1
    assert client.calls[0]["schema_name"] == "CitedAnswer"
    assert client.calls[0]["model"] == "llm"
    assert "Aviso do contexto." in client.calls[0]["user_prompt"]
    assert "[TEMPORAL GROUNDING]" in client.calls[0]["user_prompt"]
    assert f"[{ROOT}]" in client.calls[0]["user_prompt"]
    assert result.output_audit.guard_version == "5"
    assert result.citation_audit["approved_claims"][0]["quotes"] == [claim().support[0].quote]
    approved = result.citation_audit["approved_claims"][0]
    assert approved["end"] - approved["start"] == len(approved["text"])


@pytest.mark.asyncio
async def test_targeted_repair_keeps_accepted_claim():
    good = claim(text="O recurso deve ser apresentado em dez dias úteis.")
    bad = claim(text="O recurso tem prazo de 99 dias úteis.", role="deadline")
    replacement = claim(role="deadline")
    client = Client(payload(good, bad), payload(replacement))
    result = await generate(client)
    assert result.citation_audit["action"] == "repaired"
    assert result.generation_attempts == len(client.calls) == 2
    request = result.citation_audit["repair"]["request"]
    assert [entry["index"] for entry in request["rejected_claims"]] == [1]
    assert good.text not in client.calls[1]["user_prompt"]
    assert good.text in result.answer


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "responses",
    [
        (
            payload(claim(text="O prazo é de 99 dias.")),
            payload(claim(text="O prazo é de 99 dias.")),
        ),
        ("not json", "not json"),
        ('{"answer_type":"answer"}', '{"answer_type":"answer"}'),
    ],
)
async def test_failed_repairs_fallback_and_never_third_call(responses):
    client = Client(*responses)
    result = await generate(client)
    assert result.citation_audit["action"] == "fallback"
    assert FALLBACK_BODY in result.answer
    assert result.generation_attempts == len(client.calls) == 2
    if responses[0].startswith("not") or responses[0] == '{"answer_type":"answer"}':
        assert result.citation_audit["structured_output_error"]


@pytest.mark.asyncio
async def test_invalid_json_can_be_repaired():
    result = await generate(Client("{", payload(claim())))
    assert result.citation_audit["action"] == "repaired"
    assert result.citation_audit["repair"]["request"]["structured_output_error"]


@pytest.mark.asyncio
async def test_guard_violation_mapped_to_claim():
    bad = claim(text="A norma está em vigor.")
    result = await generate(Client(payload(bad), payload(bad)))
    assert result.citation_audit["action"] == "fallback"
    assert (
        "guard:unsupported_current_validity" in result.citation_audit["first_verdicts"][0]["codes"]
    )
    assert result.citation_audit["guard_violations"][0]["claim_indices"] == [0]


@pytest.mark.asyncio
async def test_verified_subdivision_and_unverified_still_rejected():
    c = chunk(
        "Art. 68. A coordenação recebe o pedido.\n§ 2º O recurso deve ser apresentado em 10 dias úteis."
    )
    verified = claim(text="O § 2º do art. 68 prevê recurso em 10 dias úteis.", span_id=ROOT + ":p2")
    result = await generate(Client(payload(verified)), c)
    assert result.citation_audit["action"] == "accepted"
    assert not result.output_audit.guard_violations
    unsupported = claim(text="O § 9º do art. 68 prevê recurso em 10 dias úteis.")
    result = await generate(Client(payload(unsupported), payload(unsupported)), c)
    assert result.citation_audit["action"] == "fallback"
    assert "guard:unvalidated_subdivision" in result.citation_audit["first_verdicts"][0]["codes"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mode,grounded", [("free_text_v2", True), ("cited_v3", False), ("free_text_v2", False)]
)
async def test_legacy_paths_unchanged(mode, grounded):
    client = Client()
    c = chunk("Art. 68. Texto de contexto.")
    result = await service(client, generation_mode=mode).generate(
        "Pergunta", [c], temporal_grounding=grounding(c) if grounded else None
    )
    assert result.citation_audit is None
    assert "citation_audit" not in result.model_dump()
    assert "schema" not in client.calls[0]
    assert "Texto livre antigo." in result.answer


@pytest.mark.asyncio
@pytest.mark.parametrize("when", ["initial", "repair"])
async def test_provider_error_is_audited_fallback(when):
    responses = [OpenRouterError("offline")]
    if when == "repair":
        responses.insert(0, payload(claim(text="O prazo é de 99 dias.")))
    client = Client(*responses)
    result = await generate(client)
    assert result.citation_audit["action"] == "fallback"
    assert result.output_audit.regeneration_error == "OpenRouterError"
    assert result.generation_attempts == len(responses)


@pytest.mark.asyncio
async def test_openrouter_schema_name_payload_uses_mock_transport():
    sent = []

    def respond(request):
        sent.append(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": "{}"}}]})

    client = OpenRouterClient(
        api_key="fake",
        embedding_model="embed",
        llm_model="llm",
        transport=httpx.MockTransport(respond),
    )
    args = dict(system_prompt="system", user_prompt="user", schema={}, model="llm")
    await client.structured_chat(**args)
    await client.structured_chat(**args, schema_name="CitedAnswer")
    assert [p["response_format"]["json_schema"]["name"] for p in sent] == [
        "RouterDecision",
        "CitedAnswer",
    ]


@pytest.mark.asyncio
async def test_literal_support_respects_amending_article_and_authorizes_ordinary_article():
    from rag_baseline.normative_output import normative_references

    c = chunk(
        "Art. 68. A coordenação recebe o pedido.\n§ 2º O recurso deve ser apresentado em 10 dias úteis."
    )
    temporal = grounding(c).model_copy(
        update={
            "known_relations": [
                KnownRelation(
                    relation="AMENDED_BY",
                    source_norm="ufpi-1-2000",
                    target_norm="ufpi-177-2012",
                    evidence_source="Resolução 177/2012",
                    evidence_article="68",
                )
            ]
        }
    )
    _, base = ContentLocatorPolicy.for_generation(
        "Como apresentar recurso?", temporal, normative_references([c], temporal), [c]
    )
    assert not any(p.subdivision_type == "paragraph" for p in base)
    verified = claim(text="O § 2º do art. 68 prevê recurso em 10 dias úteis.", span_id=ROOT + ":p2")
    result = await generate(Client(payload(verified), payload(verified)), c, temporal)
    assert "guard:unvalidated_subdivision" in result.citation_audit["first_verdicts"][0]["codes"]
    assert verified.text not in result.answer
    assert not any(
        p.subdivision_value == "2" and p.subdivision_type == "paragraph"
        for p in result.output_audit.allowed_content_locators
    )
    ordinary = temporal.model_copy(update={"known_relations": []})
    result = await generate(Client(payload(verified)), c, ordinary)
    assert result.citation_audit["action"] == "accepted"
    assert verified.text in result.answer
    assert any(
        p.subdivision_value == "2" and "Literal quotation" in p.authorization_reason
        for p in result.output_audit.allowed_content_locators
    )
    unverified = verified.model_copy(update={"support": claim().support})
    result = await generate(Client(payload(unverified), payload(unverified)), c, temporal)
    assert "guard:unvalidated_subdivision" in result.citation_audit["first_verdicts"][0]["codes"]


@pytest.mark.asyncio
async def test_rejected_peripheral_is_omitted_without_repair():
    # Only essential claims with non-citation rejections trigger an LLM repair.
    bad = claim(text="O prazo é de 99 dias.", role="context")
    result = await generate(Client(payload(claim(), bad)))
    assert result.generation_attempts == 1
    assert result.citation_audit["repair"] is None
    assert result.citation_audit["action"] == "partial"
    assert result.normative_output.status == "regenerated"
    assert PARTIAL_NOTICE in result.answer
    assert "99" not in result.answer
    assert [c["index"] for c in result.citation_audit["omitted_claims"]] == [1]
    assert [c["index"] for c in result.citation_audit["approved_claims"]] == [0]


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["insufficient", "needs_user_fact"])
async def test_non_answer_dispositions(kind):
    item = claim(role="condition")
    # An abstention carries no claims; a labelled abstention with verified claims is
    # covered in test_citation_robustness.
    items = () if kind == "insufficient" else (item,)
    result = await generate(
        Client(payload(*items, answer_type=kind, missing_user_fact="Informe seu curso."))
    )
    assert result.citation_audit["action"] == kind
    assert result.generation_attempts == 1
    if kind == "insufficient":
        assert item.text not in result.answer
        assert result.citation_audit["approved_claims"] == []
    else:
        assert item.text in result.answer and "Informe seu curso." in result.answer


@pytest.mark.asyncio
async def test_missing_conclusion_falls_back_without_unnecessary_call():
    result = await generate(Client(payload(claim(role="context"))))
    assert result.citation_audit["disposition_codes"] == ["missing_conclusion"]
    assert result.citation_audit["action"] == "fallback"
    assert result.generation_attempts == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "replacement,action,structured_error",
    [
        # A rejected conclusion with no replacement of its role stays rejected.
        (payload(), "fallback", False),
        (payload(claim(role="context")), "fallback", False),
        # Only the requested replacement is used; extra claims are ignored.
        (payload(claim(), claim()), "repaired", False),
        # The kind of answer cannot change in a repair.
        (payload(answer_type="insufficient"), "fallback", True),
    ],
)
async def test_repair_pairs_replacements_by_role(replacement, action, structured_error):
    result = await generate(Client(payload(claim(text="O prazo é de 99 dias.")), replacement))
    assert result.citation_audit["action"] == action
    assert bool(result.citation_audit["structured_output_error"]) is structured_error
    assert result.generation_attempts == 2


@pytest.mark.asyncio
async def test_final_composed_body_still_passes_guard_or_falls_back():
    result = await generate(
        Client(
            payload(
                claim(role="condition"),
                answer_type="needs_user_fact",
                missing_user_fact="A norma está em vigor.",
            )
        )
    )
    assert result.citation_audit["action"] == "fallback"
    assert any(
        v["phase"] == "discarded_missing_user_fact" and v["code"] == "unsupported_current_validity"
        for v in result.citation_audit["guard_violations"]
    )


@pytest.mark.asyncio
async def test_offsets_identify_second_claim_after_a_rejected_first():
    bad = claim(text="O prazo é de 99 dias.", role="context")
    temporal = claim(text="A norma está em vigor.")
    result = await generate(Client(payload(bad, temporal), payload(bad, temporal)))
    violations = [
        v
        for v in result.citation_audit["guard_violations"]
        if v["phase"] == "first" and v["code"] == "unsupported_current_validity"
    ]
    assert violations and all(v["claim_indices"] == [1] for v in violations)
    for v in result.output_audit.guard_violations:
        assert result.output_audit.raw_answer[v.start : v.end] == v.excerpt


@pytest.mark.asyncio
async def test_default_mode_matches_explicit_v2_serialization_and_prompts():
    c = chunk("Art. 68. Texto de contexto.")
    default, explicit = Client(), Client()
    a = await service(default).generate("Pergunta", [c], temporal_grounding=grounding(c))
    b = await service(explicit, generation_mode="free_text_v2").generate(
        "Pergunta", [c], temporal_grounding=grounding(c)
    )
    assert a.model_dump_json() == b.model_dump_json()
    assert default.calls == explicit.calls


@pytest.mark.asyncio
async def test_source_display_ceiling_does_not_drop_other_eligible_articles():
    first = chunk("Art. 68. A coordenação recebe o pedido.")
    second = chunk(
        "Art. 69. O recurso deve ser apresentado em 10 dias úteis.",
        id="c2",
        article_number="69",
        article_label="Art. 69",
        rank=2,
    )
    temporal = grounding(first)
    temporal = temporal.model_copy(
        update={
            "evidence_states": [
                *temporal.evidence_states,
                temporal.evidence_states[0].model_copy(
                    update={"chunk_id": "c2", "source_article": "69"}
                ),
            ],
            "generation_constraints": temporal.generation_constraints.model_copy(
                update={"citation_granularity_ceiling": "source"}
            ),
        }
    )
    client = Client(payload(claim(span_id="ufpi-177-2012:art69")))
    result = await service(client, generation_mode="cited_v3").generate(
        "Como apresentar recurso?", [first, second], temporal_grounding=temporal
    )
    assert result.citation_audit["action"] == "accepted"
    assert "[ufpi-177-2012:art69]" in client.calls[0]["user_prompt"]
    assert len(result.normative_output.references) == 1
    assert result.normative_output.references[0].article is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "text,quote,bad",
    [
        (
            "Art. 68. O recurso tem prazo de 1 dia corrido.",
            "O recurso tem prazo de 1 dia corrido.",
            "O recurso tem prazo de 1 dia letivo.",
        ),
        (
            "Art. 68. O recurso tem prazo de 10 dias úteis. A revisão tem prazo de 10 dias corridos.",
            "O recurso tem prazo de 10 dias úteis.",
            "O recurso tem prazo de dez (10) dias corridos.",
        ),
    ],
)
async def test_deadline_qualification_rejection_survives_global_guard_evidence(text, quote, bad):
    item = claim(text=bad, quote=quote)
    result = await generate(Client(payload(item), payload(item)), chunk(text))
    assert result.citation_audit["action"] == "fallback"
    assert "deadline_qualifier_mismatch" in result.citation_audit["first_verdicts"][0]["codes"]
    assert result.generation_attempts == 2
