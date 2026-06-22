# P2P Load Balancing (Master/Worker)

Projeto de Arquitetura de Sistemas Distribuidos: Masters e Workers com balanceamento de carga P2P.

## Requisitos
- Windows
- Python 3.11+

## Estrutura
- `master.py`: servidor TCP com config no topo, fila de tarefas, negociacao P2P
- `worker.py`: cliente TCP, heartbeat, ciclo de tarefas, redirecionamento
- `worker-2.py`: worker com config padrao para Master_A
- `loadgen.py`: injeta tarefas para simular carga
- `protocol.py`: validacao de payloads
- `net.py`: framing JSON com delimitador `\n`

## Como rodar (2 maquinas)

Edite as configuracoes no topo do `master.py` antes de rodar em cada maquina.

### Maquina 1 (Master_A + Worker)

Em `master.py`:
```python
MASTER_ID = "Master_A"
PORT = 10000
PEERS = ["<IP_DO_MESTRE_B>:9100"]
NEIGHBORS = {"Master_B": "<IP_DO_MESTRE_B>:9100"}
TASK_GENERATOR_COUNT = 0
```

Depois rode os 2 terminais:
```powershell
python master.py
python worker-2.py
```

### Maquina 2 (Master_B saturado, sem worker)

Em `master.py`:
```python
MASTER_ID = "Master_B"
PORT = 9100
PEERS = ["<IP_DO_MESTRE_A>:10000"]
NEIGHBORS = {"Master_A": "<IP_DO_MESTRE_A>:10000"}
TASK_GENERATOR_COUNT = 200
TASK_GENERATOR_DELAY = 0.05
```

Depois:
```powershell
python master.py
```

> A Maquina 2 gera 200 tasks, a fila enche (>100), ele pede o worker emprestado a Maquina 1, o worker processa as tasks e quando a fila fica < 60 ele e devolvido.

## Como rodar (local, 3 terminais)

Edite `master.py` para Master_A (porta 10000), rode:

### Terminal 1 (Master_A):
```powershell
python master.py
```

Edite `master.py` para Master_B (porta 9100, tasks=200), rode:

### Terminal 2 (Master_B):
```powershell
python master.py
```

### Terminal 3 (Worker):
```powershell
python worker-2.py
```

## Configuracao do master.py
Edite as variaveis no topo do arquivo:
- `MASTER_ID`: identificador do master
- `PORT`: porta do master
- `PEERS`: lista de masters vizinhos (`["ip:porta"]`)
- `NEIGHBORS`: mapa de vizinhos (`{"id": "ip:porta"}`)
- `CAPACITY`: limite de tasks antes de pedir ajuda
- `RELEASE_THRESHOLD`: quando devolver workers emprestados
- `TASK_GENERATOR_COUNT`: tasks geradas automaticamente ao iniciar
- `TASK_GENERATOR_DELAY`: intervalo entre tasks geradas

## Configuracao do worker (worker-2.py)
- `WORKER_ID`: identificador do worker
- `MASTER_HOST`: IP do master
- `MASTER_PORT`: porta do master
- `MASTER_ID`: ID do master

## Protocolo (resumo)
### Sprint 01 - Heartbeat
Worker -> Master:
```
{"SERVER_UUID":"Master_A","TASK":"HEARTBEAT"}
```
Master -> Worker:
```
{"SERVER_UUID":"Master_A","TASK":"HEARTBEAT","RESPONSE":"ALIVE"}
```

### Sprint 02 - Ciclo de tarefas
Worker -> Master (apresentacao):
```
{"WORKER":"ALIVE","WORKER_UUID":"W-1"}
```
Worker emprestado:
```
{"WORKER":"ALIVE","WORKER_UUID":"W-2","SERVER_UUID":"Master_B"}
```
Master -> Worker:
```
{"TASK":"QUERY","USER":"Michel"}
```
ou
```
{"TASK":"NO_TASK"}
```
Worker -> Master (status):
```
{"STATUS":"OK","TASK":"QUERY","WORKER_UUID":"W-1"}
```
Master -> Worker (ack):
```
{"STATUS":"ACK","WORKER_UUID":"W-1"}
```

### Sprint 03 - Master to Master
Estrutura:
```
{
  "type": "request_help",
  "request_id": "uuid",
  "payload": {"master_id":"A","current_load":150,"capacity":100,"workers_needed":2}
}
```
Tipos suportados:
- `request_help`
- `response_accepted`
- `response_rejected`
- `command_redirect`
- `register_temporary_worker`
- `command_release`
- `notify_worker_returned`

## Observacoes
- JSON sempre termina com `\n`.
- Campos desconhecidos sao ignorados; campos obrigatorios faltando geram log de erro.
- Timeouts de 5s para respostas de Master e Worker.
