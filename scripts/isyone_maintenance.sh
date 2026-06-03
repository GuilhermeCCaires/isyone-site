#!/bin/sh
set -eu

AGENT_SERVICE="${AGENT_SERVICE:-isy-agent}"
COUPON_LOG_DIR="${COUPON_LOG_DIR:-/var/log/isyone/coupons}"
LOG_RETENTION_DAYS="${LOG_RETENTION_DAYS:-30}"
AGENT_DIR="${AGENT_DIR:-/opt/isyone/agent}"
COMPOSE_FILE="${COMPOSE_FILE:-}"
DRY_RUN=0
ACTION="status"

print_header() {
  echo "================================="
  echo "ISY.ONE - Manutencao do Agente"
  echo "================================="
  echo "Data: $(date)"
  echo "Usuario: $(whoami)"
  echo "Host: $(hostname)"
  echo ""
}

usage() {
  cat <<EOF
Uso:
  ./isyone_maintenance.sh [acao] [opcoes]

Acoes:
  status          Checa servico do agente, Docker e uso basico do servidor
  docker          Lista containers Docker em execucao
  clean-logs      Remove logs de cupons antigos
  restart-agent   Reinicia o servico local do agente
  restart-docker  Reinicia containers Docker ou stack docker compose
  update-agent    Atualiza o agente no diretorio local configurado
  all             Executa status, limpeza de logs e checagem Docker

Opcoes:
  --service NOME       Nome do servico systemd do agente. Padrao: isy-agent
  --log-dir CAMINHO    Diretorio de logs de cupons. Padrao: /var/log/isyone/coupons
  --days NUMERO        Remove logs com mais de NUMERO dias. Padrao: 30
  --agent-dir CAMINHO  Diretorio de instalacao do agente. Padrao: /opt/isyone/agent
  --compose-file ARQ   Arquivo docker-compose.yml para restart-docker
  --dry-run            Mostra o que seria feito sem apagar ou reiniciar nada
  --help               Mostra esta ajuda

Exemplos:
  ./isyone_maintenance.sh status
  ./isyone_maintenance.sh clean-logs --days 45 --dry-run
  AGENT_SERVICE=isyone-agent ./isyone_maintenance.sh restart-agent
EOF
}

run_cmd() {
  if [ "$DRY_RUN" -eq 1 ]; then
    echo "[dry-run] $*"
    return 0
  fi

  "$@"
}

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Comando nao encontrado: $1"
    return 1
  fi
}

require_value() {
  OPTION_NAME="$1"
  OPTION_VALUE="${2:-}"

  if [ "$OPTION_VALUE" = "" ]; then
    echo "Valor obrigatorio nao informado para $OPTION_NAME"
    exit 2
  fi
}

check_agent_status() {
  echo "== Status do agente =="

  if command -v systemctl >/dev/null 2>&1; then
    if systemctl list-unit-files "$AGENT_SERVICE.service" --no-pager --no-legend 2>/dev/null | grep -q "$AGENT_SERVICE.service"; then
      systemctl is-active "$AGENT_SERVICE" >/dev/null 2>&1 \
        && echo "Servico $AGENT_SERVICE: ativo" \
        || echo "Servico $AGENT_SERVICE: inativo ou com falha"

      systemctl status "$AGENT_SERVICE" --no-pager --lines=12 || true
    else
      echo "Servico systemd nao encontrado: $AGENT_SERVICE"
    fi
  else
    echo "systemctl indisponivel neste ambiente."
  fi

  echo ""
}

check_server_health() {
  echo "== Saude do servidor =="
  echo "Diretorio atual: $(pwd)"
  echo ""

  echo "Uso de disco:"
  df -h / 2>/dev/null || df -h
  echo ""

  echo "Memoria:"
  if command -v free >/dev/null 2>&1; then
    free -h
  else
    echo "Comando free indisponivel."
  fi

  echo ""
}

check_docker_status() {
  echo "== Containers Docker =="

  if ! require_cmd docker; then
    echo ""
    return 0
  fi

  if ! docker info >/dev/null 2>&1; then
    echo "Docker nao esta acessivel para o usuario atual."
    echo ""
    return 0
  fi

  docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
  echo ""
}

clean_coupon_logs() {
  echo "== Limpeza de logs de cupons =="
  echo "Diretorio: $COUPON_LOG_DIR"
  echo "Retencao: $LOG_RETENTION_DAYS dias"

  if [ ! -d "$COUPON_LOG_DIR" ]; then
    echo "Diretorio nao encontrado. Nada para limpar."
    echo ""
    return 0
  fi

  echo "Arquivos candidatos:"
  find "$COUPON_LOG_DIR" -type f -name '*.log' -mtime +"$LOG_RETENTION_DAYS" -print

  if [ "$DRY_RUN" -eq 1 ]; then
    echo "[dry-run] Nenhum arquivo removido."
  else
    find "$COUPON_LOG_DIR" -type f -name '*.log' -mtime +"$LOG_RETENTION_DAYS" -delete
    echo "Logs antigos removidos."
  fi

  echo ""
}

restart_agent() {
  echo "== Reinicio do agente =="

  if ! command -v systemctl >/dev/null 2>&1; then
    echo "systemctl indisponivel neste ambiente."
    echo ""
    return 1
  fi

  run_cmd systemctl restart "$AGENT_SERVICE"
  systemctl is-active "$AGENT_SERVICE" >/dev/null 2>&1 \
    && echo "Servico $AGENT_SERVICE reiniciado e ativo." \
    || echo "Servico $AGENT_SERVICE reiniciado, mas nao ficou ativo."

  echo ""
}

restart_docker_containers() {
  echo "== Reinicio dos containers Docker =="

  if ! require_cmd docker; then
    echo ""
    return 1
  fi

  if [ "$COMPOSE_FILE" != "" ]; then
    if [ ! -f "$COMPOSE_FILE" ]; then
      echo "Arquivo compose nao encontrado: $COMPOSE_FILE"
      echo ""
      return 1
    fi

    if docker compose version >/dev/null 2>&1; then
      run_cmd docker compose -f "$COMPOSE_FILE" restart
    elif command -v docker-compose >/dev/null 2>&1; then
      run_cmd docker-compose -f "$COMPOSE_FILE" restart
    else
      echo "docker compose/docker-compose indisponivel."
      echo ""
      return 1
    fi
  else
    CONTAINERS="$(docker ps -q)"
    if [ "$CONTAINERS" = "" ]; then
      echo "Nenhum container em execucao."
    else
      run_cmd docker restart $CONTAINERS
    fi
  fi

  echo ""
}

update_agent() {
  echo "== Atualizacao do agente =="
  echo "Diretorio: $AGENT_DIR"

  if [ ! -d "$AGENT_DIR" ]; then
    echo "Diretorio do agente nao encontrado."
    echo ""
    return 1
  fi

  if [ -d "$AGENT_DIR/.git" ]; then
    if ! require_cmd git; then
      echo ""
      return 1
    fi

    CURRENT_DIR="$(pwd)"
    cd "$AGENT_DIR"
    run_cmd git pull --ff-only
    cd "$CURRENT_DIR"
  else
    echo "Diretorio nao possui repositorio Git. Atualizacao automatica ignorada."
  fi

  restart_agent
}

run_status() {
  check_agent_status
  check_server_health
  check_docker_status
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    status|docker|clean-logs|restart-agent|restart-docker|update-agent|all)
      ACTION="$1"
      shift
      ;;
    --service)
      require_value "$1" "${2:-}"
      AGENT_SERVICE="${2:-}"
      shift 2
      ;;
    --log-dir)
      require_value "$1" "${2:-}"
      COUPON_LOG_DIR="${2:-}"
      shift 2
      ;;
    --days)
      require_value "$1" "${2:-}"
      LOG_RETENTION_DAYS="${2:-}"
      shift 2
      ;;
    --agent-dir)
      require_value "$1" "${2:-}"
      AGENT_DIR="${2:-}"
      shift 2
      ;;
    --compose-file)
      require_value "$1" "${2:-}"
      COMPOSE_FILE="${2:-}"
      shift 2
      ;;
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      echo "Opcao desconhecida: $1"
      echo ""
      usage
      exit 2
      ;;
  esac
done

case "$LOG_RETENTION_DAYS" in
  ''|*[!0-9]*)
    echo "Valor invalido para --days: $LOG_RETENTION_DAYS"
    exit 2
    ;;
esac

print_header

case "$ACTION" in
  status)
    run_status
    ;;
  docker)
    check_docker_status
    ;;
  clean-logs)
    clean_coupon_logs
    ;;
  restart-agent)
    restart_agent
    ;;
  restart-docker)
    restart_docker_containers
    ;;
  update-agent)
    update_agent
    ;;
  all)
    run_status
    clean_coupon_logs
    ;;
esac

echo "Script executado com sucesso."
