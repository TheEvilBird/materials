from datetime import datetime
from pathlib import Path
import requests
import shutil
import subprocess
import sys
import time
import yaml

SERVER = "https://edu.distcomp.org"
REGISTRY = "distsys/registry"
GRADER = "distsys/grader"
SCRIPT_DIR = Path(__file__).resolve().parent
MAX_SOLUTION_SIZE = 1048576


def get_current_assignment():
    cwd = Path.cwd()
    if not (cwd / "assignment.yaml").exists():
        print(f"Cannot find assignment.yaml in current directory.")
        sys.exit(1)
    with open(cwd / "assignment.yaml", 'r') as f:
        config = yaml.safe_load(f)
    return cwd.name, config


def get_token():
    if not (SCRIPT_DIR / ".token").exists():
        print("The .token file is not found, it seems that you are not registered.")
        sys.exit(1)
    return (SCRIPT_DIR / ".token").read_text().strip()


def register():
    if (SCRIPT_DIR / ".token").exists():
        print("The .token file exists, it seems that you are already registered.")
        sys.exit(1)

    reg_token = input("Enter registration token: ")
    name = input("Enter your name: ")
    r = requests.post(
        f"{SERVER}/api/apps/{REGISTRY}",
        headers={"Authorization": f"Bearer {reg_token}"},
        json={
            'name': name,
            'inputs': {'name': name}
        }
    )
    if r.status_code == 201:
        print("Sent request to server, waiting for result", end='', flush=True)
        resp = r.json()
        job_id = resp['id']
        while True:
            print('.', end='', flush=True)
            time.sleep(2)
            r = requests.get(
                f"{SERVER}/api/jobs/{job_id}",
                headers={"Authorization": f"Bearer {reg_token}"}
            )
            if r.ok:
                resp = r.json()
                job_state = resp['state']
                if job_state in {'DONE', 'FAILED'}:
                    print(f"\n\n{resp['result']['status'].strip()}")
                    if job_state == 'DONE':
                        token = resp['result']['token']
                        with open(SCRIPT_DIR / ".token", "w") as f:
                            f.write(token)
                        print("Your access token is saved in .token, do not delete this file.")
                    break
            else:
                print("\n\nFAILED: %d(%s) %s" % (r.status_code, r.reason, r.text))
    else:
        print("\nFAILED: %d(%s) %s" % (r.status_code, r.reason, r.text))


def test(options):
    _, config = get_current_assignment()
    subprocess.run(config['tests']['command'].split(' ') + options)


def test_full():
    _, config = get_current_assignment()
    tests_command = config['tests']['command'].split(' ')
    if 'full-options' in config['tests']:
        tests_command += config['tests']['full-options'].split(' ')
    subprocess.run(tests_command)


def submit(force=False):
    assignment, config = get_current_assignment()
    session = requests.Session()
    session.headers.update({"Authorization": f"Bearer {get_token()}"})

    submissions_dir = Path.cwd() / ".submissions"
    tmp_dir = submissions_dir / "tmp"
    if tmp_dir.exists():
        shutil.rmtree(tmp_dir)
    if submissions_dir.exists():
        for item in submissions_dir.iterdir():
            if item.is_dir():
                state = (item / "state").read_text()
                if state not in {'DONE', 'FAILED', 'CANCELLED'}:
                    print("Pending submissions exist, run watch command.")
                    sys.exit(1)
    tmp_dir.mkdir(parents=True)

    solution_dir = Path.cwd() / config['solution-dir']

    report_path = solution_dir / 'readme.md'
    if not report_path.exists() or report_path.stat().st_size == 0:
        print(f"WARNING: Solution report is not found in {solution_dir.name}/readme.md.\n"
              f"Make sure to submit it later, otherwise your solution will not be accepted.\n")

    solution_zip_path = tmp_dir / "solution.zip"
    try:
        shutil.make_archive(str(solution_zip_path).replace('.zip', ''), 'zip', str(solution_dir))
        print(f"Created archive with solution.")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")

    solution_zip_size = solution_zip_path.stat().st_size
    if solution_zip_size > MAX_SOLUTION_SIZE:
        print(f"Solution archive size exceeds maximum size of {MAX_SOLUTION_SIZE} bytes.")
        sys.exit(1)

    with open(solution_zip_path, 'rb') as solution_zip:
        r = session.post(
            f"{SERVER}/api/files/temp",
            files={'solution.zip': solution_zip}
        )
        if r.ok:
            solution_zip_uri = r.json()['uri']
        else:
            print("Failed to upload solution: %d(%s) %s" % (r.status_code, r.reason, r.text))

    r = session.post(
        f"{SERVER}/api/apps/{GRADER}",
        json={
            'name': assignment,
            'inputs': {
                'assignment': assignment,
                'solution': solution_zip_uri,
                'force': force
            }
        }
    )
    if r.status_code == 201:
        print("Submitted solution to the server.")
        resp = r.json()
        job_id = resp['id']
        with open(tmp_dir / "state", "w") as f:
            f.write(resp['state'])
        submission_time = datetime.fromtimestamp(int(resp['submitted']) / 1000)
        submission_id = submission_time.strftime("%Y-%m-%d_%H-%M-%S") + "_" + job_id
        shutil.move(tmp_dir, f".submissions/{submission_id}")
        watch()
    else:
        print("Failed to submit solution: %d(%s) %s" % (r.status_code, r.reason, r.text))


def watch():
    _, _ = get_current_assignment()
    session = requests.Session()
    session.headers.update({"Authorization": f"Bearer {get_token()}"})

    submissions_dir = Path.cwd() / ".submissions"
    if not submissions_dir.exists():
        return
    for item in submissions_dir.iterdir():
        if not item.is_dir():
            continue
        submission_id = item.name
        state = (item / "state").read_text()
        if state in {'DONE', 'FAILED', 'CANCELLED'}:
            continue
        print(f"Watching pending submission {submission_id}:")
        job_id = submission_id.split("_")[2]
        while True:
            r = session.get(f"{SERVER}/api/jobs/{job_id}")
            if r.ok:
                resp = r.json()
                state = resp['state']
                print(f"- {state}")
                if state in {'DONE', 'FAILED'}:
                    if state == 'DONE':
                        score = resp['result']['score']
                        with open(item / "score", "w") as f:
                            f.write(str(score))
                        print(f"Score: {score}")
                    r = session.get(f"{SERVER}{resp['result']['log']}")
                    r.raise_for_status()
                    with open(item / "log", "wb") as f:
                        f.write(r.content)
                    if state == 'FAILED':
                        lines = r.text.strip().split('\n')
                        if len(lines) > 0:
                            print(f"Reason: {lines[-1]}")
                    print(f'Log: {item / "log"}')
                with open(item / "state", 'w') as f:
                    f.write(state)
                if state in {'DONE', 'FAILED', 'CANCELLED'}:
                    break
            else:
                print("Failed: %d(%s) %s" % (r.status_code, r.reason, r.text))
            time.sleep(3)


def cancel(submission_id):
    _, _ = get_current_assignment()
    session = requests.Session()
    session.headers.update({"Authorization": f"Bearer {get_token()}"})

    job_id = submission_id.split("_")[2]
    r = session.post(f"{SERVER}/api/jobs/{job_id}/cancel")
    if r.ok:
        print("Canceled submission.")
    else:
        print("Failed: %d(%s) %s" % (r.status_code, r.reason, r.text))


if __name__ == "__main__":
    command = sys.argv[1]
    if command == 'register':
        register()
    elif command == 'test':
        if len(sys.argv) == 3 and sys.argv[2] == '--full':
            test_full()
        else:
            tests_options = sys.argv[2:] if len(sys.argv) >= 3 else []
            test(tests_options)
    elif command == 'submit':
        force = len(sys.argv) == 3 and sys.argv[2] == '--force'
        submit(force)
    elif command == 'watch':
        watch()
    elif command == 'cancel':
        if len(sys.argv) < 3:
            print("Specify submission id")
            sys.exit(1)
        cancel(sys.argv[2])
    else:
        print("Unknown command")
        sys.exit(1)
