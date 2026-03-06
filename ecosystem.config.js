module.exports = {
  apps:[
    {
      name: "CheckerSVC",
      script: "python3",
      args: "utils/checker/service.py",
      interpreter: "none",
      instances: 1,
      autorestart: true,
      watch: false,
      out_file: "/dev/null",
      error_file: "/dev/null",
      max_memory_restart: "200M",
      kill_timeout: 5000,
      wait_ready: true,
      listen_timeout: 10000
    },
    {
      name: "VPN_Worker",
      script: "python3",
      args: "-m celery -A celery_app worker -Q high_priority,low_priority -c 1 --prefetch-multiplier=1",
      interpreter: "none",
      instances: 1,
      autorestart: true,
      watch: false,
      out_file: "/dev/null",
      error_file: "/dev/null",
      max_memory_restart: "500M",
      kill_timeout: 10000,
      wait_ready: true
    },
    {
      name: "VPN_Beat",
      script: "python3",
      args: "-m celery -A celery_app beat",
      interpreter: "none",
      instances: 1,
      autorestart: true,
      watch: false,
      out_file: "/dev/null",
      error_file: "/dev/null",
      max_memory_restart: "100M",
      kill_timeout: 5000
    },
    {
      name: "VPN_Bot",
      script: "bot.py",
      interpreter: "python3",
      instances: 1,
      autorestart: true,
      watch: false,
      out_file: "/dev/null",
      error_file: "/dev/null",
      max_memory_restart: "512M",
      kill_timeout: 10000,
      wait_ready: true,
      listen_timeout: 10000,
      env: {
        PYTHONOPTIMIZE: "1",
        PYTHONDONTWRITEBYTECODE: "1"
      }
    }
  ]
};