# 📘 Documentação da API

Esta API fornece um backend robusto em **FastAPI** para orquestração de agentes inteligentes, utilizando **LangGraph** para gerenciar fluxos de conversação e memória. Ela suporta interações via texto síncrono ou *streaming* de tokens em tempo real.

## 1. Configuração e Autenticação

A autenticação da API é **opcional** e controlada por variáveis de ambiente, facilitando o uso tanto em desenvolvimento local quanto em produção segura.

### Como Habilitar/Desabilitar

O comportamento é definido pela variável `AUTH_SECRET` no seu arquivo `.env`:

* Desabilitar Autenticação (Modo Aberto):
  Deixe a variável vazia ou não a defina.
  **Snippet de código**

  ```
  AUTH_SECRET=
  ```

  *Neste modo, o backend não exigirá nenhum token para processar as requisições.*
* Habilitar Autenticação (Modo Seguro):
  Defina um valor para a chave. Este valor será o token exigido.
  **Snippet de código**

  ```
  AUTH_SECRET=meu_segredo_super_seguro_123
  ```

### Realizando Requisições (Quando habilitado)

Se a autenticação estiver ativa, todas as chamadas devem incluir o cabeçalho `Authorization` com o esquema `Bearer`:

**HTTP**

```
Authorization: Bearer meu_segredo_super_seguro_123
```

> **Nota:** Se a autenticação estiver ativa e o cabeçalho não for enviado (ou for inválido), a API retornará `401 Unauthorized`.

---

## 2. Endpoints de Conversação (Chat)

Estes são os endpoints principais para interação com os agentes.

### 2.1. Streaming de Resposta (Recomendado)

Gera uma resposta do agente enviando eventos parciais (Server-Sent Events - SSE). Ideal para interfaces de chat que mostram o texto sendo digitado.

* **Método:** `POST`
* **URL:** `/stream` (ou `/{agent_id}/stream` para um agente específico)
* **Content-Type:** `application/json`
* **Response Content-Type:** `text/event-stream`

**Corpo da Requisição (`StreamInput`):**

| **Campo**   | **Tipo** | **Obrigatório** | **Descrição**                                                                                                 |
| ----------------- | -------------- | ---------------------- | --------------------------------------------------------------------------------------------------------------------- |
| `message`       | string         | Sim                    | A mensagem do usuário.                                                                                               |
| `thread_id`     | string         | Não                   | ID único da conversa (UUID). Se omitido, uma nova thread é criada.**Essencial para memória de curto prazo.** |
| `user_id`       | string         | Não                   | ID único do usuário.**Essencial para memória de longo prazo.**                                               |
| `model`         | string         | Não                   | O modelo de LLM a ser usado (ex:`gpt-4o-mini`). Se nulo, usa o padrão do sistema.                                  |
| `stream_tokens` | boolean        | Não                   | Padrão `true`. Se `false`, envia apenas eventos de mensagens completas, sem tokens parciais.                     |

**Exemplo de Requisição:**

**JSON**

```
{
  "message": "Quais as normas para TCC na UFPI?",
  "thread_id": "550e8400-e29b-41d4-a716-446655440000",
  "stream_tokens": true
}
```

Formato da Resposta (Event Stream):

A API envia linhas de texto iniciadas por data:, contendo um JSON. O frontend deve ler linha a linha.

1. **Evento de Token (`token`):** Fragmento de texto gerado.
   **JSON**

   ```
   data: {"type": "token", "content": "As"}
   data: {"type": "token", "content": " normas"}
   ```
2. **Evento de Mensagem (`message`):** Mensagem completa estruturada (Human ou AI). Contém o `run_id` para feedback.
   **JSON**

   ```
   data: {"type": "message", "content": {"type": "ai", "content": "As normas...", "run_id": "abc-123"}}
   ```
3. **Evento de Erro (`error`):**
   **JSON**

   ```
   data: {"type": "error", "content": "Falha interna ao processar."}
   ```
4. **Finalização:**
   **Plaintext**

   ```
   data: [DONE]
   ```

---

### 2.2. Invocação Síncrona (Invoke)

Processa a mensagem e retorna a resposta completa de uma só vez. Útil para chamadas onde a experiência de "digitação" não é necessária.

* **Método:** `POST`
* **URL:** `/invoke` (ou `/{agent_id}/invoke`)
* **Corpo da Requisição:** `UserInput` (Mesmos campos do `/stream`, exceto `stream_tokens`).

**Exemplo de Resposta (`ChatMessage`):**

**JSON**

```
{
  "type": "ai",
  "content": "Para realizar o TCC, você deve seguir a resolução...",
  "run_id": "87588325-1e43-410a-ba92-749372297123",
  "response_metadata": {
    "token_usage": { "total_tokens": 150 }
  }
}
```

---

## 3. Gestão de Histórico e Feedback

Recursos para manter a consistência da conversa e monitorar a qualidade.

### 3.1. Recuperar Histórico

Retorna todas as mensagens trocadas em uma thread específica. O frontend deve chamar isso ao carregar uma conversa existente.

* **Método:** `POST`
* **URL:** `/history`

**Corpo da Requisição (`ChatHistoryInput`):**

**JSON**

```
{
  "thread_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

**Exemplo de Resposta:**

**JSON**

```
{
  "messages": [
    { "type": "human", "content": "Olá" },
    { "type": "ai", "content": "Olá! Como posso ajudar com seu TCC?", "run_id": "..." }
  ]
}
```

---

### 3.2. Enviar Feedback

Registra a avaliação do usuário (ex: like/dislike) no  **LangSmith** . Requer o `run_id` recebido na resposta do chat.

* **Método:** `POST`
* **URL:** `/feedback`

**Corpo da Requisição (`Feedback`):**

| **Campo** | **Tipo** | **Descrição**                                                   |
| --------------- | -------------- | ----------------------------------------------------------------------- |
| `run_id`      | string         | ID único da execução da IA (retornado em `/stream`ou `/invoke`). |
| `key`         | string         | Nome da métrica (ex:`user_score`,`thumbs_up`).                     |
| `score`       | float          | Valor numérico (ex:`1.0`para positivo,`0.0`para negativo).         |
| `kwargs`      | object         | Dados extras opcionais (ex:`{"comment": "Resposta imprecisa"}`).      |

**Exemplo:**

**JSON**

```
{
  "run_id": "87588325-1e43-410a-ba92-749372297123",
  "key": "user_feedback",
  "score": 1.0
}
```

---

## 4. Utilitários e Sistema

### 4.1. Metadados do Serviço (`/info`)

Retorna as configurações disponíveis no backend, útil para popular menus de configuração no frontend.

* **Método:** `GET`
* **URL:** `/info`

**Retorno:**

* `agents`: Lista de agentes disponíveis (ex: `research-assistant`, `chatbot-ufpi`).
* `models`: Lista de modelos de LLM suportados (ex: `gpt-4o`, `gemini-1.5-pro`).
* `default_agent`: Agente padrão utilizado se nenhum for especificado.
* `default_model`: Modelo padrão.

### 4.2. Health Check (`/health`)

Verifica se a API está online e se a integração com serviços de monitoramento (Langfuse) está ativa.

* **Método:** `GET`
* **URL:** `/health`

---

## 5. Resumo dos Modelos de Dados (Schemas)

Para referência rápida ao desenvolver o frontend:

### `UserInput` / `StreamInput`

**JSON**

```
{
  "message": "string (obrigatório)",
  "model": "string (opcional)",
  "thread_id": "uuid (opcional - para contexto)",
  "user_id": "uuid (opcional - para memória)",
  "agent_config": { "param": "valor" },
  "stream_tokens": true  // Apenas no StreamInput
}
```

### `ChatMessage`

**JSON**

```
{
  "type": "human | ai | tool | custom",
  "content": "string",
  "run_id": "uuid",
  "tool_calls": [],
  "response_metadata": {}
}
```
