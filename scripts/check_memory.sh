#!/bin/sh
echo "Uso de memória:"
free -h 2>/dev/null || vm_stat 2>/dev/null || echo "Comando de memória não disponível neste ambiente."
