# Isy.One Remote Maintenance - Site Dockerizado

Sistema web em Flask para cadastro de servidores Linux/Ubuntu e execução remota de rotinas de manutenção via SSH.

## Requisito de entrega

A aplicação **não deve ser executada diretamente no terminal local do host**. O deploy deve ser feito via Docker.

## Estrutura

```text
isyone_site/
├── app.py
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── scripts/          # scripts Shell lidos via volume Docker
├── data/             # banco SQLite persistido via volume Docker
├── templates/
└── static/
```

## Rodar com Docker Compose

Na pasta onde está o `docker-compose.yml`, execute:

```bash
docker compose up --build
```

Acesse:

```text
http://127.0.0.1:5000
```

## Volumes

O `docker-compose.yml` mapeia:

```yaml
volumes:
  - ./data:/app/data
  - ./scripts:/app/scripts:ro
```

- `./data`: mantém o banco SQLite salvo no host.
- `./scripts`: contém os Shell Scripts de manutenção. O container lê os scripts em modo somente leitura.

## Scripts suportados

Os nomes dos scripts são vinculados às tarefas do sistema:

```text
check_docker.sh
check_disk.sh
check_memory.sh
check_agent_status.sh
clean_old_coupon_logs.sh
restart_docker_containers.sh
```

Se o script existir em `/app/scripts`, ele será enviado e executado no servidor remoto via SSH usando `bash -s`.
