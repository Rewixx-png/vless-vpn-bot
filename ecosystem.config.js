module.exports = {
  apps:[
    {
      name: "CheckerSVC",
      cwd: "/root/vless-vpn-bot",
      script: "/root/vless-vpn-bot/.venv/bin/python3",
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
      cwd: "/root/vless-vpn-bot",
      script: "/root/vless-vpn-bot/.venv/bin/python3",
      args: "-m celery -A celery_app worker -n worker_high@%h -Q high_priority -c 1 --prefetch-multiplier=1",
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
      name: "VPN_Worker_Low",
      cwd: "/root/vless-vpn-bot",
      script: "/root/vless-vpn-bot/.venv/bin/python3",
      args: "-m celery -A celery_app worker -n worker_low@%h -Q low_priority -c 1 --prefetch-multiplier=1",
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
      cwd: "/root/vless-vpn-bot",
      script: "/root/vless-vpn-bot/.venv/bin/python3",
      args: "-m celery -A celery_app beat",
      interpreter: "none",
      instances: 1,
      autorestart: true,
      watch: false,
      out_file: "/dev/null",
      error_file: "/dev/null",
      max_memory_restart: "256M",
      kill_timeout: 5000
    },
    {
      name: "VPN_Bot",
      cwd: "/root/vless-vpn-bot",
      script: "bot.py",
      interpreter: "/root/vless-vpn-bot/.venv/bin/python3",
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
    },
    {
      name: "RU_SSH_Proxy",
      cwd: "/root/vless-vpn-bot",
      script: "/usr/bin/ssh",
      args: "-N -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 -o ServerAliveCountMax=3 -o StrictHostKeyChecking=no -i /root/.ssh/ru_checker_tunnel -D 127.0.0.1:19080 user1@37.18.102.249",
      interpreter: "none",
      instances: 1,
      autorestart: true,
      watch: false,
      out_file: "/dev/null",
      error_file: "/dev/null",
      max_memory_restart: "64M",
      kill_timeout: 5000
    }
  ]
};
