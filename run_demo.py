import subprocess
import sys
import time


def run_demo():
    master = subprocess.Popen([sys.executable, "master.py"])
    time.sleep(1)
    worker_scripts = ["worker_1.py", "worker-2.py", "worker_3.py"]
    workers = [subprocess.Popen([sys.executable, script]) for script in worker_scripts]
    time.sleep(2)
    load = subprocess.Popen([sys.executable, "loadgen.py"])
    load.wait()
    time.sleep(3)
    for w in workers:
        w.terminate()
    master.terminate()


if __name__ == "__main__":
    run_demo()
