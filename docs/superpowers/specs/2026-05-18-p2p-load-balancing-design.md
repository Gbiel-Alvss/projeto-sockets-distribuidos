# P2P Load Balancing Design (Masters/Workers)

**Goal**
Build a Windows-friendly Python implementation of the PDF project: P2P masters with worker farms, load monitoring, consensus-style negotiation, and dynamic worker redirection across masters. It must interoperate with other groups strictly via the defined protocol.

**Non-Goals**
- No external config files (all parameters in Python code).
- No GUI.
- No custom protocol extensions beyond optional extra fields that are safely ignored.

## Architecture Overview
- **Processes:** `master.py`, `worker.py`, `loadgen.py`, `run_demo.py`.
- **Concurrency:** `threading` in the Master to handle multiple worker/master sockets concurrently.
- **Transport:** TCP sockets with JSON messages delimited by `\n`.
- **Interoperability:** Strictly follow all payloads and types from the PDF; ignore unknown JSON fields but error on missing required fields.

## Components and Responsibilities
### Master (`master.py`)
- Listens for Worker and Master connections on TCP.
- Maintains a task queue and current load (pending tasks).
- Distributes tasks to workers using Sprint 02 flow.
- Detects saturation and triggers Sprint 03 negotiation.
- Manages borrowed workers and releases them when load drops below release threshold.
- Logs all Master-to-Master messages with `request_id` and timestamps.

### Worker (`worker.py`)
- Connects to Master and sends Heartbeat (Sprint 01).
- Presents itself (Sprint 02) with `WORKER_UUID` and optional `SERVER_UUID` when borrowed.
- Requests and processes tasks, reports status, waits for ACK.
- Handles `command_redirect` and `command_release` to reconnect as needed.

### Load Generator (`loadgen.py`)
- Connects to Master and injects tasks to grow the queue and trigger saturation.

### Demo Runner (`run_demo.py`)
- Convenience script to start one Master and three local Workers for a quick demo.

## Protocol Compliance
### Sprint 01: Heartbeat
- Worker -> Master: `{"SERVER_UUID":"...","TASK":"HEARTBEAT"}`
- Master -> Worker: `{"SERVER_UUID":"...","TASK":"HEARTBEAT","RESPONSE":"ALIVE"}`

### Sprint 02: Task Cycle
- Worker -> Master (handshake):
  - `{"WORKER":"ALIVE","WORKER_UUID":"..."}`
  - Borrowed: `{"WORKER":"ALIVE","WORKER_UUID":"...","SERVER_UUID":"..."}`
- Master -> Worker:
  - With task: `{"TASK":"QUERY","USER":"..."}`
  - No task: `{"TASK":"NO_TASK"}`
- Worker -> Master (status): `{"STATUS":"OK|NOK","TASK":"QUERY","WORKER_UUID":"..."}`
- Master -> Worker (ack): `{"STATUS":"ACK","WORKER_UUID":"..."}`

### Sprint 03: Master-to-Master
Message format:
```
{
  "type": "request_help | response_accepted | response_rejected | command_redirect | register_temporary_worker | command_release | notify_worker_returned",
  "request_id": "uuid-v4",
  "payload": { ... }
}
```
- `request_help`: includes `master_id`, `current_load`, `capacity`, `workers_needed`.
- `response_accepted`: includes `workers_offered`, `worker_details` (id + address).
- `response_rejected`: includes `reason`.
- `command_redirect`: sent by Master B to Worker; includes `new_master_address`.
- `register_temporary_worker`: sent by Worker to new Master; includes `worker_id` and `original_master_address`.
- `command_release`: sent by Master A to borrowed Worker; includes `original_master_address`.
- `notify_worker_returned`: sent by Master A to Master B; includes `worker_id`.

## Load, Saturation, and Hysteresis
- `capacity` and `release_threshold` defined in `master.py`.
- Saturation: `current_load > capacity` triggers `request_help`.
- Release: `current_load < release_threshold` triggers `command_release` + `notify_worker_returned`.

## Error Handling and Timeouts
- Unknown JSON fields are ignored; missing required fields cause controlled error logs.
- Worker timeouts for Master response: 5 seconds.
- Master timeouts for Master-to-Master response: 5 seconds; then tries next neighbor.

## Observability
- Log every Master-to-Master message with `request_id`, `type`, and timestamp.
- Log borrowed worker lifecycle: loaned, registered, tasks executed, returned.

## Required Backlog Coverage (PDF)
This design includes tasks 01, 02, and 03 from the PDF backlog by implementing:
- TCP infrastructure with newline-delimited JSON.
- Heartbeat request/response.
- Master-side parsing and response to HEARTBEAT.

## Testing Strategy
- Manual smoke tests via `run_demo.py` and separate processes.
- Protocol conformance checks with sample payloads.
- Timeout and reconnection behavior validated by killing/restarting processes.
