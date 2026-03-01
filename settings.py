COLLECTOR_SETTINGS = {
    "max_links_per_batch": 50000,
    "initial_workers": 25,
    "min_workers": 10,
    "max_workers": 100,
    "target_cpu": 85.0,
    "check_timeout": 8,
    "fetch_timeout": 10,
    "batch_size_fetch": 5,
}

CHECKER_SETTINGS = {
    "max_concurrent": 40,
    "timeout": 8,
    "connect_timeout": 3,
    "workers": 3,
}

WORKER_SETTINGS = {
    "concurrency": 8,
    "max_tasks_per_child": 50,
    "prefetch_multiplier": 2,
}

BEAT_SCHEDULE = {
    "collector_interval": 1800,
}
