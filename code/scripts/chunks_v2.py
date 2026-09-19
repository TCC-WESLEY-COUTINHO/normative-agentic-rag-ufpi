import re
import json


def separar_titulo(titulo: str) -> dict:
    """
    Separa título em número e nome.
    Exemplo: "TÍTULO II - DA EXECUÇÃO, REGISTRO E CONTROLE ACADÊMICOS"
    Retorna: {"numero": "II", "nome": "DA EXECUÇÃO, REGISTRO E CONTROLE ACADÊMICOS"}
    """
    if not titulo:
        return {"numero": "", "nome": ""}
    
    # Padrão: TÍTULO [ROMANO] - [NOME]
    # Aceita números romanos: I, II, III, IV, V, VI, VII, VIII, IX, X, XI, XII, ..., XX, etc.
    match = re.match(r'TÍTULO\s+([IVX]+)\s*-\s*(.+)', titulo, re.IGNORECASE)
    if match:
        return {"numero": match.group(1).upper(), "nome": match.group(2).strip()}
    
    # Se não tem o padrão completo, tenta extrair número romano
    match = re.match(r'([IVX]+)', titulo)
    if match:
        numero = match.group(1).upper()
        nome = titulo.replace(match.group(1), "").strip(" -")
        return {"numero": numero, "nome": nome}
    
    return {"numero": "", "nome": titulo}


def separar_capitulo(capitulo: str) -> dict:
    """
    Separa capítulo em número e nome.
    Exemplo: "CAPÍTULO I - DAS DISCIPLINAS"
    Retorna: {"numero": "I", "nome": "DAS DISCIPLINAS"}
    """
    if not capitulo:
        return {"numero": "", "nome": ""}
    
    # Padrão: CAPÍTULO [ROMANO] - [NOME]
    # Aceita números romanos: I, II, III, IV, V, VI, VII, VIII, IX, X, etc.
    match = re.match(r'CAPÍTULO\s+([IVX]+)\s*-\s*(.+)', capitulo, re.IGNORECASE)
    if match:
        return {"numero": match.group(1).upper(), "nome": match.group(2).strip()}
    
    # Se não tem o padrão completo, tenta extrair número romano
    match = re.match(r'([IVX]+)', capitulo)
    if match:
        numero = match.group(1).upper()
        nome = capitulo.replace(match.group(1), "").strip(" -")
        return {"numero": numero, "nome": nome}
    
    return {"numero": "", "nome": capitulo}


def separar_secao(secao: str) -> dict:
    """
    Separa seção em número e nome.
    Exemplo: "Seção I - Do Trancamento De Matrícula"
    Retorna: {"numero": "I", "nome": "Do Trancamento De Matrícula"}
    """
    if not secao:
        return {"numero": "", "nome": ""}
    
    # Padrão: Seção [ROMANO] - [nome]
    # Aceita números romanos: I, II, III, IV, V, VI, VII, VIII, IX, X, etc.
    match = re.match(r'Seção\s+([IVX]+)\s*-\s*(.+)', secao, re.IGNORECASE)
    if match:
        return {"numero": match.group(1).upper(), "nome": match.group(2).strip()}
    
    # Se não tem o padrão completo, tenta extrair número romano
    match = re.match(r'([IVX]+)', secao)
    if match:
        numero = match.group(1).upper()
        nome = secao.replace(match.group(1), "").strip(" -")
        return {"numero": numero, "nome": nome}
    
    return {"numero": "", "nome": secao}


def separar_subsecao(subsecao: str) -> dict:
    """
    Separa subseção em número e nome.
    Exemplo: "Subseção I - Da Matrícula"
    Retorna: {"numero": "I", "nome": "Da Matrícula"}
    """
    if not subsecao:
        return {"numero": "", "nome": ""}
    
    # Padrão: Subseção [ROMANO] - [nome]
    # Aceita números romanos: I, II, III, IV, V, VI, VII, VIII, IX, X, etc.
    match = re.match(r'Subseção\s+([IVX]+)\s*-\s*(.+)', subsecao, re.IGNORECASE)
    if match:
        return {"numero": match.group(1).upper(), "nome": match.group(2).strip()}
    
    # Se não tem o padrão completo, tenta extrair número romano
    match = re.match(r'([IVX]+)', subsecao)
    if match:
        numero = match.group(1).upper()
        nome = subsecao.replace(match.group(1), "").strip(" -")
        return {"numero": numero, "nome": nome}
    
    return {"numero": "", "nome": subsecao}


def separar_artigo(artigo: str) -> dict:
    """
    Separa artigo em número e formato completo.
    Exemplo: "Art. 2" ou "Art. 123"
    Retorna: {"numero": "2", "completo": "Art. 2"}
    """
    if not artigo:
        return {"numero": "", "completo": ""}
    
    # Padrão: Art. [NÚMERO]
    match = re.search(r'Art\.\s*(\d+)', artigo, re.IGNORECASE)
    if match:
        numero = match.group(1)
        return {"numero": numero, "completo": f"Art. {numero}"}
    
    return {"numero": "", "completo": artigo}


class ChunkExtractorV2:
    def __init__(self):
        self.titulo_atual = ""
        self.capitulo_atual = ""
        self.secao_atual = ""
        self.subsecao_atual = ""
        self.chunks = []
        self.conteudo_artigo_atual = []
        self.contexto = {
            "titulo": "",
            "capitulo": "",
            "secao": "", 
            "subsecao": ""
        }
        
    def atualiza_contexto(self, linha):
        # Atualiza título
        if linha.startswith('# '):
            self.contexto["titulo"] = linha.lstrip('#').strip()
            self.contexto["capitulo"] = ""
            self.contexto["secao"] = ""
            self.contexto["subsecao"] = ""
            return True
            
        # Atualiza capítulo
        if linha.startswith('## '):
            self.contexto["capitulo"] = linha.lstrip('#').strip()
            self.contexto["secao"] = ""
            self.contexto["subsecao"] = ""
            return True
            
        # Atualiza seção
        if linha.startswith('### '):
            self.contexto["secao"] = linha.lstrip('#').strip()
            self.contexto["subsecao"] = ""
            return True
            
        # Atualiza subseção
        if linha.startswith('#### '):
            self.contexto["subsecao"] = linha.lstrip('#').strip()
            return True
            
        return False

    def finaliza_chunk_atual(self):
        if not self.conteudo_artigo_atual:
            return

        conteudo = '\n'.join(self.conteudo_artigo_atual)
        
        # Extrai o número do artigo
        numero_artigo = ""
        match = re.search(r'\*\*Art\. (\d+)', conteudo)
        if match:
            numero_artigo = f"Art. {match.group(1)}"

        # Separa cada campo em número e nome
        titulo_info = separar_titulo(self.titulo_atual)
        capitulo_info = separar_capitulo(self.capitulo_atual)
        secao_info = separar_secao(self.secao_atual)
        subsecao_info = separar_subsecao(self.subsecao_atual)
        artigo_info = separar_artigo(numero_artigo)

        # Cria metadados v2 com campos separados
        metadados = {
            "fonte": "Regulamento Geral da Graduação da UFPI",
            # Título
            "titulo_numero": titulo_info["numero"],
            "titulo_nome": titulo_info["nome"],
            # Capítulo
            "capitulo_numero": capitulo_info["numero"],
            "capitulo_nome": capitulo_info["nome"],
            # Seção
            "secao_numero": secao_info["numero"],
            "secao_nome": secao_info["nome"],
            # Subseção
            "subsecao_numero": subsecao_info["numero"],
            "subsecao_nome": subsecao_info["nome"],
            # Artigo
            "artigo_numero": artigo_info["numero"],
            "artigo": artigo_info["completo"]  # Mantém formato completo para compatibilidade
        }

        chunk = {
            "conteudo": conteudo,
            "metadados": metadados
        }
        
        self.chunks.append(chunk)
        self.conteudo_artigo_atual = []

    def processa_arquivo(self, caminho_arquivo):
        with open(caminho_arquivo, 'r', encoding='utf-8') as arquivo:
            linhas = arquivo.readlines()
            
            for linha in linhas:
                linha = linha.rstrip()
                
                # Pula linhas vazias
                if not linha:
                    continue
                
                # Se é um cabeçalho, atualiza o contexto
                if self.atualiza_contexto(linha):
                    continue
                
                # Se encontrou um novo artigo
                if linha.startswith('**Art.'):
                    # Finaliza o chunk anterior se existir
                    if self.conteudo_artigo_atual:
                        self.finaliza_chunk_atual()
                        
                    # Atualiza o contexto do novo artigo
                    self.titulo_atual = self.contexto["titulo"]
                    self.capitulo_atual = self.contexto["capitulo"] 
                    self.secao_atual = self.contexto["secao"]
                    self.subsecao_atual = self.contexto["subsecao"]
                    
                    # Adiciona o novo artigo
                    self.conteudo_artigo_atual.append(linha)
                    continue
                
                # Adiciona a linha ao chunk atual se estiver coletando um artigo
                if self.conteudo_artigo_atual:
                    self.conteudo_artigo_atual.append(linha)
                    
            # Finaliza o último chunk se existir
            if self.conteudo_artigo_atual:
                self.finaliza_chunk_atual()

    def salva_chunks(self, caminho_saida):
        with open(caminho_saida, 'w', encoding='utf-8') as arquivo:
            json.dump(self.chunks, arquivo, ensure_ascii=False, indent=2)


def main():
    extractor = ChunkExtractorV2()
    
    # Processa o arquivo markdown
    caminho_entrada = 'RGG_markdown.txt'
    extractor.processa_arquivo(caminho_entrada)
    
    # Salva os chunks em um arquivo JSON
    caminho_saida = 'chunks_v2.json'
    extractor.salva_chunks(caminho_saida)
    
    print(f'✅ Foram extraídos {len(extractor.chunks)} chunks v2 do documento.')
    print(f'📁 Os chunks foram salvos em: {caminho_saida}')
    
    # Mostra exemplo do primeiro chunk para validação
    if extractor.chunks:
        print('\n📋 Exemplo do primeiro chunk:')
        exemplo = extractor.chunks[0]
        print(f'  Artigo: {exemplo["metadados"]["artigo"]}')
        print(f'  Título: {exemplo["metadados"]["titulo_numero"]} - {exemplo["metadados"]["titulo_nome"]}')
        print(f'  Capítulo: {exemplo["metadados"]["capitulo_numero"]} - {exemplo["metadados"]["capitulo_nome"]}')
        print(f'  Seção: {exemplo["metadados"]["secao_numero"]} - {exemplo["metadados"]["secao_nome"]}')


if __name__ == '__main__':
    main()

