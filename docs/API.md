# API do backend

API HTTP (FastAPI) servida pelo backend do protótipo. Para expô-la no host, veja [`DEPLOY_LINUX.md`](DEPLOY_LINUX.md) §4 (`deploy/compose.api.yaml`, padrão `http://127.0.0.1:8080`). A documentação interativa (OpenAPI) fica em `/docs`.

## Agente do protótipo

O agente do protótipo é **`chatbot_ufpi_integrated_v1`**, que a interface web usa.

O registro de agentes também contém agentes legados e de exemplo, herdados do serviço anterior e do template. O agente padrão das rotas sem ID (`/invoke`, `/stream`) é o legado `chatbot_ufpi_v2`, que depende de um banco vetorial externo não suportado nesta versão. **Sempre informe o ID na rota.**

## Autenticação

Sem `AUTH_SECRET` no `.env`, a API é aberta. Com `AUTH_SECRET` definido, todas as rotas, exceto `/health`, `/docs` e `/prototype/identity`, exigem:

```
Authorization: Bearer <AUTH_SECRET>
```

## Rotas

| Método e rota | Função |
|---|---|
| `GET /health` | Estado do processo e prontidão do agente integrado (`integrated_agent.ready`, `index_records`, `reason_code`). Não chama provedores |
| `GET /prototype/identity` | Configuração em execução: arquitetura, modo do intérprete, política de transição, modelos, host do endpoint de LLM, `evaluated_configuration`, tag/commit da imagem. Publicada pelo launcher de `deploy/backend/` |
| `GET /info` | Agentes registrados e modelos disponíveis |
| `GET /agents/{agent_id}/readiness` | Prontidão de um agente |
| `POST /{agent_id}/invoke` | Executa um turno e devolve a mensagem final |
| `POST /{agent_id}/stream` | Executa um turno com Server-Sent Events |
| `POST /history` | Mensagens de uma thread (`{"thread_id": "..."}`) |
| `POST /feedback` | Registro de feedback (herdado do serviço) |

## Turno: entrada

```json
{
  "message": "Posso trancar o curso no primeiro período?",
  "thread_id": "minha-conversa-1"
}
```

Use o mesmo `thread_id` para continuar a conversa. A pendência de esclarecimento e o nível de ensino declarado ficam associados à thread. O campo `model` é ignorado pelo agente integrado, que usa os modelos configurados no backend.

```bash
curl -s http://127.0.0.1:8080/chatbot_ufpi_integrated_v1/invoke \
  -H 'Content-Type: application/json' \
  -d '{"message":"Qual a frequência mínima no mestrado?","thread_id":"t1"}'
```

## Turno: saída

Mensagem com `type: "ai"`, `content` (texto exibido) e, nos turnos normativos, `normative_result`:

| Campo | Significado |
|---|---|
| `status` | `ANSWER`, `CLARIFICATION` ou `ERROR` |
| `core_status` | `accepted` (aceita na primeira geração), `regenerated` (aceita após a nova tentativa), `fallback` (resposta de contingência do validador) ou `abstained` |
| `answer` | Texto da resposta normativa |
| `references` | Lista de `NormativeReference`: `norm_id`, `source`, `article`, `validated_subdivision`, `display_text`, `temporal_role` (`eligible`, `historical` ou `posterior`) e `evidence_text` |
| `domain` | `graduacao`, `pos_graduacao` ou `ambas` |
| `retrieval_strategy` | `dense_vector`, `metadata_exact` ou `vector_filtered` |
| `needs_clarification`, `clarification_question` | Pedido de esclarecimento (por exemplo, o nível de ensino) |
| `temporal_provenance`, `temporal_status_text` | Contexto temporal aplicado pelo filtro de versões |
| `error_code`, `safe_message` | Erro técnico, com mensagem segura |
| `correlation_id` | Identificador do turno |

**As referências vêm de objetos estruturados, não do texto gerado.** Uma resposta `fallback` traz as referências consultadas, mas não uma conclusão.

## Stream

`POST /chatbot_ufpi_integrated_v1/stream` aceita o mesmo corpo, mais `stream_tokens`. Os eventos `data:` trazem mensagens no mesmo formato; o último evento é `data: [DONE]`.
