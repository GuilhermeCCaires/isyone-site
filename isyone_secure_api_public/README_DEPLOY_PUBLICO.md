# Deploy público sem localhost - Render

Este projeto foi ajustado para rodar em ambiente público usando Docker no Render.
O Render define a porta automaticamente pela variável `PORT`, e o Dockerfile já usa:

```bash
gunicorn --bind 0.0.0.0:${PORT:-5000} --workers 2 app:app
```

## Passo a passo

1. Envie estes arquivos para o GitHub.
2. Acesse https://render.com.
3. Clique em **New +** > **Web Service**.
4. Selecione o repositório `isyone-site`.
5. Em **Environment**, escolha **Docker**.
6. Em **Environment Variables**, cadastre:

```text
ISY_INITIAL_TOKEN=coloque-um-token-forte-aqui
```

Exemplo:

```text
ISY_INITIAL_TOKEN=IsyOne@2026-token-seguro
```

7. Clique em **Create Web Service**.

O Render irá gerar uma URL pública parecida com:

```text
https://isyone-secure-api.onrender.com
```

## Como acessar

A interface web ficará em:

```text
https://sua-url-do-render.onrender.com/
```

A listagem de scripts ficará em:

```text
https://sua-url-do-render.onrender.com/api/scripts
```

A execução de scripts exige o cabeçalho HTTP:

```text
X-Isy-Token: seu-token
```

Exemplo com PowerShell:

```powershell
$headers = @{ "X-Isy-Token" = "IsyOne@2026-token-seguro" }
$body = '{"params":["Guilherme"]}'
Invoke-RestMethod -Uri "https://sua-url-do-render.onrender.com/api/scripts/hello/run" -Method POST -Headers $headers -Body $body -ContentType "application/json"
```

## Observação importante sobre scripts

No Render, os scripts `.sh` executam dentro do container na nuvem, não no seu computador.
Para executar scripts em servidores de restaurantes, a solução correta em produção é instalar um agente local nos servidores dos clientes ou usar uma VPS/infraestrutura acessível pela aplicação.
