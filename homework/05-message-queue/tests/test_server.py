import sys
import docker
import pytest
import requests
import subprocess
import time
import uuid

from pathlib import Path
from loguru import logger


IMAGES_ENDPOINT = 'http://localhost:5000/api/v1.0/images'
TASK_QUEUE_ENDPOINT = 'http://guest:guest@localhost:15672/api/queues/%2F/task_queue'

logger.remove()
logger.add(sys.stderr, colorize=False, format="=== TEST ===| {time:YYYY-MM-DD HH:mm:ss.SSS} {level} {message}")


# Tests ===============================================================================================================

@pytest.mark.parametrize("services", [['rabbitmq', 'server']])
def test_empty_data_dir(docker_tester):
    logger.info(f"Sending GET {IMAGES_ENDPOINT}")
    try:
        response = requests.get(IMAGES_ENDPOINT, timeout=3)
    except Exception as e:
        logger.error(f"Request failed: {e}")
        pytest.fail(f"Failed to get images: {e}")
    logger.info(f"Got response: {response.status_code} {response.text.rstrip()}")
    assert response.status_code == 200
    assert 'image_ids' in response.json()
    assert len(response.json()['image_ids']) == 0


@pytest.mark.parametrize("services", [['rabbitmq', 'server']])
def test_bad_request(docker_tester):
    logger.info(f"Sending POST {IMAGES_ENDPOINT} {{}}")
    try:
        response = requests.post(IMAGES_ENDPOINT, json={}, timeout=3)
    except Exception as e:
        logger.error(f"Request failed: {e}")
        pytest.fail(f"Failed to post image: {e}")
    logger.info(f"Got response: {response.status_code} {response.text.rstrip()}")
    assert response.status_code == 400


@pytest.mark.parametrize("services", [['rabbitmq', 'server']])
def test_nonexistent_image(docker_tester):
    nonexistent_image_id = str(uuid.uuid4())
    logger.info(f"Sending GET {IMAGES_ENDPOINT}/{nonexistent_image_id}")
    try:
        response = requests.get(f'{IMAGES_ENDPOINT}/{nonexistent_image_id}', timeout=3)
    except Exception as e:
        logger.error(f"Request failed: {e}")
        pytest.fail(f"Failed to get images: {e}")
    logger.info(f"Got response: {response.status_code} {response.text.rstrip()}")
    assert response.status_code == 404


@pytest.mark.parametrize("services", [['rabbitmq', 'server']])
def test_task_queue(docker_tester):
    time.sleep(5)
    check_task_queue(0, 10)
    post_images(10)
    check_task_queue(10, 10)
    time.sleep(5)
    check_task_queue(10, 10)


@pytest.mark.parametrize("services", [['rabbitmq', 'server', 'worker']])
def test_single_image(docker_tester):
    pending_ids = post_images(1)
    wait_and_check_results(pending_ids, 10)
    for image_id in pending_ids:
        check_image_caption(image_id)


@pytest.mark.parametrize("services", [['rabbitmq', 'server', 'worker']])
def test_multiple_images(docker_tester):
    pending_ids = post_images(10)
    wait_and_check_results(pending_ids, 10)
    for image_id in pending_ids:
        check_image_caption(image_id)


@pytest.mark.parametrize("services", [['rabbitmq', 'server', 'worker']])
def test_captions_generated_on_workers(docker_tester):
    worker1 = docker_tester.containers.get("distsys-mq-worker-1")
    worker2 = docker_tester.containers.get("distsys-mq-worker-2")
    worker1.pause()
    worker2.pause()
    time.sleep(1)

    pending_ids = post_images(10)
    time.sleep(5)    

    wait_and_check_results(set(), 10)
    worker1.unpause()
    worker2.unpause()
    wait_and_check_results(pending_ids, 10)


@pytest.mark.parametrize("services", [['rabbitmq', 'server-fdv', 'worker']])
def test_multiple_images_no_listdir(docker_tester):
    pending_ids = post_images(10)
    wait_and_check_results(pending_ids, 10)


@pytest.mark.parametrize("services", [['rabbitmq', 'server', 'worker']])
def test_heartbeats_timeout(docker_tester):
    time.sleep(15)
    pending_ids = post_images(10)
    wait_and_check_results(pending_ids, 10)


@pytest.mark.parametrize("services", [['rabbitmq', 'server', 'worker']])
def test_publisher_confirms(docker_tester):
    rabbit = docker_tester.containers.get("distsys-mq-rabbitmq-1")
    rabbit.pause()
    pending_ids = post_images(10)
    time.sleep(5)
    rabbit.kill()
    time.sleep(1)
    rabbit.start()
    wait_and_check_results(pending_ids, 10)


@pytest.mark.parametrize("services", [['rabbitmq', 'server', 'worker']])
def test_faulty_worker(docker_tester):
    worker1 = docker_tester.containers.get("distsys-mq-worker-1")
    worker1.pause()
    pending_ids = post_images(10)
    time.sleep(5)
    worker1.kill()
    wait_and_check_results(pending_ids, 10)


@pytest.mark.parametrize("services", [['rabbitmq', 'server', 'worker']])
def test_two_faulty_workers(docker_tester):
    worker1 = docker_tester.containers.get("distsys-mq-worker-1")
    worker2 = docker_tester.containers.get("distsys-mq-worker-2")
    worker1.pause()
    worker2.pause()
    pending_ids = post_images(10)
    time.sleep(5)
    worker1.kill()
    worker2.kill()
    time.sleep(5)
    worker1.start()
    wait_and_check_results(pending_ids, 10)


@pytest.mark.parametrize("services", [['rabbitmq', 'server', 'worker']])
def test_faulty_worker_and_rabbit_restart(docker_tester):
    worker1 = docker_tester.containers.get("distsys-mq-worker-1")
    rabbit = docker_tester.containers.get("distsys-mq-rabbitmq-1")
    worker1.pause()
    pending_ids = post_images(10)
    time.sleep(5)
    rabbit.kill()
    worker1.kill()
    time.sleep(5)
    rabbit.start()
    wait_and_check_results(pending_ids, 10)


@pytest.mark.parametrize("services", [['rabbitmq', 'server', 'worker']])
def test_total_eclipse_of_the_heart(docker_tester):
    pending_ids = post_images(10)
    wait_and_check_results(pending_ids, 10)

    docker_tester.containers.get("distsys-mq-worker-1").kill()
    docker_tester.containers.get("distsys-mq-worker-2").kill()
    docker_tester.containers.get("distsys-mq-rabbitmq-1").kill()

    post_images(10)
    time.sleep(5)
    wait_and_check_results(pending_ids, 10)

    docker_tester.containers.get("distsys-mq-server-1").restart()
    # can your server pass this test if the next line is commented?
    docker_tester.containers.get("distsys-mq-rabbitmq-1").start()
    check_server_endpoint()
    post_images(10)
    time.sleep(5)
    wait_and_check_results(set(), 10)


# Utils ===============================================================================================================

@pytest.fixture
def docker_tester(services):
    print()
    run_docker_compose_up(services)
    check_server_endpoint()
    client = docker.from_env()
    yield client
    print()
    run_docker_compose_down()


def run_docker_compose_up(services):
    command = ["docker", "compose", "--ansi", "never", "up", "--force-recreate"]
    for service in services:
        command.append(service)
    subprocess.Popen(command, cwd=Path(__file__).parent.parent.absolute(), stdout=None, stderr=None)


def run_docker_compose_down():
    command = ["docker", "compose", "down", "--volumes"]
    subprocess.run(command, cwd=Path(__file__).parent.parent.absolute(), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def check_server_endpoint(max_attempts=10):
    attempt = 0
    while True:
        attempt += 1
        try:
            logger.info(f"Sending GET {IMAGES_ENDPOINT}")
            requests.get(f'{IMAGES_ENDPOINT}', timeout=3)
            logger.info(f"Attempt {attempt} succeeded: got response, server endpoint is ready")
            return
        except Exception as e:
            logger.error(f"Attempt {attempt} failed: {e}")
        if attempt == max_attempts:
            logger.error(f"Max attempts reached, give up")
            pytest.fail("Server endpoint is not ready")
        logger.info(f"Retry in 3 seconds...")
        time.sleep(3)


def post_images(num_requests):
    pending_ids = set()
    for i in range(num_requests):
        input_data = {"image_url": f"https://somehost.com/some-image-{i}.jpg"}
        logger.info(f"Sending POST {IMAGES_ENDPOINT} {input_data}")
        try:
            response = requests.post(IMAGES_ENDPOINT, json=input_data, timeout=3)
        except Exception as e:
            logger.error(f"Request failed: {e}")
            pytest.fail(f"Failed to post image: {e}")
        logger.info(f"Got response: {response.status_code} {response.text.rstrip()}")
        assert response.status_code == 200
        assert 'image_id' in response.json()
        image_id = response.json()['image_id']
        assert image_id not in pending_ids
        pending_ids.add(image_id)
    return pending_ids


def wait_and_check_results(pending_ids, max_attempts):
    expected_count = len(pending_ids)
    attempt = 0
    while True:
        attempt += 1
        try:
            logger.info(f"Sending GET {IMAGES_ENDPOINT}")
            response = requests.get(IMAGES_ENDPOINT, timeout=3)
            logger.info(f"Got response: {response.status_code} {response.text.rstrip()}")
            assert response.status_code == 200
            assert 'image_ids' in response.json()
            ready_ids = response.json()['image_ids']
            assert pending_ids.issuperset(ready_ids)
            count = len(ready_ids)
            if count == expected_count:
                logger.info(f"Attempt {attempt} succeeded: got {count} results as expected")
                return
            else:
                logger.info(f"Attempt {attempt} not succeeded: got {count} results, expect {expected_count}")
        except Exception as e:
            logger.error(f"Attempt {attempt} failed: {e}")
        if attempt == max_attempts:
            logger.error(f"Max attempts reached, give up")
            pytest.fail("Server didn't return expected results")
        logger.info(f"Retry in 3 seconds...")
        time.sleep(3)


def check_image_caption(image_id):
    logger.info(f"Sending GET {IMAGES_ENDPOINT}/{image_id}")
    try:
        response = requests.get(f'{IMAGES_ENDPOINT}/{image_id}', timeout=3)
    except Exception as e:
        logger.error(f"Request failed: {e}")
        pytest.fail(f"Failed to get image caption: {e}")
    logger.info(f"Got response: {response.status_code} {response.text.rstrip()}")
    assert response.status_code == 200
    assert 'caption' in response.json()
    assert isinstance(response.json()['caption'], str)


def check_task_queue(expected_count, max_attempts):
    attempt = 0
    while True:
        attempt += 1
        try:
            logger.info(f"Sending GET {TASK_QUEUE_ENDPOINT}")
            response = requests.get(TASK_QUEUE_ENDPOINT, timeout=3)
            logger.info(f"Got response: {response.status_code} {response.text.rstrip()}")
            assert response.status_code == 200
            assert 'messages_ready' in response.json()
            count = response.json()['messages_ready']
            if count == expected_count:
                logger.info(f"Attempt {attempt} succeeded: got {count} ready messages as expected")
                return
            else:
                logger.info(f"Attempt {attempt} not succeeded: got {count} ready messages, expect {expected_count}")
        except Exception as e:
            logger.error(f"Attempt {attempt} failed: {e}")
        if attempt == max_attempts:
            logger.error(f"Max attempts reached, give up")
            pytest.fail("Message broker didn't return expected number of ready messages")
        logger.info(f"Retry in 3 seconds...")
        time.sleep(3)
