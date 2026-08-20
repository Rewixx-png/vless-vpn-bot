module.exports = {
  apps:[
    {
      name: "CheckerSVC",
      cwd: "/root/Projects/vless-vpn-bot",
      script: "/root/Projects/vless-vpn-bot/.venv/bin/python3",
      args: "utils/checker/service.py",
      interpreter: "none",
      instances: 1,
      autorestart: true,
      watch: false,
      out_file: "/root/Projects/vless-vpn-bot/logs/checker.out.log",
      error_file: "/root/Projects/vless-vpn-bot/logs/checker.err.log",
      log_date_format: "YYYY-MM-DD HH:mm:ss",
      max_memory_restart: "1G",
      kill_timeout: 5000,
      wait_ready: true,
      listen_timeout: 10000
    },
    {
      name: "VPN_Worker",
      cwd: "/root/Projects/vless-vpn-bot",
      script: "/root/Projects/vless-vpn-bot/.venv/bin/python3",
      args: "-m celery -A celery_app worker -n worker_high@%h -Q high_priority -c 1 --prefetch-multiplier=1",
      interpreter: "none",
      instances: 1,
      autorestart: true,
      watch: false,
      out_file: "/root/Projects/vless-vpn-bot/logs/worker_high.out.log",
      error_file: "/root/Projects/vless-vpn-bot/logs/worker_high.err.log",
      log_date_format: "YYYY-MM-DD HH:mm:ss",
      max_memory_restart: "500M",
      kill_timeout: 10000,
      wait_ready: true
    },
    {
      name: "VPN_Worker_Low",
      cwd: "/root/Projects/vless-vpn-bot",
      script: "/root/Projects/vless-vpn-bot/.venv/bin/python3",
      args: "-m celery -A celery_app worker -n worker_low@%h -Q low_priority -c 1 --prefetch-multiplier=1",
      interpreter: "none",
      instances: 1,
      autorestart: true,
      watch: false,
      out_file: "/root/Projects/vless-vpn-bot/logs/worker_low.out.log",
      error_file: "/root/Projects/vless-vpn-bot/logs/worker_low.err.log",
      log_date_format: "YYYY-MM-DD HH:mm:ss",
      max_memory_restart: "500M",
      kill_timeout: 10000,
      wait_ready: true
    },
    {
      name: "VPN_Beat",
      cwd: "/root/Projects/vless-vpn-bot",
      script: "/root/Projects/vless-vpn-bot/.venv/bin/python3",
      args: "-m celery -A celery_app beat",
      interpreter: "none",
      instances: 1,
      autorestart: true,
      watch: false,
      out_file: "/root/Projects/vless-vpn-bot/logs/beat.out.log",
      error_file: "/root/Projects/vless-vpn-bot/logs/beat.err.log",
      log_date_format: "YYYY-MM-DD HH:mm:ss",
      max_memory_restart: "256M",
      kill_timeout: 5000
    },
    {
      name: "VPN_Bot",
      cwd: "/root/Projects/vless-vpn-bot",
      script: "bot.py",
      interpreter: "/root/Projects/vless-vpn-bot/.venv/bin/python3",
      instances: 1,
      autorestart: true,
      watch: false,
      out_file: "/root/Projects/vless-vpn-bot/logs/bot.out.log",
      error_file: "/root/Projects/vless-vpn-bot/logs/bot.err.log",
      log_date_format: "YYYY-MM-DD HH:mm:ss",
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
