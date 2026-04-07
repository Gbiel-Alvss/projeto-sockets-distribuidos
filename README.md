# Projeto sockets distribuidos - Master com eleicao de workers

Este projeto roda com:
- 1 computador master inicial
- 3 computadores workers

Regra implementada:
- cada worker envia heartbeat para o master atual
- se houver 4 falhas consecutivas de conexao/heartbeat, o worker inicia eleicao
- o worker eleito como novo master e aquele com maior espaco livre em disco
- apos consenso de maioria entre os workers alcancaveis, o novo master sobe servidor e passa a responder heartbeat

## Arquivos principais
- server.py: master inicial
- common.py: funcoes de socket + runtime de eleicao/consenso
- worker_1.py: configuracao do worker A1
- worker-2.py: configuracao do worker A2
- worker_3.py: configuracao do worker A3

## Portas usadas
- 5000: heartbeat do master
- 6001: canal de eleicao do worker A1
- 6002: canal de eleicao do worker A2
- 6003: canal de eleicao do worker A3

Libere essas portas no firewall dos respectivos computadores.

## Passo 1 - ajustar IPs
Edite os 3 arquivos de worker para o IP real de cada maquina:
- worker_1.py
- worker-2.py
- worker_3.py

Em cada worker, ajuste as constantes:
- WORKER_HOST: IP da propria maquina worker
- MASTER_HOST: IP da maquina master inicial
- PEERS: IP e porta de eleicao dos outros 2 workers

Exemplo de topologia:
- master inicial: 192.168.0.10
- worker A1: 192.168.0.11
- worker A2: 192.168.0.12
- worker A3: 192.168.0.13

## Passo 2 - executar em cada computador
Use Python 3.10+.

No computador master inicial:

python server.py --host 0.0.0.0 --port 5000 --uuid MASTER-INICIAL

No computador worker A1:

python worker_1.py

No computador worker A2:

python worker-2.py

No computador worker A3:

python worker_3.py

## Como validar failover
1. Suba master e os 3 workers.
2. Verifique nos logs dos workers mensagens de master ativo.
3. Derrube o processo do master inicial.
4. Aguarde 4 ciclos de falha de heartbeat.
5. Observe logs de eleicao e anuncio de novo master.
6. Verifique os outros workers voltando a reportar heartbeat para o novo master.

## Observacoes
- Em empate de espaco livre, o desempate e pelo worker_id (ordem lexicografica).
- O calculo de maioria usa os workers alcancaveis no momento da eleicao.
- Todos os workers devem ter relogio e rede estaveis para reduzir falso positivo de downtime.
