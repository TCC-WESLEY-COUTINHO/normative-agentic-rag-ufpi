import json
import os
from openai import OpenAI
from supabase import create_client, Client
from dotenv import load_dotenv

# Carregar variáveis de ambiente do arquivo .env
load_dotenv()

# Configurações
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
EMBEDDING_MODEL = "text-embedding-3-small"
BATCH_SIZE = 100  # Processar em lotes para otimizar

# Inicializar clientes
openai_client = OpenAI(api_key=OPENAI_API_KEY)
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def criar_embedding(texto: str) -> list[float]:
    """Cria embedding usando OpenAI API"""
    response = openai_client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=texto
    )
    return response.data[0].embedding

def processar_chunks(arquivo_json: str):
    """Processa arquivo JSON e insere embeddings no Supabase"""
    
    # Carregar JSON
    with open(arquivo_json, 'r', encoding='utf-8') as f:
        chunks = json.load(f)
    
    print(f"Total de chunks a processar: {len(chunks)}")
    
    # Processar em lotes
    for i in range(0, len(chunks), BATCH_SIZE):
        batch = chunks[i:i + BATCH_SIZE]
        registros = []
        
        for idx, chunk in enumerate(batch):
            try:
                # Criar embedding do conteúdo
                embedding = criar_embedding(chunk['conteudo'])
                
                # Preparar registro para inserção
                registro = {
                    'conteudo': chunk['conteudo'],
                    'embedding': embedding,
                    'metadados': chunk['metadados']
                }
                registros.append(registro)
                
                print(f"Processado chunk {i + idx + 1}/{len(chunks)}")
                
            except Exception as e:
                print(f"Erro ao processar chunk {i + idx + 1}: {str(e)}")
                continue
        
        # Inserir lote no Supabase
        if registros:
            try:
                supabase.table('documentos_embeddings_v2').insert(registros).execute()
                print(f"Lote {i//BATCH_SIZE + 1} inserido com sucesso!")
            except Exception as e:
                print(f"Erro ao inserir lote no Supabase: {str(e)}")
    
    print("Processamento concluído!")

def buscar_similar(query: str, limite: int = 5, filtros: dict = None):
    """Busca documentos similares por similaridade semântica"""
    
    # Criar embedding da query
    query_embedding = criar_embedding(query)
    
    # Buscar no Supabase usando função de similaridade
    # A função match_documentos deve ser criada no Supabase (veja SQL abaixo)
    resultado = supabase.rpc(
        'match_documentos',
        {
            'query_embedding': query_embedding,
            'match_threshold': 0.7,
            'match_count': limite,
            'filtros_metadados': filtros or {}
        }
    ).execute()
    
    return resultado.data

if __name__ == "__main__":
    # Processar arquivo JSON
    processar_chunks('chunks_v2.json')
    
    # Exemplo de busca
    # resultados = buscar_similar("Como funciona a matrícula na UFPI?")
    # for r in resultados:
    #     print(f"Similaridade: {r['similarity']}")
    #     print(f"Conteúdo: {r['conteudo'][:200]}...")
    #     print(f"Metadados: {r['metadados']}\n")