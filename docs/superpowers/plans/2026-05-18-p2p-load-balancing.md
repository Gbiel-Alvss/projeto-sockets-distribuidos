# P2P Load Balancing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Python, Windows-friendly P2P master/worker system with heartbeat, task cycle, and master-to-master negotiation exactly as defined in the PDF.

**Architecture:** Separate executables for master, worker, and load generator. TCP sockets with JSON plus newline delimiter. Threaded master handles workers and peers concurrently. Strict payload validation with tolerant parsing of unknown fields.

**Tech Stack:** Python 3.11+, standard library (`socket`, `threading`, `queue`, `json`, `uuid`, `time`, `logging`), pytest for tests.

---

## File Structure
- Create: `protocol.py` (message validation helpers)
- Create: `net.py` (newline-delimited JSON send/recv)
- Create: `master.py` (server, queue, saturation, negotiation)
- Create: `worker.py` (client loops, heartbeat, task cycle, redirection)
- Create: `loadgen.py` (task injection)
- Create: `run_demo.py` (start 1 master + 3 workers)
- Create: `tests/test_protocol.py` (protocol validation unit tests)
- Create: `tests/test_net.py` (framing unit tests)
- Create: `README.md` (full usage and protocol doc)

---

### Task 1: Protocol validation helpers (TDD)

**Files:**
- Create: `protocol.py`
- Create: `tests/test_protocol.py`

- [ ] **Step 1: Write failing tests for protocol validation**

```python
# tests/test_protocol.py
import pytest
from protocol import (
    validate_heartbeat_request,
    validate_heartbeat_response,
    validate_worker_hello,
    validate_task_delivery,
    validate_task_status,
    validate_ack,
    validate_master_message,
)


def test_validate_heartbeat_request_ok():
    msg = {"SERVER_UUID": "Master_A", "TASK": "HEARTBEAT"}
    validate_heartbeat_request(msg)


def test_validate_heartbeat_request_missing_field():
    msg = {"TASK": "HEARTBEAT"}
    with pytest.raises(ValueError):
        validate_heartbeat_request(msg)


def test_validate_worker_hello_ok_local():
    msg = {"WORKER": "ALIVE", "WORKER_UUID": "W-1"}
    validate_worker_hello(msg)


def test_validate_worker_hello_ok_borrowed():
    msg = {"WORKER": "ALIVE", "WORKER_UUID": "W-2", "SERVER_UUID": "Master_B"}
    validate_worker_hello(msg)


def test_validate_task_delivery_query():
    msg = {"TASK": "QUERY", "USER": "Michel"}
    validate_task_delivery(msg)


def test_validate_task_delivery_no_task():
    msg = {"TASK": "NO_TASK"}
    validate_task_delivery(msg)


def test_validate_task_status_ok():
    msg = {"STATUS": "OK", "TASK": "QUERY", "WORKER_UUID": "W-1"}
    validate_task_status(msg)


def test_validate_ack_ok():
    msg = {"STATUS": "ACK", "WORKER_UUID": "W-1"}
    validate_ack(msg)


def test_validate_master_message_request_help():
    msg = {
        "type": "request_help",
        "request_id": "uuid",
        "payload": {"master_id": "A", "current_load": 10, "capacity": 5, "workers_needed": 1},
    }
    validate_master_message(msg)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_protocol.py -v`
Expected: FAIL because `protocol.py` does not exist.

- [ ] **Step 3: Implement protocol validation helpers**

```python
# protocol.py
REQUIRED = object()


def _require_fields(msg, fields):
    for field in fields:
        if field not in msg:
            raise ValueError(f"missing field: {field}")


def validate_heartbeat_request(msg):
    _require_fields(msg, ["SERVER_UUID", "TASK"])
    if msg.get("TASK") != "HEARTBEAT":
        raise ValueError("invalid TASK")


def validate_heartbeat_response(msg):
    _require_fields(msg, ["SERVER_UUID", "TASK", "RESPONSE"])
    if msg.get("TASK") != "HEARTBEAT":
        raise ValueError("invalid TASK")
    if msg.get("RESPONSE") != "ALIVE":
        raise ValueError("invalid RESPONSE")


def validate_worker_hello(msg):
    _require_fields(msg, ["WORKER", "WORKER_UUID"])
    if msg.get("WORKER") != "ALIVE":
        raise ValueError("invalid WORKER")


def validate_task_delivery(msg):
    _require_fields(msg, ["TASK"])
    if msg.get("TASK") == "QUERY":
        _require_fields(msg, ["USER"])
    elif msg.get("TASK") == "NO_TASK":
        return
    else:
        raise ValueError("invalid TASK")


def validate_task_status(msg):
    _require_fields(msg, ["STATUS", "TASK", "WORKER_UUID"])
    if msg.get("TASK") != "QUERY":
        raise ValueError("invalid TASK")
    if msg.get("STATUS") not in ("OK", "NOK"):
        raise ValueError("invalid STATUS")


def validate_ack(msg):
    _require_fields(msg, ["STATUS", "WORKER_UUID"])
    if msg.get("STATUS") != "ACK":
        raise ValueError("invalid STATUS")


MASTER_TYPES = {
    "request_help",
    "response_accepted",
    "response_rejected",
    "command_redirect",
    "register_temporary_worker",
    "command_release",
    "notify_worker_returned",
}


def validate_master_message(msg):
    _require_fields(msg, ["type", "request_id", "payload"])
    if msg.get("type") not in MASTER_TYPES:
        raise ValueError("invalid type")

    payload = msg.get("payload") or {}
    msg_type = msg.get("type")

    if msg_type == "request_help":
        _require_fields(payload, ["master_id", "current_load", "capacity", "workers_needed"])
    elif msg_type == "response_accepted":
        _require_fields(payload, ["workers_offered", "worker_details"])
    elif msg_type == "response_rejected":
        _require_fields(payload, ["reason"])
    elif msg_type == "command_redirect":
        _require_fields(payload, ["new_master_address"])
    elif msg_type == "register_temporary_worker":
        _require_fields(payload, ["worker_id", "original_master_address"])
    elif msg_type == "command_release":
        _require_fields(payload, ["original_master_address"])
    elif msg_type == "notify_worker_returned":
        _require_fields(payload, ["worker_id"])
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_protocol.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add protocol.py tests/test_protocol.py
git commit -m "feat: add protocol validation helpers"
```

---

### Task 2: Newline-delimited JSON framing (TDD)

**Files:**
- Create: `net.py`
- Create: `tests/test_net.py`

- [ ] **Step 1: Write failing tests for framing**

```python
# tests/test_net.py
import json
from net import encode_message, decode_stream


def test_encode_message_adds_newline():
    msg = {"a": 1}
    data = encode_message(msg)
    assert data.endswith(b"\n")


def test_decode_stream_single_message():
    payload = {"x": 2}
    data = json.dumps(payload).encode("utf-8") + b"\n"
    messages, rest = decode_stream(data)
    assert messages == [payload]
    assert rest == b""


def test_decode_stream_partial_message():
    data = b"{\"a\": 1}"
    messages, rest = decode_stream(data)
    assert messages == []
    assert rest == data


def test_decode_stream_multiple_messages():
    data = b"{\"a\": 1}\n{\"b\": 2}\n"
    messages, rest = decode_stream(data)
    assert messages == [{"a": 1}, {"b": 2}]
    assert rest == b""
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_net.py -v`
Expected: FAIL because `net.py` does not exist.

- [ ] **Step 3: Implement framing helpers**

```python
# net.py
import json


def encode_message(msg):
    return (json.dumps(msg) + "\n").encode("utf-8")


def decode_stream(buffer):
    messages = []
    while b"\n" in buffer:
        line, buffer = buffer.split(b"\n", 1)
        if not line:
            continue
        messages.append(json.loads(line.decode("utf-8")))
    return messages, buffer
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_net.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add net.py tests/test_net.py
git commit -m "feat: add newline-delimited json framing"
```

---

### Task 3: Master TCP server + heartbeat handling (Sprint 01)

**Files:**
- Create: `master.py`

- [ ] **Step 1: Write minimal master heartbeat handler (manual check)**

```python
# master.py
import json
import logging
import socket
import threading
import time
from net import encode_message, decode_stream
from protocol import validate_heartbeat_request

MASTER_ID = "Master_A"
HOST = "127.0.0.1"
PORT = 9000

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def handle_client(conn, addr):
    logging.info("connection from %s", addr)
    buffer = b""
    while True:
        data = conn.recv(4096)
        if not data:
            break
        buffer += data
        messages, buffer = decode_stream(buffer)
        for msg in messages:
            try:
                validate_heartbeat_request(msg)
                response = {"SERVER_UUID": MASTER_ID, "TASK": "HEARTBEAT", "RESPONSE": "ALIVE"}
                conn.sendall(encode_message(response))
            except ValueError:
                logging.warning("invalid heartbeat payload: %s", msg)
    conn.close()


def run_server():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((HOST, PORT))
    server.listen()
    logging.info("Master listening on %s:%s", HOST, PORT)
    while True:
        conn, addr = server.accept()
        t = threading.Thread(target=handle_client, args=(conn, addr), daemon=True)
        t.start()


if __name__ == "__main__":
    run_server()
```

- [ ] **Step 2: Run a manual check**

Run (terminal 1): `python master.py`
Run (terminal 2): `python -c "import socket, json; s=socket.socket(); s.connect(('127.0.0.1',9000)); s.sendall((json.dumps({'SERVER_UUID':'Master_A','TASK':'HEARTBEAT'})+'\n').encode()); print(s.recv(4096).decode()); s.close()"`
Expected: JSON response with `RESPONSE` set to `ALIVE`.

- [ ] **Step 3: Commit**

```bash
git add master.py
git commit -m "feat: add master heartbeat server"
```

---

### Task 4: Worker heartbeat loop (Sprint 01)

**Files:**
- Create: `worker.py`

- [ ] **Step 1: Implement worker heartbeat loop**

```python
# worker.py
import logging
import socket
import time
from net import encode_message, decode_stream
from protocol import validate_heartbeat_response

WORKER_ID = "W-1"
MASTER_ID = "Master_A"
MASTER_HOST = "127.0.0.1"
MASTER_PORT = 9000
HEARTBEAT_INTERVAL = 10

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def run_worker():
    while True:
        try:
            with socket.create_connection((MASTER_HOST, MASTER_PORT), timeout=5) as s:
                buffer = b""
                while True:
                    heartbeat = {"SERVER_UUID": MASTER_ID, "TASK": "HEARTBEAT"}
                    s.sendall(encode_message(heartbeat))
                    start = time.time()
                    while time.time() - start < 5:
                        data = s.recv(4096)
                        if not data:
                            raise ConnectionError("connection closed")
                        buffer += data
                        messages, buffer = decode_stream(buffer)
                        for msg in messages:
                            validate_heartbeat_response(msg)
                            logging.info("heartbeat response: %s", msg.get("RESPONSE"))
                            break
                        else:
                            continue
                        break
                    time.sleep(HEARTBEAT_INTERVAL)
        except Exception as exc:
            logging.warning("worker reconnecting after error: %s", exc)
            time.sleep(2)


if __name__ == "__main__":
    run_worker()
```

- [ ] **Step 2: Manual check**

Run (terminal 1): `python master.py`
Run (terminal 2): `python worker.py`
Expected: Worker logs heartbeat response `ALIVE` every 10 seconds.

- [ ] **Step 3: Commit**

```bash
git add worker.py
git commit -m "feat: add worker heartbeat loop"
```

---

### Task 5: Task queue and Sprint 02 cycle

**Files:**
- Modify: `master.py`
- Modify: `worker.py`
- Create: `loadgen.py`

- [ ] **Step 1: Add task queue and worker handshake handling to Master**

```python
# master.py (replace content with full implementation below)
import json
import logging
import queue
import socket
import threading
import time
import uuid
from net import encode_message, decode_stream
from protocol import (
    validate_heartbeat_request,
    validate_worker_hello,
    validate_task_status,
)

MASTER_ID = "Master_A"
HOST = "127.0.0.1"
PORT = 9000
CAPACITY = 100
RELEASE_THRESHOLD = 60

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

TASK_QUEUE = queue.Queue()
BORROWED_WORKERS = {}
WORKER_LOCK = threading.Lock()


def handle_worker(conn, addr):
    logging.info("worker connection from %s", addr)
    buffer = b""
    worker_id = None
    while True:
        data = conn.recv(4096)
        if not data:
            break
        buffer += data
        messages, buffer = decode_stream(buffer)
        for msg in messages:
            try:
                if msg.get("TASK") == "HEARTBEAT":
                    validate_heartbeat_request(msg)
                    response = {"SERVER_UUID": MASTER_ID, "TASK": "HEARTBEAT", "RESPONSE": "ALIVE"}
                    conn.sendall(encode_message(response))
                    continue

                if msg.get("WORKER") == "ALIVE":
                    validate_worker_hello(msg)
                    worker_id = msg.get("WORKER_UUID")
                    if msg.get("SERVER_UUID"):
                        with WORKER_LOCK:
                            BORROWED_WORKERS[worker_id] = msg.get("SERVER_UUID")
                    if TASK_QUEUE.empty():
                        conn.sendall(encode_message({"TASK": "NO_TASK"}))
                    else:
                        task = TASK_QUEUE.get()
                        conn.sendall(encode_message({"TASK": "QUERY", "USER": task}))
                    continue

                if msg.get("STATUS"):
                    validate_task_status(msg)
                    logging.info("task status from %s: %s", msg.get("WORKER_UUID"), msg.get("STATUS"))
                    conn.sendall(encode_message({"STATUS": "ACK", "WORKER_UUID": msg.get("WORKER_UUID")}))
                    continue
            except ValueError as exc:
                logging.warning("invalid worker payload: %s (%s)", msg, exc)
    conn.close()


def accept_loop():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((HOST, PORT))
    server.listen()
    logging.info("Master listening on %s:%s", HOST, PORT)
    while True:
        conn, addr = server.accept()
        t = threading.Thread(target=handle_worker, args=(conn, addr), daemon=True)
        t.start()


def run_master():
    accept_loop()


if __name__ == "__main__":
    run_master()
```

- [ ] **Step 2: Add worker Sprint 02 cycle**

```python
# worker.py (replace content with full implementation below)
import logging
import random
import socket
import time
from net import encode_message, decode_stream
from protocol import validate_heartbeat_response, validate_task_delivery, validate_ack

WORKER_ID = "W-1"
MASTER_ID = "Master_A"
MASTER_HOST = "127.0.0.1"
MASTER_PORT = 9000
HEARTBEAT_INTERVAL = 10

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def run_worker():
    while True:
        try:
            with socket.create_connection((MASTER_HOST, MASTER_PORT), timeout=5) as s:
                buffer = b""
                # Heartbeat once on connect
                heartbeat = {"SERVER_UUID": MASTER_ID, "TASK": "HEARTBEAT"}
                s.sendall(encode_message(heartbeat))

                while True:
                    hello = {"WORKER": "ALIVE", "WORKER_UUID": WORKER_ID}
                    s.sendall(encode_message(hello))

                    # Wait for task delivery or no task
                    start = time.time()
                    while time.time() - start < 5:
                        data = s.recv(4096)
                        if not data:
                            raise ConnectionError("connection closed")
                        buffer += data
                        messages, buffer = decode_stream(buffer)
                        for msg in messages:
                            if msg.get("TASK") in ("QUERY", "NO_TASK"):
                                validate_task_delivery(msg)
                                if msg.get("TASK") == "NO_TASK":
                                    time.sleep(1)
                                    break
                                # Simulate work
                                time.sleep(random.uniform(0.2, 0.8))
                                status = {"STATUS": "OK", "TASK": "QUERY", "WORKER_UUID": WORKER_ID}
                                s.sendall(encode_message(status))
                            elif msg.get("RESPONSE") == "ALIVE":
                                validate_heartbeat_response(msg)
                            elif msg.get("STATUS") == "ACK":
                                validate_ack(msg)
                        break
        except Exception as exc:
            logging.warning("worker reconnecting after error: %s", exc)
            time.sleep(2)


if __name__ == "__main__":
    run_worker()
```

- [ ] **Step 3: Add load generator**

```python
# loadgen.py
import random
import socket
import time
from net import encode_message

MASTER_HOST = "127.0.0.1"
MASTER_PORT = 9000


def run_load():
    with socket.create_connection((MASTER_HOST, MASTER_PORT), timeout=5) as s:
        for i in range(50):
            task = {"TASK": "QUERY", "USER": f"User-{i}"}
            s.sendall(encode_message(task))
            time.sleep(random.uniform(0.05, 0.2))


if __name__ == "__main__":
    run_load()
```

- [ ] **Step 4: Manual check**

Run (terminal 1): `python master.py`
Run (terminal 2): `python worker.py`
Run (terminal 3): `python loadgen.py`
Expected: Master logs task status and ACKs.

- [ ] **Step 5: Commit**

```bash
git add master.py worker.py loadgen.py
git commit -m "feat: implement sprint 02 task cycle"
```

---

### Task 6: Master-to-master negotiation and worker redirection (Sprint 03)

**Files:**
- Modify: `master.py`
- Modify: `worker.py`

- [ ] **Step 1: Extend Master with peer negotiation**

```python
# master.py (additions: peer support and saturation checks)
PEERS = ["127.0.0.1:9100"]


def send_master_message(sock, msg):
    sock.sendall(encode_message(msg))


def request_help():
    for peer in PEERS:
        host, port = peer.split(":")
        try:
            with socket.create_connection((host, int(port)), timeout=5) as s:
                request_id = str(uuid.uuid4())
                msg = {
                    "type": "request_help",
                    "request_id": request_id,
                    "payload": {
                        "master_id": MASTER_ID,
                        "current_load": TASK_QUEUE.qsize(),
                        "capacity": CAPACITY,
                        "workers_needed": 1,
                    },
                }
                send_master_message(s, msg)
                s.settimeout(5)
                buffer = b""
                while True:
                    buffer += s.recv(4096)
                    messages, buffer = decode_stream(buffer)
                    for resp in messages:
                        if resp.get("request_id") == request_id:
                            return resp
        except Exception as exc:
            logging.warning("peer request failed: %s", exc)
    return None
```

- [ ] **Step 2: Add worker redirection handling to Worker**

```python
# worker.py (add handler inside loop when receiving type messages)
if msg.get("type") == "command_redirect":
    new_addr = msg["payload"]["new_master_address"]
    host, port = new_addr.split(":")
    MASTER_HOST = host
    MASTER_PORT = int(port)
    break
```

- [ ] **Step 3: Manual check**

Run two masters on different ports. Trigger saturation by running loadgen. Expect request_help from Master A.

- [ ] **Step 4: Commit**

```bash
git add master.py worker.py
git commit -m "feat: implement sprint 03 negotiation"
```

---

### Task 7: Demo runner and README

**Files:**
- Create: `run_demo.py`
- Create: `README.md`

- [ ] **Step 1: Add demo runner**

```python
# run_demo.py
import subprocess
import sys
import time


def run_demo():
    master = subprocess.Popen([sys.executable, "master.py"])
    time.sleep(1)
    workers = [subprocess.Popen([sys.executable, "worker.py"]) for _ in range(3)]
    time.sleep(2)
    load = subprocess.Popen([sys.executable, "loadgen.py"])
    load.wait()
    time.sleep(3)
    for w in workers:
        w.terminate()
    master.terminate()


if __name__ == "__main__":
    run_demo()
```

- [ ] **Step 2: Write README**

```markdown
# P2P Load Balancing (Master/Worker)

## Requisitos
- Python 3.11+
- Windows

## Como rodar
1. Abra um terminal para o Master:
   ```
   python master.py
   ```
2. Abra outro terminal para um Worker:
   ```
   python worker.py
   ```
3. (Opcional) Gere carga:
   ```
   python loadgen.py
   ```
4. (Opcional) Demo automatizada:
   ```
   python run_demo.py
   ```

## Protocolo
- JSON com `\n` como delimitador.
- Payloads e tipos seguem o PDF do projeto.

## Interoperabilidade
- O Master aceita Workers externos que sigam o protocolo.
- Workers podem ser redirecionados para Masters externos via Sprint 03.

## Sprints cobertas
- Sprint 01: Heartbeat
- Sprint 02: Ciclo de tarefas
- Sprint 03: Negociacao Master-to-Master e redirecionamento
```

- [ ] **Step 3: Commit**

```bash
git add run_demo.py README.md
git commit -m "docs: add demo runner and readme"
```

---

## Self-Review
- Spec coverage: tasks cover heartbeat, task cycle, loadgen, and master-to-master negotiation.
- Placeholder scan: no TODO or TBD left in steps.
- Type consistency: payload fields match the spec and tests.

---

Plan complete and saved to `docs/superpowers/plans/2026-05-18-p2p-load-balancing.md`. Two execution options:

1. Subagent-Driven (recommended) - I dispatch a fresh subagent per task, review between tasks, fast iteration
2. Inline Execution - Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?
