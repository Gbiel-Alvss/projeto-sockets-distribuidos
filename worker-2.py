import os

os.environ.setdefault("WORKER_ID", "W-2")
os.environ.setdefault("MASTER_HOST", "127.0.0.1")
os.environ.setdefault("MASTER_PORT", "9000")

from worker import run_worker

if __name__ == "__main__":
    run_worker()
