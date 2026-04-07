import socket
import threading
import uuid
import json
import argparse

from common import send_json, extract_messages, BUFFER_SIZE

HOST = "0.0.0.0"
PORT = 5000

SERVER_UUID = "cd46f1b8-a974-4f11-acac-fe9e5b590700"


def build_parser():
    parser = argparse.ArgumentParser(description="Servidor master para heartbeat dos workers")
    parser.add_argument("--host", default=HOST, help="IP de bind do servidor")
    parser.add_argument("--port", type=int, default=PORT, help="Porta de bind do servidor")
    parser.add_argument("--uuid", default=SERVER_UUID, help="UUID logico do master")
    return parser


def process_message(conn, addr, payload, server_uuid):
    """
    Processa uma mensagem recebida do worker
    """
    print(f"[RECEBIDO DE {addr}] {payload}")

    task = payload.get("TASK")

    if task == "HEARTBEAT":
        response = {
            "SERVER_UUID": server_uuid,
            "TASK": "HEARTBEAT",
            "RESPONSE": "ALIVE"
        }
        send_json(conn, response)
        print(f"[RESPOSTA ENVIADA PARA {addr}] {response}")

    else:
        response = {
            "SERVER_UUID": server_uuid,
            "TASK": task if task else "UNKNOWN",
            "RESPONSE": "INVALID_TASK"
        }
        send_json(conn, response)
        print(f"[TAREFA INVÁLIDA PARA {addr}] {response}")


def handle_client(conn, addr, server_uuid):
    """
    Trata a conexão de um cliente em uma thread separada
    """
    print(f"[NOVA CONEXÃO] {addr}")
    buffer = ""

    try:
        while True:
            data = conn.recv(BUFFER_SIZE)

            if not data:
                print(f"[DESCONECTADO] {addr}")
                break

            buffer += data.decode("utf-8")

            messages, buffer = extract_messages(buffer)

            for message in messages:
                try:
                    payload = json.loads(message)
                    print("Mensagem recebida:")
                    print(json.dumps(payload, indent=4))
                    process_message(conn, addr, payload, server_uuid)
                except json.JSONDecodeError:
                    print(f"[ERRO] JSON inválido de {addr}: {message}")

    except ConnectionResetError:
        print(f"[ERRO] Conexão resetada por {addr}")

    except Exception as e:
        print(f"[ERRO] Falha com {addr}: {e}")

    finally:
        conn.close()


def main():
    args = build_parser().parse_args()

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind((args.host, args.port))
    server.listen()

    print(f"[SERVIDOR ATIVO] Escutando em {args.host}:{args.port}")
    print(f"[SERVER_UUID] {args.uuid}")

    while True:
        conn, addr = server.accept()

        client_thread = threading.Thread(
            target=handle_client,
            args=(conn, addr, args.uuid),
            daemon=True
        )
        client_thread.start()


if __name__ == "__main__":
    main()
