"""Headless Chrome helper shared by the archive page step."""

from __future__ import annotations

import os
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service

from storage.config import PROJECT_ROOT

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/152.0.0.0 Safari/537.36"
)


def chromedriver_path() -> str | None:
    """Return an explicit chromedriver binary if one is configured."""
    env_path = os.getenv("CHROMEDRIVER_PATH", "").strip()
    if env_path:
        return env_path

    driver_dir = PROJECT_ROOT / "chromedriver"
    for name in ("chromedriver.exe", "chromedriver"):
        candidate = driver_dir / name
        if candidate.exists():
            return str(candidate)
    return None


def create_driver(timeout_seconds: int = 20) -> webdriver.Chrome:
    """Create one headless Chrome instance for a whole page batch."""
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--window-size=1920,1080")
    options.add_argument(f"--user-agent={USER_AGENT}")
    options.page_load_strategy = "eager"

    binary = chromedriver_path()
    if binary:
        service = Service(executable_path=binary)
        driver = webdriver.Chrome(options=options, service=service)
    else:
        driver = webdriver.Chrome(options=options)

    driver.set_page_load_timeout(timeout_seconds)
    return driver
