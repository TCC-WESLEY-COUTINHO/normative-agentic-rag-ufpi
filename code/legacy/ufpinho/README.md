# UFpinho (personagem anterior) — cópia de rollback

O personagem 3D anterior (cabeça `head_front.png` com o rosto desenhado em SVG no visor) foi
substituído pelo Bisco como identidade visual padrão da interface. Esta pasta preserva os arquivos
exatamente como estavam, fora do caminho de produção: a imagem da interface copia apenas `src/`,
portanto nada daqui é carregado nem empacotado.

- `static/head_front.png`, `static/favicon-64.png`: assets servidos antes em `src/static/ufpinho/`.
- `chat_ui/character.py`, `chat_ui/character.js`, `chat_ui/character.css`: marcação, script e
  estilos do personagem anterior.

Para voltar ao personagem anterior, restaure esses arquivos nos caminhos originais (ou recupere-os
pelo histórico do Git) e reverta as referências ao Bisco em `src/streamlit_app.py`.
