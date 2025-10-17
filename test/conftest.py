from datetime import datetime
import logging
import os
import pytest

from logger import JsonLineFormatter, setup_logger


@pytest.fixture(scope="session", autouse=True)
def configure_logging(session_report_dir: str):
    """Configure logging once for all tests."""
    setup_logger(session_report_dir)


@pytest.fixture(scope="session", autouse=False)
def session_report_dir(request: pytest.FixtureRequest):
    report_dir = f"./test_report/{datetime.now().isoformat()}"
    report_abs = os.path.abspath(report_dir)
    os.makedirs(report_abs)
    if os.path.exists(f"./test_report/latest"):
        os.remove(f"./test_report/latest")
    os.symlink(report_abs, f"./test_report/latest", target_is_directory=True)
    return report_abs


@pytest.fixture(scope="module", autouse=False)
def module_report_dir(session_report_dir: str):
    report_dir = f"{session_report_dir}/{__name__}"
    os.makedirs(report_dir)
    return report_dir


@pytest.fixture(scope="function", autouse=False)
def test_report_dir(session_report_dir: str, request: pytest.FixtureRequest):
    report_dir = f"{session_report_dir}/{request.node.name}"
    os.makedirs(report_dir)
    return report_dir


@pytest.fixture(scope="function", autouse=True)
def switch_test_datalog(test_report_dir: str, request: pytest.FixtureRequest):
    logger = logging.getLogger("graphtefacts")
    for h in logger.handlers:
        if isinstance(h, logging.FileHandler):
            logger.removeHandler(h)
            h.close()

    file_path = f"{test_report_dir}/data.log.jsonl"
    fh = logging.FileHandler(file_path, mode="w")
    fh.setFormatter(JsonLineFormatter())
    fh.setLevel(logging.DEBUG)
    logger.addHandler(fh)
    return file_path
