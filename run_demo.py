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
