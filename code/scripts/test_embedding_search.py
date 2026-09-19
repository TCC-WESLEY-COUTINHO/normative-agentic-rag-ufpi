import os
import sys
import json
import argparse
from typing import Optional, Dict, Any

from dotenv import load_dotenv
from openai import OpenAI
from supabase import create_client, Client


def get_env(var_name: str, required: bool = True) -> Optional[str]:
    value = os.getenv(var_name)
    if required and not value:
        print(f"[ERRO] Variável de ambiente ausente: {var_name}")
        sys.exit(1)
    return value


def create_clients() -> tuple[OpenAI, Client]:
    load_dotenv()
    openai_api_key = get_env("OPENAI_API_KEY")
    supabase_url = get_env("SUPABASE_URL")
    supabase_key = get_env("SUPABASE_KEY")

    openai_client = OpenAI(api_key=openai_api_key)
    supabase_client: Client = create_client(supabase_url, supabase_key)
    return openai_client, supabase_client


def create_embedding(openai_client: OpenAI, text: str, model: str = "text-embedding-3-small") -> list[float]:
    resp = openai_client.embeddings.create(model=model, input=text)
    return resp.data[0].embedding


def call_match_function(
    supabase_client: Client,
    fn_name: str,
    query_embedding: list[float],
    match_threshold: float,
    match_count: int,
    filtros_metadados: Optional[Dict[str, Any]] = None,
):
    payload = {
        "query_embedding": query_embedding,
        "match_threshold": match_threshold,
        "match_count": match_count,
    }

    # v2 usa filtros_metadados, a antiga pode usar o mesmo nome
    if filtros_metadados is None:
        filtros_metadados = {}
    payload["filtros_metadados"] = filtros_metadados

    return supabase_client.rpc(fn_name, payload).execute()


def table_stats(supabase_client: Client) -> dict:
    # Obtém contagem total e uma amostra de metadados para diagnóstico
    count = supabase_client.table("documentos_embeddings").select("id", count="exact").execute()
    sample = (
        supabase_client.table("documentos_embeddings")
        .select("id, metadados")
        .limit(3)
        .execute()
    )
    return {
        "total_registros": count.count if hasattr(count, "count") else None,
        "amostra_metadados": getattr(sample, "data", None),
    }


def main():
    parser = argparse.ArgumentParser(
        description="Testa a recuperação vetorial no Supabase usando embeddings OpenAI."
    )
    parser.add_argument("--query", required=True, help="Consulta em linguagem natural.")
    parser.add_argument("--threshold", type=float, default=0.7, help="Limite de similaridade (0-1).")
    parser.add_argument("--k", type=int, default=5, help="Quantidade de resultados.")
    parser.add_argument(
        "--fonte",
        type=str,
        default=None,
        help="Filtro de fonte (opcional). Usa metadados->>'fonte'.",
    )
    parser.add_argument(
        "--function",
        type=str,
        default="match_documentos_v2",
        choices=["match_documentos_v2", "match_documentos", "auto"],
        help="Função SQL a usar (auto tenta v2 e cai para antiga).",
    )
    parser.add_argument(
        "--model",
        type=str,
        default="text-embedding-3-small",
        help="Modelo de embeddings (dimensão deve bater com a coluna VECTOR).",
    )

    args = parser.parse_args()

    openai_client, supabase_client = create_clients()

    # Diagnóstico rápido da tabela
    stats = table_stats(supabase_client)
    print("== Diagnóstico da Tabela ==")
    print(json.dumps(stats, ensure_ascii=False, indent=2))

    print("\n== Gerando embedding da query ==")
    query_emb = create_embedding(openai_client, args.query, model=args.model)
    print(f"Embedding gerado. Dimensão: {len(query_emb)}")

    filtros = {}
    if args.fonte:
        filtros["fonte"] = args.fonte

    fn_order = []
    if args.function == "auto":
        fn_order = ["match_documentos_v2", "match_documentos"]
    else:
        fn_order = [args.function]

    last_error: Optional[Exception] = None
    result = None
    for fn in fn_order:
        print(f"\n== Chamando função: {fn} ==")
        try:
            result = call_match_function(
                supabase_client,
                fn,
                query_embedding=query_emb,
                match_threshold=args.threshold,
                match_count=args.k,
                filtros_metadados=filtros,
            )
            break
        except Exception as e:
            last_error = e
            print(f"[AVISO] Falha ao chamar {fn}: {e}")

    if result is None:
        print("\n[ERRO] Nenhuma função pôde ser chamada com sucesso.")
        if last_error:
            print(f"Último erro: {last_error}")
        sys.exit(2)

    data = getattr(result, "data", [])
    print(f"\n== Resultados (top {args.k}) ==")
    if not data:
        print("Nenhum resultado acima do threshold. Tente reduzir --threshold ou revisar os dados.")
        sys.exit(0)

    for i, row in enumerate(data, start=1):
        similarity = row.get("similarity")
        conteudo = row.get("conteudo", "")
        metadados = row.get("metadados", {})
        artigo = None
        if isinstance(metadados, dict):
            artigo = metadados.get("artigo")

        print(f"\n[{i}] similarity={similarity:.4f}")
        if artigo:
            print(f"artigo={artigo}")
        print(f"fonte={metadados.get('fonte') if isinstance(metadados, dict) else None}")
        print("conteudo_preview=\n" + (conteudo[:400].replace("\n", " ") + ("..." if len(conteudo) > 400 else "")))


if __name__ == "__main__":
    main()


