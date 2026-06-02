# Isy.One Secure API

Sistema web/API para cadastro e execução controlada de Shell Scripts `.sh` via Docker.

## Requisitos atendidos

- Endpoints limpos para listagem de scripts disponíveis.
- Endpoint parametrizável para execução customizada.
- Execução obrigatória com `subprocess`, capturando `stdout` e `stderr`.
- Segurança via cabeçalho HTTP `X-Isy-Token`.
- Interface web para cadastro de scripts Bash.
- Campos: script, parâmetros de envio, descrição curta e status lógico.
- Alteração dinâmica do token de autenticação.
- Logs e auditoria em SQLite.
- Dockerfile otimizado com `python:3.11-slim`.
- Volume Docker para leitura dos scripts do host.
- Sem execução direta no terminal local do host.

## Como rodar com Docker

```bash
docker compose up --build
```

Acesse:

```text
http://localhost:5000
```

Token inicial:

```text
isyone-dev-token
```

## Volumes

```yaml
volumes:
  - ./data:/app/data
  - ./scripts:/app/scripts:ro
```

- `./data`: banco SQLite persistente.
- `./scripts`: scripts Bash do host montados como somente leitura.

## Endpoints

### Listar scripts

```bash
curl http://localhost:5000/api/scripts \
  -H "X-Isy-Token: isyone-dev-token"
```

### Executar script

```bash
curl -X POST http://localhost:5000/api/scripts/hello/execute \
  -H "Content-Type: application/json" \
  -H "X-Isy-Token: isyone-dev-token" \
  -d '{"params": {"name": "Isy.One"}}'
```

## Administração

- `/admin/scripts`: cadastro e ativação/inativação de scripts.
- `/admin/token`: alteração dinâmica do token.
- `/admin/logs`: logs de auditoria.
