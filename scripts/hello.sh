#!/bin/sh
NAME="Mundo"
while [ $# -gt 0 ]; do
  case "$1" in
    --name)
      NAME="$2"
      shift 2
      ;;
    *)
      shift
      ;;
  esac
done
echo "Olá, $NAME! Script executado com sucesso."
