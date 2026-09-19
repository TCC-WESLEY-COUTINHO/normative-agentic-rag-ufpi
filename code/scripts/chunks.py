import re
import json

class ChunkExtractor:
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

        chunk = {
            "conteudo": conteudo,
            "metadados": {
                "fonte": "Regulamento Geral da Graduação da UFPI",
                "titulo": self.titulo_atual,
                "capitulo": self.capitulo_atual,
                "secao": self.secao_atual,
                "subsecao": self.subsecao_atual,
                "artigo": numero_artigo
            }
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
    extractor = ChunkExtractor()
    
    # Processa o arquivo markdown
    caminho_entrada = 'RGG_markdown.txt'
    extractor.processa_arquivo(caminho_entrada)
    
    # Salva os chunks em um arquivo JSON
    caminho_saida = 'chunks.json'
    extractor.salva_chunks(caminho_saida)
    
    print(f'Foram extraídos {len(extractor.chunks)} chunks do documento.')
    print(f'Os chunks foram salvos em: {caminho_saida}')

if __name__ == '__main__':
    main()