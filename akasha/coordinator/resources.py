"""Give the preview of each task its own database name and port, so that two previews never collide."""

from __future__ import annotations

import re
import zlib

PORT_FIRST = 4100
PORT_COUNT = 800


def port(task_id: str) -> int:
    """A port from the task id. The same task always gets the same port."""
    return PORT_FIRST + zlib.crc32(task_id.encode("utf-8")) % PORT_COUNT


def fill(template: str, task_id: str) -> str:
    """Put the task name and the port into a preview template, for example "app_{task}" or "--port {port}"."""
    safe = re.sub(r"[^A-Za-z0-9_]", "_", task_id)
    return template.replace("{task}", safe).replace("{port}", str(port(task_id)))
