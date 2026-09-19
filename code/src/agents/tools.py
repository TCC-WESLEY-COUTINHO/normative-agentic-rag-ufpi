import logging
import math
import os
import re
from datetime import datetime
from typing import Any, Dict, Optional

import numexpr
from dotenv import load_dotenv
from langchain_chroma import Chroma
from langchain_core.tools import BaseTool, tool
from langchain_openai import OpenAIEmbeddings
from openai import OpenAI
from supabase import Client, create_client


# Logger para a tool de RAG
logger = logging.getLogger(__name__)

def calculator_func(expression: str) -> str:
    """Calculates a math expression using numexpr.

    Useful for when you need to answer questions about math using numexpr.
    This tool is only for math questions and nothing else. Only input
    math expressions.

    Args:
        expression (str): A valid numexpr formatted math expression.

    Returns:
        str: The result of the math expression.
    """

    try:
        local_dict = {"pi": math.pi, "e": math.e}
        output = str(
            numexpr.evaluate(
                expression.strip(),
                global_dict={},  # restrict access to globals
                local_dict=local_dict,  # add common mathematical functions
            )
        )
        return re.sub(r"^\[|\]$", "", output)
    except Exception as e:
        raise ValueError(
            f'calculator("{expression}") raised error: {e}.'
            " Please try again with a valid numerical expression"
        )


calculator: BaseTool = tool(calculator_func)
calculator.name = "Calculator"


def get_current_datetime_func() -> str:
    """Retorna a data e hora atual em um formato contextual e legível.

    Useful for when you need to answer questions about current date and time.
    Returns date and time in a contextual format suitable for Brazilian Portuguese context.

    Returns:
        str: Data e hora formatada no formato: "DD de Mês de YYYY, HH:MM"
    """
    now = datetime.now()
    
    # Mapeamento de meses em português
    meses = {
        1: "janeiro", 2: "fevereiro", 3: "março", 4: "abril",
        5: "maio", 6: "junho", 7: "julho", 8: "agosto",
        9: "setembro", 10: "outubro", 11: "novembro", 12: "dezembro"
    }
    
    dia = now.day
    mes_nome = meses[now.month]
    ano = now.year
    hora = now.hour
    minuto = now.minute
    
    # Formata a data: "15 de janeiro de 2024, 14:30"
    data_formatada = f"{dia} de {mes_nome} de {ano}, {hora:02d}:{minuto:02d}"
    
    return data_formatada


get_current_datetime: BaseTool = tool(get_current_datetime_func)
get_current_datetime.name = "GetCurrentDateTime"


# Format retrieved documents
def format_contexts(docs):
    return "\n\n".join(doc.page_content for doc in docs)


def load_chroma_db():
    # Create the embedding function for our project description database
    try:
        embeddings = OpenAIEmbeddings()
    except Exception as e:
        raise RuntimeError(
            "Failed to initialize OpenAIEmbeddings. Ensure the OpenAI API key is set."
        ) from e

    # Load the stored vector database
    chroma_db = Chroma(persist_directory="./chroma_db", embedding_function=embeddings)
    retriever = chroma_db.as_retriever(search_kwargs={"k": 5})
    return retriever


def database_search_func(query: str) -> str:
    """Searches chroma_db for information in the company's handbook."""
    # Get the chroma retriever
    retriever = load_chroma_db()

    # Search the database for relevant documents
    documents = retriever.invoke(query)

    # Format the documents into a string
    context_str = format_contexts(documents)

    return context_str


database_search: BaseTool = tool(database_search_func)
database_search.name = "Database_Search"  # Update name with the purpose of your database


# ------------------------------
# Supabase RAG Search (vector DB)
# ------------------------------

# Fixos (controlados somente via código)
_RAG_MODEL = "text-embedding-3-small"
_RAG_FUNCTION = "match_documentos_v2"
_RAG_THRESHOLD = 0.4
_RAG_K = 4

_openai_client: Optional[OpenAI] = None
_supabase_client: Optional[Client] = None


def _init_clients() -> tuple[OpenAI, Client]:
    global _openai_client, _supabase_client
    if _openai_client is not None and _supabase_client is not None:
        logger.info("[RAG] Clientes já inicializados (cache).")
        return _openai_client, _supabase_client

    # Carrega .env apenas uma vez
    load_dotenv()

    openai_api_key = os.getenv("OPENAI_API_KEY")
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_KEY")

    if not openai_api_key:
        raise RuntimeError("OPENAI_API_KEY não definido no ambiente.")
    if not supabase_url or not supabase_key:
        raise RuntimeError("SUPABASE_URL/SUPABASE_KEY não definidos no ambiente.")

    _openai_client = OpenAI(api_key=openai_api_key)
    _supabase_client = create_client(supabase_url, supabase_key)
    logger.info("[RAG] Clientes OpenAI e Supabase inicializados com sucesso.")
    return _openai_client, _supabase_client


def _create_embedding(openai_client: OpenAI, text: str, model: str = _RAG_MODEL) -> list[float]:
    logger.info(f"[RAG] Gerando embedding | model={model} | len(text)={len(text)}")
    resp = openai_client.embeddings.create(model=model, input=text)
    emb = resp.data[0].embedding
    logger.info(f"[RAG] Embedding gerado | dim={len(emb)}")
    return emb


def _call_rag_function(
    supabase_client: Client,
    fn_name: str,
    query_embedding: list[float],
    match_threshold: float,
    match_count: int,
    filtros_metadados: Optional[Dict[str, Any]] = None,
):
    payload: Dict[str, Any] = {
        "query_embedding": query_embedding,
        "match_threshold": match_threshold,
        "match_count": match_count,
        "filtros_metadados": filtros_metadados or {},
    }
    filtros_count = len((filtros_metadados or {}).keys())
    logger.info(
        f"[RAG] Chamando RPC | fn={fn_name} | threshold={match_threshold} | k={match_count} | filtros={filtros_count} | emb_dim={len(query_embedding)}"
    )
    return supabase_client.rpc(fn_name, payload).execute()


def _format_rag_results(rows: list[Dict[str, Any]]) -> str:
    if not rows:
        logger.info("[RAG] Nenhuma linha retornada pela RPC.")
        return ""
    logger.info(f"[RAG] Linhas retornadas: {len(rows)} (mostrando até {_RAG_K})")
    formatted_parts: list[str] = []
    for row in rows[:_RAG_K]:
        similarity = row.get("similarity")
        conteudo = row.get("conteudo", "") or ""
        metadados = row.get("metadados", {}) or {}
        
        # Extrai todos os metadados disponíveis
        artigo = None
        fonte = None
        titulo = None
        capitulo = None
        secao = None
        subsecao = None
        
        if isinstance(metadados, dict):
            artigo = metadados.get("artigo")
            fonte = metadados.get("fonte")
            titulo = metadados.get("titulo")
            capitulo = metadados.get("capitulo")
            secao = metadados.get("secao")
            subsecao = metadados.get("subsecao")
        
        # Log completo dos metadados para debugging
        logger.info(
            f"[RAG] Item | sim={similarity} | artigo={artigo} | fonte={fonte} | "
            f"titulo={titulo[:50] if titulo else '(vazio)'} | capitulo={capitulo[:50] if capitulo else '(vazio)'} | "
            f"secao={secao[:50] if secao else '(vazio)'} | subsecao={subsecao[:50] if subsecao else '(vazio)'} | "
            f"conteudo_len={len(conteudo)}"
        )

        # Monta o header com informações hierárquicas
        header_lines = []
        
        # Linha 1: Similaridade e Artigo
        first_line_bits = []
        if similarity is not None:
            try:
                first_line_bits.append(f"similarity={float(similarity):.4f}")
            except Exception:
                first_line_bits.append(f"similarity={similarity}")
        if artigo:
            first_line_bits.append(f"artigo={artigo}")
        if first_line_bits:
            header_lines.append(" | ".join(first_line_bits))
        
        # Linha 2: Hierarquia do documento (Título → Capítulo → Seção → Subseção)
        hierarchy_lines = []
        if titulo:
            hierarchy_lines.append(f"Título: {titulo}")
        if capitulo:
            hierarchy_lines.append(f"Capítulo: {capitulo}")
        if secao:
            hierarchy_lines.append(f"Seção: {secao}")
        if subsecao:
            hierarchy_lines.append(f"Subseção: {subsecao}")
        
        if hierarchy_lines:
            header_lines.append(" → ".join(hierarchy_lines))
        
        # Adiciona o header formatado e o conteúdo
        if header_lines:
            formatted_parts.append("\n".join(header_lines))
        formatted_parts.append(conteudo)
    
    return "\n\n".join(formatted_parts)


def supabase_rag_search_func(query: str, filtros_metadados: Optional[Dict[str, Any]] = None) -> str:
    """Executa busca vetorial no Supabase com RAG.

    Recebe somente a consulta e metadados para filtragem.
    Retorna um texto com os trechos mais relevantes e metadados úteis.
    """

    logger.info("[RAG] ===== Início da busca RAG Supabase =====")
    logger.info(f"[RAG] Parâmetros fixos | model={_RAG_MODEL} | fn={_RAG_FUNCTION} | threshold={_RAG_THRESHOLD} | k={_RAG_K}")
    openai_client, supabase_client = _init_clients()
    filtros_info = (list((filtros_metadados or {}).keys()))
    logger.info(f"[RAG] Query recebida | len={len(query)} | filtros_keys={filtros_info}")
    query_emb = _create_embedding(openai_client, query, model=_RAG_MODEL)

    # Chamada direta à função configurada (sem fallback para simplicidade/eficiência)
    result = _call_rag_function(
        supabase_client,
        _RAG_FUNCTION,
        query_embedding=query_emb,
        match_threshold=_RAG_THRESHOLD,
        match_count=_RAG_K,
        filtros_metadados=filtros_metadados,
    )

    rows = getattr(result, "data", []) or []
    out = _format_rag_results(rows)
    logger.info(f"[RAG] Tamanho do texto formatado de saída: {len(out)}")
    logger.info("[RAG] ===== Fim da busca RAG Supabase =====")
    return out


supabase_rag_search: BaseTool = tool(supabase_rag_search_func)
supabase_rag_search.name = "Supabase_RAG_Search"
