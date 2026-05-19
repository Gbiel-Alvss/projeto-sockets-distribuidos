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
