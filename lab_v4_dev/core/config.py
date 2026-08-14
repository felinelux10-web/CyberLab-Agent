# CyberLab Agent v4.0
# core/config.py

HARD_LIMITS = {
    "max_ram_mb": 150,
    "max_cpu_percent": 40,
    "max_tasks_per_hour": 10,
    "max_file_edits_per_session": 5,
    "max_shell_commands_per_task": 20,
    "max_consecutive_failures": 3,
    "task_timeout_sec": 30,
    "idle_sleep_sec": 5,
    "log_max_size_mb": 50,
    "queue_max_age_sec": 300,
}

CRITICAL_THRESHOLDS = {
    "boot_failures_before_frozen": 3,
    "loop_instability_before_safe": 5,
    "archive_failures_before_warning": 3,
}

FROZEN_ZONES = [
    "stable/",
    "tests/",
    "run.py",
    "lab_v4_dev/configs/MASTER_REF.yaml",
]

PATHS = {
    "stable": "stable/v3.5",
    "lab": "lab_v4_dev",
    "logs": "lab_v4_dev/logs",
    "memory": "lab_v4_dev/memory",
    "archives": "lab_v4_dev/archives",
    "cache": "lab_v4_dev/cache",
    "configs": "lab_v4_dev/configs",
}

LOG_FILES = {
    "debug": "lab_v4_dev/logs/debug.log",
    "agent": "lab_v4_dev/logs/agent.log",
    "errors": "lab_v4_dev/logs/errors.log",
}

APPROVED_LIBRARIES = [
    "asyncio", "sqlite3", "subprocess",
    "hashlib", "pathlib", "logging",
    "psutil", "aiofiles", "pyyaml", "rich",
]

BANNED_LIBRARIES = [
    "langchain", "transformers", "chromadb",
    "pandas", "numpy", "fastapi", "flask",
]
