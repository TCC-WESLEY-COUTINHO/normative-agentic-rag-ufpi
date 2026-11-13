# Implantação controlada em AWS (EC2 + Docker Compose): roteiro preparado, não executado

**Nenhum recurso AWS foi criado.**

- **Finalidade:** demonstração ou avaliação experimental controlada.
- **O que não é:** serviço normativo. O defeito G4-014 continua aberto, e o protótipo não é fonte para decisões acadêmicas reais.
- **O que a implantação não é:** pesquisa de campo realizada.

## 1. Arquitetura

- Uma instância EC2 em sub-rede pública, com os mesmos três containers testados localmente (`compose.demo.yaml`: `postgres`, `backend` e `interface`).
- Um proxy reverso com HTTPS e autenticação à frente da interface. É o único componente novo, e fica fora das imagens do protótipo.
- O backend e o PostgreSQL não publicam porta. A interface publica apenas `127.0.0.1:8501`, que só o proxy acessa.

```
Navegador ──HTTPS + autenticação──► proxy (porta 443) ──► 127.0.0.1:8501 interface ──rede Docker──► backend ──rede interna──► postgres
```

O navegador só fala com o proxy e com a interface. Quem chama o backend é o processo da interface (Streamlit roda no servidor), então o backend e o banco nunca precisam ser alcançáveis de fora da instância.

## 2. Instância

| Item | Recomendação |
|---|---|
| Tipo | `t3.medium` (4 GB de RAM: o backend usa Chroma em processo, e o PostgreSQL roda na mesma instância) |
| Disco | EBS gp3, 20 GB, criptografado |
| Sistema | Ubuntu Server LTS ou Amazon Linux 2023, com Docker Engine e o plugin Compose |
| Imagens | Construídas na instância a partir de uma tag Git, ou publicadas em um registro privado (ECR) com tag imutável `tcc2-prototype-backend:<commit>` |

## 3. Rede restrita

- **Security group:** entrada só na porta 443, limitada aos IPs autorizados (CIDR da instituição ou dos avaliadores). Porta 22 fechada; acesso administrativo pelo SSM Session Manager.
- **Saída:** HTTPS para `openrouter.ai` (geração, embeddings e Jev).
- **Sem IP público de administração e sem porta 8080 exposta.**

## 4. HTTPS e autenticação

- **Proxy:** Caddy ou Nginx, com certificado TLS (Let's Encrypt em domínio próprio, ou ACM com ALB, se houver balanceador).
- **Autenticação:** HTTP Basic com usuários individuais e senhas fortes, ou OAuth (por exemplo, oauth2-proxy). A interface Streamlit não tem login próprio.
- **Opcional:** `AUTH_SECRET` no backend protege as rotas da API. A interface precisaria da mesma variável.

## 5. Segredos

- `OPENROUTER_API_KEY`, `POSTGRES_PASSWORD` e `AUTH_SECRET` vão no **AWS Secrets Manager** ou no SSM Parameter Store (SecureString). Em servidor, defina `AUTH_SECRET`: o backend passa a exigir o bearer e a interface o envia. O `.env` é materializado na instância no momento do deploy, com permissão `600` e fora de qualquer imagem ou repositório.
- **Chave dedicada à demonstração**, com limite de crédito no provedor, revogável ao fim.

## 6. Limites de custo e de requisições

- **AWS:** Budgets com alerta (por exemplo, US$ 10/mês) e ação de parada da instância.
- **OpenRouter:** limite de crédito na chave dedicada.
- **Proxy:** limite de requisições por IP (por exemplo, 30 por minuto) e tamanho máximo do corpo.
- Cada turno consome geração, Scope Gate, roteamento, embeddings e Jev. Referência: cerca de US$ 0,0005 por pergunta isolada nas medições exploratórias. Os custos variam com o provedor.

## 7. Persistência, logs e backup

- **Volumes:** `postgres_data` (checkpoints das conversas) e o diretório do índice (`INDEX_DIR`), ambos no EBS.
- **Logs:** `docker compose logs` encaminhados ao CloudWatch, com retenção curta (por exemplo, 14 dias). Os logs do backend registram a identidade da versão, sem chaves. As perguntas dos usuários podem aparecer nos logs, então tratar como dado pessoal (LGPD) e informar no termo de uso.
- **Backup:** snapshot do EBS antes de cada atualização (inclui o volume do PostgreSQL), ou `pg_dump` (ver `docs/DEPLOY_LINUX.md` §7). O índice é reprodutível a partir do corpus, mas a reindexação tem custo.

### 7.1. Banco dos checkpoints: container (padrão) ou Amazon RDS

**Padrão: o mesmo container `postgres` do ambiente local.** Nada muda entre a máquina local e a EC2: o `compose.demo.yaml` sobe o PostgreSQL na rede interna do Docker, sem porta no host, com dados no EBS. É a opção mais simples e barata para uma demonstração com uma única instância.

**Alternativa: Amazon RDS for PostgreSQL**, quando o estado das conversas precisar sobreviver à perda da instância, ou para ter backups automáticos com restauração a um ponto no tempo e atualizações gerenciadas. O código não muda. Só o endereço do banco muda, pelo override `deploy/compose.external-postgres.yaml`:

1. **Rede:** criar um DB subnet group com sub-redes **privadas** em duas AZs; `Publicly accessible = No`.
2. **Security group do RDS:** entrada TCP 5432 **somente** a partir do security group da EC2. Nenhuma outra regra de entrada.
3. **Instância:** PostgreSQL 17, `db.t4g.micro`, 20 GB gp3, armazenamento criptografado (KMS), backups automáticos (7 dias), Single-AZ (Multi-AZ só se a demonstração exigir alta disponibilidade), proteção contra exclusão ativada.
4. **Credenciais:** usuário mestre gerenciado pelo Secrets Manager. Criar o banco e um usuário próprio do protótipo (`CREATE DATABASE tcc2; CREATE USER tcc2 ...; GRANT ALL ON DATABASE tcc2 TO tcc2;` e, no PostgreSQL 15+, `GRANT ALL ON SCHEMA public TO tcc2` dentro do banco `tcc2`), com a senha também no Secrets Manager.
5. **TLS:** o RDS aceita TLS, e o cliente usa `sslmode=prefer` (TLS sem verificar o certificado). Para impor TLS, ative `rds.force_ssl=1` no parameter group.
6. **`.env` na EC2:** `POSTGRES_HOST=<endpoint do RDS>`, `POSTGRES_PORT=5432`, `POSTGRES_DB=tcc2`, `POSTGRES_USER=tcc2`, `POSTGRES_PASSWORD=<do Secrets Manager>`.
7. **Subir:** `docker compose -f compose.demo.yaml -f deploy/compose.external-postgres.yaml up -d --build --wait`. O container `postgres` não sobe, e o backend cria as tabelas no RDS na primeira subida.

Custo de referência (us-east-1): cerca de US$ 15 a 20/mês para `db.t4g.micro` Single-AZ com 20 GB. Pare a instância RDS junto com a EC2 entre as demonstrações; o RDS a religa sozinho depois de 7 dias parado.

## 8. Operação

| Ação | Comando |
|---|---|
| Subir | `./scripts/start-local.sh` (o mesmo `docker compose -f compose.demo.yaml up --build -d --wait`) |
| Parar | `./scripts/stop-local.sh` (preserva os volumes) |
| Versão em execução | `docker exec tcc2-demo-backend-1 python -c "import urllib.request;print(urllib.request.urlopen('http://127.0.0.1:8080/prototype/identity').read().decode())"` |
| Rollback | Checkout da tag anterior, rebuild e `up -d`; ou retag da imagem anterior no ECR. O snapshot EBS restaura o estado |
| Desligar | Parar a instância ao fim de cada sessão de demonstração; encerrar a instância, revogar a chave e apagar o segredo ao fim do período |

## 9. Avisos obrigatórios

A interface já exibe, em todas as telas, o aviso "Protótipo de pesquisa. Consulte os documentos oficiais para confirmar as informações." Os avisos abaixo devem constar da página de acesso (antes da autenticação) ou dos termos de uso aceitos pelo avaliador:

- Protótipo experimental de pesquisa (TCC II); não é serviço institucional da UFPI.
- As respostas podem conter afirmações sem suporte. Confirme sempre no texto da norma.
- As perguntas são enviadas a provedores externos de modelos de linguagem. Não inclua dados pessoais.
- Coleta de dados com participantes só depois da verificação ética aplicável (CEP/CONEP), do consentimento e da LGPD.
