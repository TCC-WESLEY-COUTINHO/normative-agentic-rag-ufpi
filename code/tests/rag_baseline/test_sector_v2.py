from types import SimpleNamespace

import pytest

from agents import tools_v2
from rag_baseline.corpus import build_embedding_text, normalize_chunk
from rag_baseline.models import RetrievedChunk
from rag_baseline.service import _context, _reference
from rag_baseline.vector_store import ChromaVectorStore


def raw(sector=None, source="Norma pós", article="20"):
    metadata = {"fonte": source, "artigo_numero": article, "artigo": f"Art. {article}"}
    if sector is not None:
        metadata["setor"] = sector
    return {"conteudo": "Regra verificável.", "metadados": metadata}


def test_sector_survives_loader_embedding_context_and_reference():
    chunk = normalize_chunk(raw("pos_graduacao"), 0, id_prefix="post")
    assert chunk.sector == "pos_graduacao"
    assert "Setor: pos_graduacao" in build_embedding_text(chunk, norm_name="Norma pós")
    retrieved = RetrievedChunk(**chunk.model_dump(), rank=1, distance=0)
    assert "Setor: pos_graduacao" in _context([retrieved])
    assert _reference(retrieved).sector == "pos_graduacao"


def test_absent_sector_is_unknown_not_graduation():
    assert normalize_chunk(raw(), 0).sector is None


def test_invalid_sector_is_rejected():
    with pytest.raises(ValueError):
        normalize_chunk(raw("inventado"), 0)


def test_sector_filter_prevents_article_collision_in_real_chroma(tmp_path):
    store = ChromaVectorStore(tmp_path, "sector_test")
    chunks = [
        normalize_chunk(raw("graduacao", "Grad"), 0, id_prefix="grad"),
        normalize_chunk(raw("pos_graduacao", "Pós"), 0, id_prefix="post"),
    ]
    store.upsert(chunks, [[1.0, 0.0], [0.0, 1.0]])
    assert len(store.query([1.0, 0.0], 5)) == 2
    result = store.query([1.0, 0.0], 5, sector="pos_graduacao")
    assert len(result) == 1 and result[0].id.startswith("post-")


class RpcRecorder:
    def __init__(self):
        self.calls = []

    def rpc(self, name, payload):
        self.calls.append((name, payload))
        filters = payload["filtros_metadados"]
        source = filters.get("fonte", "Pós")
        rows = [
            {
                "id": f"{source}-{n}",
                "conteudo": f"Regra {source} {n}",
                "similarity": 1 - n / 100,
                "metadados": {
                    "fonte": source,
                    "setor": "pos_graduacao",
                    "artigo_numero": str(n),
                    "artigo": f"Art. {n}",
                },
            }
            for n in range(1, 11)
        ]
        return SimpleNamespace(execute=lambda: SimpleNamespace(data=rows))


def setup_clients(monkeypatch):
    rpc = RpcRecorder()
    monkeypatch.setattr(tools_v2, "_init_clients", lambda: (object(), rpc))
    monkeypatch.setattr(tools_v2, "_create_embedding", lambda *a, **k: [1.0, 0.0])
    return rpc


def test_metadata_search_does_not_add_graduation_source(monkeypatch):
    rpc = setup_clients(monkeypatch)
    tools_v2.supabase_metadata_search_func(artigo_numero="20")
    assert rpc.calls[0][1]["filtros_metadados"] == {"artigo_numero": "20"}


def test_semantic_sector_and_two_sources_are_forwarded_with_global_limit(monkeypatch):
    rpc = setup_clients(monkeypatch)
    output = tools_v2.supabase_semantic_search_func(
        "pergunta", setor="pos_graduacao", fontes=["A", "B"]
    )
    assert [c[1]["filtros_metadados"] for c in rpc.calls] == [
        {"setor": "pos_graduacao", "fonte": "A"},
        {"setor": "pos_graduacao", "fonte": "B"},
    ]
    assert "Regra A 1" in output and "Regra B 1" in output
    assert "Regra A 3" not in output and "Regra B 3" not in output


def test_metadata_union_keeps_ten_total_and_preserves_same_article_across_sources(monkeypatch):
    rpc = setup_clients(monkeypatch)
    output = tools_v2.supabase_metadata_search_func(fontes=["A", "B"], artigo_numero="1")
    assert len(rpc.calls) == 2
    assert all(c[1]["match_count"] == 10 for c in rpc.calls)
    assert "Regra A 1" in output and "Regra B 1" in output
    assert "Regra A 6" not in output and "Regra B 6" not in output


def test_invalid_sector_fails_before_remote_calls(monkeypatch):
    rpc = setup_clients(monkeypatch)
    with pytest.raises(ValueError):
        tools_v2.supabase_semantic_search_func("pergunta", setor="errado")
    assert not rpc.calls


def test_post_chapter_does_not_require_nonexistent_title(monkeypatch):
    rpc = setup_clients(monkeypatch)
    output = tools_v2.supabase_metadata_search_func(setor="pos_graduacao", capitulo_numero="II")
    assert "ERRO" not in output
    assert rpc.calls[0][1]["filtros_metadados"] == {
        "setor": "pos_graduacao",
        "capitulo_numero": "II",
    }


def test_source_only_post_scope_accepts_chapter(monkeypatch):
    rpc = setup_clients(monkeypatch)
    output = tools_v2.supabase_metadata_search_func(
        fonte="Resolução CEPEX/UFPI nº 956/2025", capitulo_numero="II"
    )
    assert "ERRO" not in output
    assert rpc.calls[0][1]["filtros_metadados"] == {
        "fonte": "Resolução CEPEX/UFPI nº 956/2025",
        "capitulo_numero": "II",
    }


def test_legacy_grad_source_still_requires_title(monkeypatch):
    rpc = setup_clients(monkeypatch)
    output = tools_v2.supabase_metadata_search_func(
        fonte="Regulamento Geral da Graduação da UFPI", capitulo_numero="II"
    )
    assert "ERRO DE HIERARQUIA" in output
    assert not rpc.calls
