#!/bin/sh
set -eu

AGENT_SERVICE="${AGENT_SERVICE:-isy-agent}"
COUPON_LOG_DIR="${COUPON_LOG_DIR:-/var/log/isyone/coupons}"
LOG_RETENTION_DAYS="${LOG_RETENTION_DAYS:-30}"
OUTPUT_FILE=""

usage() {
  cat <<EOF
Uso:
  ./isyone_diagnostic_report.sh [opcoes]

Opcoes:
  --service NOME       Nome do servico systemd do agente. Padrao: isy-agent
  --log-dir CAMINHO    Diretorio de logs de cupons. Padrao: /var/log/isyone/coupons
  --days NUMERO        Idade usada para contar logs antigos. Padrao: 30
  --output ARQUIVO     Salva o relatorio no arquivo informado
  --help               Mostra esta ajuda

Exemplos:
  ./isyone_diagnostic_report.sh
  ./isyone_diagnostic_report.sh --service isyone-agent
  ./isyone_diagnostic_report.sh --log-dir /var/log/isyone/coupons --days 45
  ./isyone_diagnostic_report.sh --output diagnostico-isyone.txt
EOF
}

require_value() {
  OPTION_NAME="$1"
  OPTION_VALUE="${2:-}"

  if [ "$OPTION_VALUE" = "" ]; then
    echo "Valor obrigatorio nao informado para $OPTION_NAME"
    exit 2
  fi
}

command_exists() {
  command -v "$1" >/dev/null 2>&1
}

print_section() {
  echo ""
  echo "== $1 =="
}

print_header() {
  echo "================================="
  echo "ISY.ONE - Relatorio de Diagnostico"
  echo "================================="
  echo "Data: $(date)"
  echo "Usuario: $(whoami 2>/dev/null || echo desconhecido)"
  echo "Host: $(hostname 2>/dev/null || echo desconhecido)"
  echo "Diretorio atual: $(pwd)"
}

print_os_info() {
  print_section "Sistema operacional"

  if [ -r /etc/os-release ]; then
    sed -n 's/^PRETTY_NAME=//p' /etc/os-release | tr -d '"'
  else
    uname -a 2>/dev/null || echo "Informacao de sistema indisponivel."
  fi
}

print_agent_status() {
  print_section "Agente Isy.One"
  echo "Servico configurado: $AGENT_SERVICE"

  if ! command_exists systemctl; then
    echo "systemctl indisponivel neste ambiente."
    return 0
  fi

  if systemctl list-unit-files "$AGENT_SERVICE.service" --no-pager --no-legend 2>/dev/null | grep -q "$AGENT_SERVICE.service"; then
    if systemctl is-active "$AGENT_SERVICE" >/dev/null 2>&1; then
      echo "Status: ativo"
    else
      echo "Status: inativo ou com falha"
    fi

    echo ""
    echo "Ultimas linhas do systemctl status:"
    systemctl status "$AGENT_SERVICE" --no-pager --lines=12 2>&1 || true
  else
    echo "Servico systemd nao encontrado."
  fi
}

print_docker_status() {
  print_section "Docker"

  if ! command_exists docker; then
    echo "Docker nao instalado ou nao disponivel no PATH."
    return 0
  fi

  docker --version 2>/dev/null || true

  if ! docker info >/dev/null 2>&1; then
    echo "Docker instalado, mas daemon nao esta acessivel para o usuario atual."
    return 0
  fi

  echo ""
  echo "Containers em execucao:"
  docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}' 2>/dev/null || true

  echo ""
  echo "Containers parados ou relacionados a Isy/iFood/banco:"
  docker ps -a --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}' 2>/dev/null \
    | grep -Ei 'isy|ifood|db|database|postgres|mysql|mariadb|mongo|redis|sql|cupom|coupon' \
    || echo "Nenhum container relacionado encontrado."
}

print_database_containers() {
  print_section "Containers de banco"

  if ! command_exists docker || ! docker info >/dev/null 2>&1; then
    echo "Docker indisponivel para diagnostico de banco."
    return 0
  fi

  docker ps -a --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}' 2>/dev/null \
    | grep -Ei 'db|database|postgres|mysql|mariadb|mongo|redis|sql' \
    || echo "Nenhum container de banco identificado por nome/imagem."
}

print_coupon_logs() {
  print_section "Logs de cupons"
  echo "Diretorio configurado: $COUPON_LOG_DIR"
  echo "Idade considerada antiga: mais de $LOG_RETENTION_DAYS dias"

  if [ ! -d "$COUPON_LOG_DIR" ]; then
    echo "Diretorio nao encontrado."
    return 0
  fi

  TOTAL_LOGS="$(find "$COUPON_LOG_DIR" -type f -name '*.log' 2>/dev/null | wc -l | tr -d ' ')"
  OLD_LOGS="$(find "$COUPON_LOG_DIR" -type f -name '*.log' -mtime +"$LOG_RETENTION_DAYS" 2>/dev/null | wc -l | tr -d ' ')"
  TOTAL_SIZE="$(du -sh "$COUPON_LOG_DIR" 2>/dev/null | awk '{print $1}')"

  echo "Total de arquivos .log: $TOTAL_LOGS"
  echo "Logs antigos: $OLD_LOGS"
  echo "Tamanho total do diretorio: ${TOTAL_SIZE:-indisponivel}"

  echo ""
  echo "Ultimos 10 logs modificados:"
  find "$COUPON_LOG_DIR" -type f -name '*.log' -printf '%TY-%Tm-%Td %TH:%TM %p\n' 2>/dev/null \
    | sort -r \
    | head -n 10 \
    || echo "Nao foi possivel listar os logs."
}

print_server_resources() {
  print_section "Recursos do servidor"

  echo "Uptime:"
  uptime 2>/dev/null || echo "Indisponivel."

  echo ""
  echo "Disco:"
  df -h / 2>/dev/null || df -h 2>/dev/null || echo "Indisponivel."

  echo ""
  echo "Memoria:"
  if command_exists free; then
    free -h
  else
    echo "Comando free indisponivel."
  fi

  echo ""
  echo "Carga do sistema:"
  if [ -r /proc/loadavg ]; then
    cat /proc/loadavg
  else
    echo "Indisponivel."
  fi
}

print_network_snapshot() {
  print_section "Rede"

  echo "IPs locais:"
  if command_exists hostname; then
    hostname -I 2>/dev/null || echo "hostname -I indisponivel."
  else
    echo "hostname indisponivel."
  fi

  echo ""
  echo "Portas em escuta:"
  if command_exists ss; then
    ss -tuln 2>/dev/null | head -n 25
  elif command_exists netstat; then
    netstat -tuln 2>/dev/null | head -n 25
  else
    echo "ss/netstat indisponiveis."
  fi
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --service)
      require_value "$1" "${2:-}"
      AGENT_SERVICE="$2"
      shift 2
      ;;
    --log-dir)
      require_value "$1" "${2:-}"
      COUPON_LOG_DIR="$2"
      shift 2
      ;;
    --days)
      require_value "$1" "${2:-}"
      LOG_RETENTION_DAYS="$2"
      shift 2
      ;;
    --output)
      require_value "$1" "${2:-}"
      OUTPUT_FILE="$2"
      shift 2
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

if [ "$OUTPUT_FILE" != "" ]; then
  exec >"$OUTPUT_FILE" 2>&1
fi

print_header
print_os_info
print_agent_status
print_docker_status
print_database_containers
print_coupon_logs
print_server_resources
print_network_snapshot

echo ""
echo "Relatorio de diagnostico concluido."
