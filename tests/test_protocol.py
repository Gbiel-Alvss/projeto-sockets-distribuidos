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
