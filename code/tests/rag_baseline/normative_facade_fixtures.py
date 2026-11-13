"""Hand-built transport fixtures; no provider or persisted corpus writes."""

from rag_baseline.models import QueryResult

CORRELATION = "8ab5d1af-9708-4555-a442-bf8c8a744c91"
FINAL = "Resposta final do núcleo.\nFontes oficiais: Resolução 177/2012, art. 68."


def provenance():
    return {
        "temporal_intent": "historical",
        "requested_time_context": {
            "norm_ids": [],
            "before_amendment": True,
            "relation_query": None,
            "article": "68",
            "paragraph": None,
            "requested_year": None,
        },
        "evidence_states": [
            {
                "chunk_id": "ufpi-177-2012-68",
                "source_norm": "ufpi-177-2012",
                "source_article": "68",
                "temporal_action": "historical_preserved",
                "normative_status": "desconhecida",
                "temporal_role": "historical",
                "relation_source": None,
            }
        ],
        "known_relations": [],
        "generation_constraints": {
            "must_frame_as_historical": True,
            "must_not_claim_current_validity": True,
            "must_not_claim_unknown_as_current": True,
            "must_not_present_revoked_rule_as_current": True,
            "must_not_present_successor_as_historical_predecessor": True,
            "must_separate_temporal_states": False,
            "must_follow_evidence_roles": True,
            "must_not_treat_partial_amendment_as_total_revocation": True,
            "must_not_duplicate_superseded_wording": True,
            "must_not_reintroduce_excluded_evidence": True,
            "must_not_deny_present_evidence": True,
            "must_not_invent_effective_date": True,
            "must_not_invent_temporal_scope": True,
            "citation_granularity_ceiling": "article",
        },
    }


def answer_data():
    return dict(
        contract_version="1",
        core_version="structured_output_v2",
        status="ANSWER",
        answer=FINAL,
        references=[
            dict(
                chunk_id="ufpi-177-2012-68",
                norm_id="ufpi-177-2012",
                source="Resolução 177/2012",
                article="68",
                validated_subdivision=None,
                display_text="Resolução 177/2012, art. 68",
                temporal_role="historical",
            )
        ],
        temporal_provenance=provenance(),
        temporal_status_text="Contexto histórico.",
        allowed_temporal_facts={"items": [{"kind": "HISTORICAL_CONTEXT"}]},
        core_status="accepted",
        domain="graduacao",
        retrieval_strategy="dense_vector",
        needs_clarification=False,
        clarification_question=None,
        correlation_id=CORRELATION,
    )


def audit_data():
    return dict(
        response_kind="generated",
        generation_attempts=1,
        output_audit=dict(
            raw_answer="UNSAFE RAW",
            guard_violations=[],
            regenerated_answer=None,
            second_guard_violations=[],
            final_answer=FINAL,
            guard_action="accepted",
            guard_version="5",
        ),
        exception_type=None,
    )


def core_answer():
    data = answer_data()
    return QueryResult(
        answer=FINAL,
        references=[
            dict(
                rank=1,
                article_number="68",
                source="Resolução 177/2012",
                sector="graduacao",
                content="FULL CHUNK EVIDENCE",
                distance=0.1,
            )
        ],
        llm_model="fake",
        embedding_model="fake",
        selected_scope="graduacao",
        needs_clarification=False,
        route=dict(
            scope="graduacao",
            needs_clarification=False,
            clarification_question=None,
            reason_code="explicit_graduacao",
        ),
        version_filter={"enabled": True},
        normative_output={
            "references": data["references"],
            "temporal_provenance": data["temporal_provenance"],
            "temporal_status_text": data["temporal_status_text"],
            "allowed_temporal_facts": data["allowed_temporal_facts"],
            "status": "accepted",
        },
        output_audit=audit_data()["output_audit"],
    )
