# Projeto de Balanceamento de Carga P2P (Mestres/Workers)

## Objetivo

Construir uma implementação em Python compatível com Windows baseada no projeto em PDF: mestres P2P com fazendas de workers, monitoramento de carga, negociação em estilo de consenso e redirecionamento dinâmico de workers entre mestres. A solução deve interoperar com outros grupos seguindo rigorosamente o protocolo definido.

## Não Objetivos

* Não utilizar arquivos de configuração externos (todos os parâmetros devem estar definidos diretamente no código Python).
* Não possuir interface gráfica (GUI).
* Não criar extensões personalizadas do protocolo além de campos opcionais que possam ser ignorados com segurança.

---

# Visão Geral da Arquitetura

### Processos

* `master.py`
* `worker.py`
* `loadgen.py`
* `run_demo.py`

### Concorrência

Utilizar `threading` no Master para lidar simultaneamente com múltiplas conexões de Workers e outros Masters.

### Transporte

Sockets TCP com mensagens JSON delimitadas por `\n`.

### Interoperabilidade

Seguir estritamente todos os formatos de payload e tipos definidos no PDF. Campos JSON desconhecidos devem ser ignorados, mas a ausência de campos obrigatórios deve gerar erro.

---

# Componentes e Responsabilidades

## Master (`master.py`)

* Escuta conexões TCP de Workers e outros Masters.
* Mantém uma fila de tarefas e o valor atual de carga (tarefas pendentes).
* Distribui tarefas aos Workers utilizando o fluxo da Sprint 02.
* Detecta saturação e inicia a negociação da Sprint 03.
* Gerencia Workers emprestados e os libera quando a carga cai abaixo do limite de liberação.
* Registra em log todas as mensagens Master-to-Master com `request_id` e timestamp.

---

## Worker (`worker.py`)

* Conecta-se ao Master e envia Heartbeats (Sprint 01).
* Apresenta-se (Sprint 02) utilizando `WORKER_UUID` e, opcionalmente, `SERVER_UUID` quando estiver emprestado.
* Solicita e processa tarefas, reporta status e aguarda ACK.
* Trata os comandos `command_redirect` e `command_release` para reconectar quando necessário.

---

## Gerador de Carga (`loadgen.py`)

* Conecta-se ao Master e injeta tarefas para aumentar a fila e provocar saturação.

---

## Executor de Demonstração (`run_demo.py`)

* Script auxiliar para iniciar um Master e três Workers locais para uma demonstração rápida.

---

# Conformidade com o Protocolo

## Sprint 01: Heartbeat

### Worker → Master

```json
{
  "SERVER_UUID": "...",
  "TASK": "HEARTBEAT"
}
```

### Master → Worker

```json
{
  "SERVER_UUID": "...",
  "TASK": "HEARTBEAT",
  "RESPONSE": "ALIVE"
}
```

---

## Sprint 02: Ciclo de Tarefas

### Worker → Master (handshake)

```json
{
  "WORKER": "ALIVE",
  "WORKER_UUID": "..."
}
```

### Worker emprestado

```json
{
  "WORKER": "ALIVE",
  "WORKER_UUID": "...",
  "SERVER_UUID": "..."
}
```

### Master → Worker

Com tarefa:

```json
{
  "TASK": "QUERY",
  "USER": "..."
}
```

Sem tarefa:

```json
{
  "TASK": "NO_TASK"
}
```

### Worker → Master (status)

```json
{
  "STATUS": "OK|NOK",
  "TASK": "QUERY",
  "WORKER_UUID": "..."
}
```

### Master → Worker (ACK)

```json
{
  "STATUS": "ACK",
  "WORKER_UUID": "..."
}
```

---

## Sprint 03: Comunicação Master-to-Master

### Formato das mensagens

```json
{
  "type": "request_help | response_accepted | response_rejected | command_redirect | register_temporary_worker | command_release | notify_worker_returned",
  "request_id": "uuid-v4",
  "payload": {}
}
```

### request_help

Inclui:

* `master_id`
* `current_load`
* `capacity`
* `workers_needed`

### response_accepted

Inclui:

* `workers_offered`
* `worker_details` (ID + endereço)

### response_rejected

Inclui:

* `reason`

### command_redirect

Enviado pelo Master B ao Worker.

Inclui:

* `new_master_address`

### register_temporary_worker

Enviado pelo Worker ao novo Master.

Inclui:

* `worker_id`
* `original_master_address`

### command_release

Enviado pelo Master A ao Worker emprestado.

Inclui:

* `original_master_address`

### notify_worker_returned

Enviado pelo Master A ao Master B.

Inclui:

* `worker_id`

---

# Carga, Saturação e Histerese

Os parâmetros `capacity` e `release_threshold` devem ser definidos em `master.py`.

### Saturação

```text
current_load > capacity
```

Dispara um `request_help`.

### Liberação

```text
current_load < release_threshold
```

Dispara:

* `command_release`
* `notify_worker_returned`

---

# Tratamento de Erros e Timeouts

* Campos JSON desconhecidos devem ser ignorados.
* Campos obrigatórios ausentes devem gerar logs de erro controlados.
* Timeout do Worker aguardando resposta do Master: **5 segundos**.
* Timeout do Master aguardando resposta de outro Master: **5 segundos**.
* Após timeout, o Master deve tentar o próximo vizinho disponível.

---

# Observabilidade

Registrar em log:

### Todas as mensagens Master-to-Master

Com:

* `request_id`
* `type`
* timestamp

### Ciclo de vida de Workers emprestados

Eventos:

* emprestado
* registrado
* tarefas executadas
* devolvido

---

# Cobertura Obrigatória do Backlog (PDF)

Este projeto cobre as tarefas 01, 02 e 03 do backlog do PDF por meio da implementação de:

* Infraestrutura TCP com JSON delimitado por quebra de linha (`\n`).
* Requisição e resposta de Heartbeat.
* Parsing e resposta de Heartbeat no lado do Master.

---

# Estratégia de Testes

### Testes Manuais

* Testes rápidos utilizando `run_demo.py`.
* Execução dos processos separadamente.

### Verificação de Conformidade

* Validação dos payloads utilizando exemplos do protocolo.

### Testes de Robustez

* Validação de timeout.
* Validação de reconexão.
* Encerramento e reinicialização de processos para verificar recuperação do sistema.
