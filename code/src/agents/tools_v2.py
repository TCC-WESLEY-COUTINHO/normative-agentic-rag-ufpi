# ------------------------------
# Supabase Search Tools (Dual Mode)
# ------------------------------

from typing import Optional, Dict, Any, List
from openai import OpenAI
from supabase import Client, create_client
from langchain_core.tools import BaseTool, tool
from dotenv import load_dotenv
import os
import logging

logger = logging.getLogger(__name__)

# Configurações fixas
_RAG_MODEL = "text-embedding-3-small"
_RAG_FUNCTION = "match_documentos_v2"  # Para busca semântica (com embedding)
_RAG_FUNCTION_METADATA = "match_documentos_metadados_only"  # Para busca apenas por metadados
_RAG_THRESHOLD = 0.4
_RAG_K_SEMANTIC = 4  # Para busca semântica pura
_RAG_K_METADATA = 10  # Para busca por metadados (mais resultados)

_openai_client: Optional[OpenAI] = None
_supabase_client: Optional[Client] = None


def _init_clients() -> tuple[OpenAI, Client]:
    """Inicializa clientes OpenAI e Supabase (com cache)."""
    global _openai_client, _supabase_client
    if _openai_client is not None and _supabase_client is not None:
        logger.info("[SEARCH] Clientes já inicializados (cache).")
        return _openai_client, _supabase_client

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
    logger.info("[SEARCH] Clientes OpenAI e Supabase inicializados com sucesso.")
    return _openai_client, _supabase_client


def _validate_hierarchical_filters(
    titulo_numero: Optional[str] = None,
    capitulo_numero: Optional[str] = None,
    secao_numero: Optional[str] = None,
    subsecao_numero: Optional[str] = None,
    artigo_numero: Optional[str] = None,
) -> tuple[bool, str]:
    """
    Valida a hierarquia dos filtros de metadados.
    
    Regras:
    - TÍTULO: pode ser buscado isoladamente
    - ARTIGO: pode ser buscado isoladamente (numeração única)
    - CAPÍTULO: requer TÍTULO pai
    - SEÇÃO: requer TÍTULO e CAPÍTULO pai
    - SUBSEÇÃO: requer TÍTULO, CAPÍTULO e SEÇÃO pai
    
    Returns:
        tuple[bool, str]: (válido, mensagem_erro)
    """
    
    # Artigo pode ser buscado sozinho
    if artigo_numero and not any([titulo_numero, capitulo_numero, secao_numero, subsecao_numero]):
        return True, ""
    
    # Título pode ser buscado sozinho
    if titulo_numero and not any([capitulo_numero, secao_numero, subsecao_numero, artigo_numero]):
        return True, ""
    
    # Capítulo requer Título
    if capitulo_numero and not titulo_numero:
        return False, "CAPÍTULO requer TÍTULO pai. Forneça 'titulo_numero'."
    
    # Seção requer Título e Capítulo
    if secao_numero:
        if not titulo_numero:
            return False, "SEÇÃO requer TÍTULO pai. Forneça 'titulo_numero'."
        if not capitulo_numero:
            return False, "SEÇÃO requer CAPÍTULO pai. Forneça 'capitulo_numero'."
    
    # Subseção requer Título, Capítulo e Seção
    if subsecao_numero:
        if not titulo_numero:
            return False, "SUBSEÇÃO requer TÍTULO pai. Forneça 'titulo_numero'."
        if not capitulo_numero:
            return False, "SUBSEÇÃO requer CAPÍTULO pai. Forneça 'capitulo_numero'."
        if not secao_numero:
            return False, "SUBSEÇÃO requer SEÇÃO pai. Forneça 'secao_numero'."
    
    return True, ""


def _build_metadata_filters(
    fonte: Optional[str] = None,
    titulo_numero: Optional[str] = None,
    capitulo_numero: Optional[str] = None,
    secao_numero: Optional[str] = None,
    subsecao_numero: Optional[str] = None,
    artigo_numero: Optional[str] = None,
) -> Dict[str, Any]:
    """Constrói o dicionário de filtros de metadados."""
    filtros = {}
    
    if fonte:
        filtros["fonte"] = fonte
    if titulo_numero:
        filtros["titulo_numero"] = titulo_numero
    if capitulo_numero:
        filtros["capitulo_numero"] = capitulo_numero
    if secao_numero:
        filtros["secao_numero"] = secao_numero
    if subsecao_numero:
        filtros["subsecao_numero"] = subsecao_numero
    if artigo_numero:
        filtros["artigo_numero"] = artigo_numero
    
    return filtros


def _create_embedding(openai_client: OpenAI, text: str, model: str = _RAG_MODEL) -> list[float]:
    """Gera embedding usando OpenAI."""
    logger.info(f"[SEARCH] Gerando embedding | model={model} | len(text)={len(text)}")
    resp = openai_client.embeddings.create(model=model, input=text)
    emb = resp.data[0].embedding
    logger.info(f"[SEARCH] Embedding gerado | dim={len(emb)}")
    return emb


def _call_rag_function(
    supabase_client: Client,
    fn_name: str,
    query_embedding: Optional[list[float]],
    match_threshold: float,
    match_count: int,
    filtros_metadados: Dict[str, Any],
):
    """Chama a função RPC do Supabase para busca semântica (com embedding)."""
    payload: Dict[str, Any] = {
        "query_embedding": query_embedding,
        "match_threshold": match_threshold,
        "match_count": match_count,
        "filtros_metadados": filtros_metadados,
    }
    
    logger.info(
        f"[SEARCH] Chamando RPC semântica | fn={fn_name} | threshold={match_threshold} | "
        f"k={match_count} | filtros={list(filtros_metadados.keys())}"
    )
    return supabase_client.rpc(fn_name, payload).execute()


def _call_metadata_only_function(
    supabase_client: Client,
    fn_name: str,
    match_count: int,
    filtros_metadados: Dict[str, Any],
):
    """Chama a função RPC do Supabase para busca apenas por metadados (sem embedding)."""
    payload: Dict[str, Any] = {
        "filtros_metadados": filtros_metadados,
        "match_count": match_count,
    }
    
    logger.info(
        f"[SEARCH] Chamando RPC metadados | fn={fn_name} | "
        f"k={match_count} | filtros={list(filtros_metadados.keys())}"
    )
    return supabase_client.rpc(fn_name, payload).execute()


def _format_results(rows: list[Dict[str, Any]], mode: str = "semantic") -> str:
    """
    Formata os resultados da busca.
    
    Args:
        rows: Lista de resultados do Supabase
        mode: "semantic" para busca semântica, "metadata" para busca por metadados
    """
    if not rows:
        logger.info(f"[SEARCH-{mode.upper()}] Nenhuma linha retornada pela RPC.")
        return "Nenhum resultado encontrado."
    
    logger.info(f"[SEARCH-{mode.upper()}] Linhas retornadas: {len(rows)}")
    formatted_parts: list[str] = []
    
    for idx, row in enumerate(rows, 1):
        similarity = row.get("similarity")
        conteudo = row.get("conteudo", "") or ""
        metadados = row.get("metadados", {}) or {}
        
        # Extrai metadados
        fonte = metadados.get("fonte", "")
        titulo_num = metadados.get("titulo_numero", "")
        titulo_nome = metadados.get("titulo_nome", "")
        capitulo_num = metadados.get("capitulo_numero", "")
        capitulo_nome = metadados.get("capitulo_nome", "")
        secao_num = metadados.get("secao_numero", "")
        secao_nome = metadados.get("secao_nome", "")
        subsecao_num = metadados.get("subsecao_numero", "")
        subsecao_nome = metadados.get("subsecao_nome", "")
        artigo_num = metadados.get("artigo_numero", "")
        artigo = metadados.get("artigo", "")
        
        # Monta o cabeçalho
        header_lines = [f"--- Resultado {idx} ---"]
        
        # Linha de similaridade
        if similarity is not None:
            try:
                header_lines.append(f"Similaridade: {float(similarity):.4f}")
            except Exception:
                header_lines.append(f"Similaridade: {similarity}")
        
        # Fonte
        if fonte:
            header_lines.append(f"Fonte: {fonte}")
        
        # Hierarquia completa
        hierarchy = []
        if titulo_num:
            titulo_desc = f"TÍTULO {titulo_num}"
            if titulo_nome:
                titulo_desc += f" - {titulo_nome}"
            hierarchy.append(titulo_desc)
        
        if capitulo_num:
            cap_desc = f"CAPÍTULO {capitulo_num}"
            if capitulo_nome:
                cap_desc += f" - {capitulo_nome}"
            hierarchy.append(cap_desc)
        
        if secao_num:
            sec_desc = f"SEÇÃO {secao_num}"
            if secao_nome:
                sec_desc += f" - {secao_nome}"
            hierarchy.append(sec_desc)
        
        if subsecao_num:
            subsec_desc = f"SUBSEÇÃO {subsecao_num}"
            if subsecao_nome:
                subsec_desc += f" - {subsecao_nome}"
            hierarchy.append(subsec_desc)
        
        if artigo:
            hierarchy.append(artigo)
        
        if hierarchy:
            header_lines.append("Localização: " + " → ".join(hierarchy))
        
        # Conteúdo
        header_lines.append(f"\nConteúdo:\n{conteudo}")
        
        formatted_parts.append("\n".join(header_lines))
    
    return "\n\n".join(formatted_parts)


# ============================================
# FUNÇÃO 1: BUSCA SEMÂNTICA PURA (QUERY ONLY)
# ============================================

def supabase_semantic_search_func(query: str) -> str:
    """
    Busca semântica pura no Supabase usando apenas a query.
    
    Esta ferramenta realiza busca vetorial/semântica sem filtros de metadados,
    retornando os trechos mais relevantes semanticamente para a consulta.
    
    Use esta ferramenta quando:
    - Não souber a localização exata no documento
    - Quiser explorar o conteúdo de forma ampla
    - Buscar conceitos ou temas gerais
    - Não tiver informações sobre título, capítulo, seção ou artigo
    
    Args:
        query: Texto da consulta para busca semântica (obrigatório)
    
    Returns:
        String formatada com os resultados mais relevantes
    
    Exemplos:
        1. Busca exploratória:
           supabase_semantic_search_func("como funciona a matrícula")
        
        2. Busca por conceito:
           supabase_semantic_search_func("láurea universitária requisitos")
        
        3. Busca por tema:
           supabase_semantic_search_func("desvinculação do curso")
    """
    
    logger.info("[SEMANTIC] ===== Início da busca semântica pura =====")
    logger.info(f"[SEMANTIC] Query | len={len(query)}")
    
    # Inicializa clientes
    openai_client, supabase_client = _init_clients()
    
    # Gera embedding da query
    query_emb = _create_embedding(openai_client, query, model=_RAG_MODEL)
    
    # Executa busca SEM filtros de metadados
    result = _call_rag_function(
        supabase_client,
        _RAG_FUNCTION,
        query_embedding=query_emb,
        match_threshold=_RAG_THRESHOLD,
        match_count=_RAG_K_SEMANTIC,
        filtros_metadados={},  # SEM FILTROS
    )
    
    rows = getattr(result, "data", []) or []
    out = _format_results(rows, mode="semantic")
    
    logger.info(f"[SEMANTIC] Tamanho do texto formatado: {len(out)}")
    logger.info("[SEMANTIC] ===== Fim da busca semântica pura =====")
    
    return out


# ================================================
# FUNÇÃO 2: BUSCA POR METADADOS (METADATA FILTERS)
# ================================================

def supabase_metadata_search_func(
    fonte = "Regulamento Geral da Graduação da UFPI",
    titulo_numero: Optional[str] = None,
    capitulo_numero: Optional[str] = None,
    secao_numero: Optional[str] = None,
    subsecao_numero: Optional[str] = None,
    artigo_numero: Optional[str] = None,
) -> str:
    """
    Busca documentos no Supabase filtrando por metadados hierárquicos.
    
    Esta ferramenta permite buscar conteúdos específicos baseado na estrutura
    hierárquica do documento (Título > Capítulo > Seção > Subseção > Artigo).
    
    Use esta ferramenta quando:
    - Souber a localização exata (título, capítulo, seção ou artigo)
    - Quiser restringir a busca a uma parte específica do documento
    - Precisar de resultados mais direcionados
    
    REGRAS DE HIERARQUIA:
    - TÍTULO: pode ser buscado isoladamente (numeração única: I, II, III...)
    - ARTIGO: pode ser buscado isoladamente (numeração única: 1, 2, 3...)
    - CAPÍTULO: requer TÍTULO pai (numeração repetitiva)
    - SEÇÃO: requer TÍTULO e CAPÍTULO pai (numeração repetitiva)
    - SUBSEÇÃO: requer TÍTULO, CAPÍTULO e SEÇÃO pai (numeração repetitiva)
    
    Args:
        titulo_numero: Número do título em romano (ex: "XVI", "I", "II")
        capitulo_numero: Número do capítulo em romano (ex: "I", "II")
        secao_numero: Número da seção em romano (ex: "I", "II")
        subsecao_numero: Número da subseção em romano (ex: "I", "II")
        artigo_numero: Número do artigo (ex: "339", "1", "2")
        
    Nota: Esta função realiza busca APENAS por metadados, sem necessidade de query semântica.
    
    Returns:
        String formatada com os resultados encontrados
    
    Exemplos:
        1. Buscar um artigo específico:
           supabase_metadata_search_func(
               artigo_numero="339"
           )
        
        2. Buscar em um título específico:
           supabase_metadata_search_func(
               titulo_numero="XVI"
           )
        
        3. Buscar em um capítulo (requer título pai):
           supabase_metadata_search_func(
               titulo_numero="XVI",
               capitulo_numero="I"
           )
        
        4. Buscar em uma seção (requer título e capítulo):
           supabase_metadata_search_func(
               titulo_numero="XVI",
               capitulo_numero="I",
               secao_numero="I"
           )
    """
    
    logger.info("[METADATA] ===== Início da busca por metadados =====")
    logger.info(
        f"[METADATA] Parâmetros | fonte={fonte} | "
        f"titulo={titulo_numero} | cap={capitulo_numero} | sec={secao_numero} | "
        f"subsec={subsecao_numero} | art={artigo_numero}"
    )
    
    # Valida hierarquia
    valido, erro = _validate_hierarchical_filters(
        titulo_numero=titulo_numero,
        capitulo_numero=capitulo_numero,
        secao_numero=secao_numero,
        subsecao_numero=subsecao_numero,
        artigo_numero=artigo_numero,
    )
    
    if not valido:
        logger.error(f"[METADATA] Validação falhou: {erro}")
        return f"ERRO DE HIERARQUIA: {erro}"
    
    # Inicializa clientes (não precisa do OpenAI para busca apenas por metadados)
    _, supabase_client = _init_clients()
    
    # Constrói filtros de metadados
    filtros = _build_metadata_filters(
        fonte=fonte,
        titulo_numero=titulo_numero,
        capitulo_numero=capitulo_numero,
        secao_numero=secao_numero,
        subsecao_numero=subsecao_numero,
        artigo_numero=artigo_numero,
    )
    
    if not filtros:
        logger.warning("[METADATA] Nenhum filtro de metadado fornecido!")
        return "ERRO: Forneça ao menos um filtro de metadado (fonte, titulo_numero, artigo_numero, etc.)"
    
    logger.info(f"[METADATA] Filtros construídos: {filtros}")
    
    # Executa busca APENAS por metadados (sem query/embedding)
    result = _call_metadata_only_function(
        supabase_client,
        _RAG_FUNCTION_METADATA,
        match_count=_RAG_K_METADATA,
        filtros_metadados=filtros,
    )
    
    rows = getattr(result, "data", []) or []
    out = _format_results(rows, mode="metadata")
    
    logger.info(f"[METADATA] Tamanho do texto formatado: {len(out)}")
    logger.info("[METADATA] ===== Fim da busca por metadados =====")
    
    return out


# ============================================
# CRIAÇÃO DAS TOOLS DO LANGCHAIN
# ============================================

# Tool 1: Busca Semântica Pura
supabase_semantic_search: BaseTool = tool(supabase_semantic_search_func)
supabase_semantic_search.name = "Supabase_Semantic_Search"
supabase_semantic_search.description = """
Busca semântica PURA no Supabase (APENAS query, SEM filtros).

Use quando:
- NÃO souber a localização exata no documento
- Quiser explorar conteúdo de forma ampla
- Buscar conceitos ou temas gerais

Parâmetro:
- query (obrigatório): texto para busca semântica

Retorna os 4 trechos mais relevantes semanticamente.
"""

# Tool 2: Busca por Metadados
supabase_metadata_search: BaseTool = tool(supabase_metadata_search_func)
supabase_metadata_search.name = "Supabase_Metadata_Search"
supabase_metadata_search.description = """
Busca no Supabase COM filtros hierárquicos de metadados.

Use quando:
- SOUBER a localização exata (título, capítulo, seção ou artigo)
- Quiser restringir busca a parte específica do documento

HIERARQUIA OBRIGATÓRIA:
- TÍTULO ou ARTIGO: podem ser buscados sozinhos
- CAPÍTULO: exige titulo_numero
- SEÇÃO: exige titulo_numero + capitulo_numero
- SUBSEÇÃO: exige titulo_numero + capitulo_numero + secao_numero

Parâmetros:
- fonte: nome do documento fonte (padrão: "Regulamento Geral da Graduação da UFPI")
- titulo_numero: número romano do título (ex: "XVI")
- capitulo_numero: número romano do capítulo (ex: "I")
- secao_numero: número romano da seção (ex: "I")
- subsecao_numero: número romano da subseção (ex: "I")
- artigo_numero: número do artigo (ex: "339")

Retorna até 10 resultados da área especificada (busca APENAS por metadados, sem query semântica).
"""