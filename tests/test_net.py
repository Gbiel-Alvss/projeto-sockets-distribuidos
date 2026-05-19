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
