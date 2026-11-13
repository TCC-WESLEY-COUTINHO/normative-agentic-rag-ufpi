# Tentativa interrompida antes da indexação

Em 2026-10-19, a execução isolada iniciou o manifesto, mas a primeira chamada de embeddings falhou com `httpx.ConnectError: All connection attempts failed` / `OpenRouterError: Não foi possível conectar ao OpenRouter` no ambiente com rede restrita. Não foram geradas respostas nem calculadas métricas. O manifesto `status=started` foi preservado como registro da tentativa; não representa piloto concluído.

Nova tentativa autorizada com acesso à rede em `pilot_003`, mesmo snapshot científico; nenhum resultado foi substituído.
