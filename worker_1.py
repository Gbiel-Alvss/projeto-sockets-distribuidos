import socket
import json
import time

from common import send_json, extract_messages
#send_json - envia a mensagem json pelo socket, extract_messages - separa as mensagens que recebemos,
SERVER_HOST = "10.62.206.43"
SERVER_PORT = 5000

WORKER_ID = "A1"
SERVER_UUID = "SERVER-A-UUID"


def receive_one_json(sock):
    buffer = ""
    while True:
        data = sock.recv(1024)
        if not data:
            return None

        buffer += data.decode("utf-8")
        messages, buffer = extract_messages(buffer)

        for message in messages:
            try:
                return json.loads(message)
            except json.JSONDecodeError:
                print("[ERRO] JSON inválido recebido:", message)


def main():
    worker = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    #AF_INET - IPV4 / SOCK_STREAM - TCP

    try:
        worker.connect((SERVER_HOST, SERVER_PORT))
        print(f"[WORKER {WORKER_ID}] Conectado ao servidor {SERVER_HOST}:{SERVER_PORT}")

        while True:

            heartbeat_payload = {
                "WORKER_ID": WORKER_ID,
                "SERVER_UUID": SERVER_UUID,
                "TASK": "HEARTBEAT"
            }

            print(f"[WORKER {WORKER_ID}] Enviando heartbeat...")
            send_json(worker, heartbeat_payload)

            response = receive_one_json(worker)

            if response:
                print("[RESPOSTA DO SERVIDOR]", response)

                if response.get("TASK") == "HEARTBEAT" and response.get("RESPONSE") == "ALIVE":
                    print(f"[WORKER {WORKER_ID}] Servidor está ativo.")
                else:
                    print(f"[WORKER {WORKER_ID}] Resposta inesperada.")
            else:
                print(f"[WORKER {WORKER_ID}] Nenhuma resposta recebida.")
                break

            time.sleep(5)

    except ConnectionRefusedError:
        print("[ERRO] Não foi possível conectar ao servidor.")

    except Exception as e:
        print(f"[ERRO] {e}")

    finally:
        worker.close()
        print(f"[WORKER {WORKER_ID}] Conexão encerrada.")

if __name__ == "__main__":
    main()