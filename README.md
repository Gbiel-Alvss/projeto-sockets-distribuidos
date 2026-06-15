# P2P Load Balancing (Master/Worker)

Projeto de Arquitetura de Sistemas Distribuidos: Masters e Workers com balanceamento de carga P2P, seguindo o protocolo do PDF.

## Requisitos
- Windows
- Python 3.11+

## Estrutura
- `master.py`: servidor TCP, fila de tarefas, negociacao P2P
- `worker.py`: cliente TCP, heartbeat, ciclo de tarefas, redirecionamento
- `loadgen.py`: injeta tarefas para simular carga
- `protocol.py`: validacao de payloads
- `net.py`: framing JSON com delimitador `\n`

## Como rodar (local)
1. Terminal 1 (Master):
   ```
   python master.py
   ```
2. Terminal 2..4 (Workers):
   ```
   python worker.py
   ```
3. Terminal 5 (Carga):
   ```
   python loadgen.py
   ```

## Demo rapida
```
python run_demo.py
```

## Configuracao (dentro dos .py)
Edite os valores no topo dos arquivos:

### master.py
- `MASTER_ID`, `HOST`, `PORT`
- `PEERS`: lista de masters vizinhos (ip:porta)
- `NEIGHBORS`: mapa `master_id -> ip:porta`
- `CAPACITY`, `RELEASE_THRESHOLD`
- `TASK_GENERATOR_COUNT`: quantas tasks o master gera automaticamente ao iniciar
- `TASK_GENERATOR_DELAY`: intervalo entre tasks geradas pelo master

Exemplo no Windows PowerShell:
```powershell
$env:TASK_GENERATOR_COUNT = "50"
$env:TASK_GENERATOR_DELAY = "0.1"
python master.py
```

### worker.py
- `WORKER_ID`
- `MASTER_ID`, `MASTER_HOST`, `MASTER_PORT`

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

## Interoperabilidade
- O Master aceita Workers externos que sigam o protocolo.
- Os Workers podem ser redirecionados para Masters externos via `command_redirect`.

## Observacoes
- JSON sempre termina com `\n`.
- Campos desconhecidos sao ignorados; campos obrigatorios faltando geram log de erro.
- Timeouts de 5s para respostas de Master e Worker.
