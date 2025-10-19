import pathlib
import pytest

from collections import defaultdict

SCRIPT_DIR = pathlib.Path(__file__).parent.resolve()

TEST_GROUPS = {
    'BASIC': {
        'tests': [
            'test_empty_data_dir',
            'test_bad_request',
            'test_nonexistent_image',
            'test_task_queue',
            'test_single_image',
            'test_multiple_images',
            'test_captions_generated_on_workers'
        ],
        'points': 4
    },
    'CALLBACKS': {
        'tests': [
            'test_multiple_images_no_listdir'
        ],
        'points': 2
    },
    'FAULT_TOLERANCE_1': {
        'tests': [
            'test_heartbeats_timeout'
        ],
        'points': 1
    },
    'FAULT_TOLERANCE_2': {
        'tests': [
            'test_publisher_confirms'
        ],
        'points': 1
    },
    'FAULT_TOLERANCE_3': {
        'tests': [
            'test_faulty_worker',
            'test_two_faulty_workers',
        ],
        'points': 1
    },
    'FAULT_TOLERANCE_4': {
        'tests': [
            'test_faulty_worker_and_rabbit_restart',
            'test_total_eclipse_of_the_heart'
        ],
        'points': 1
    }
}

class PassedCounter:
    def __init__(self):
        self.test_to_group = {}
        for group_name, group in TEST_GROUPS.items():
            for test in group['tests']:
                self.test_to_group[test] = group_name
        self.passed_by_group = defaultdict(int)

    def pytest_report_teststatus(self, report, config):
        if report.when == 'call' and report.passed:
            test = report.nodeid.split('::')[1].split('[')[0]
            group_name = self.test_to_group[test]
            self.passed_by_group[group_name] += 1

counter = PassedCounter()

pytest.main(['-vs', '--tb=short', SCRIPT_DIR / 'test_server.py'], plugins=[counter])

score = 0
print()
for group_name, group in TEST_GROUPS.items():
    total = len(group['tests'])
    passed = counter.passed_by_group[group_name]
    print(f'Test group {group_name}: passed {passed} of {total} tests')
    if passed == total:
        score += group['points']

print(f"\nSCORE: {score}")