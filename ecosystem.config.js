module.exports = {
  apps:[
    {
      name: "CheckerSVC",
      script: "utils/checker/service.py",
      interpreter: "python3",
      instances: 1,
      autorestart: true,
      watch: false,
      out_file: "/dev/null",
      error_file: "/dev/null"
    },
    {
      name: "VPN_Worker",
      script: "python3",
      args: "-m celery -A celery_app worker -Q high_priority,low_priority -c 8",
      interpreter: "none",
      instances: 1,
      autorestart: true,
      watch: false,
      out_file: "/dev/null",
      error_file: "/dev/null"
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
      error_file: "/dev/null"
    },
    {
      name: "VPN_Bot",
      script: "bot.py",
      interpreter: "python3",
      instances: 1,
      autorestart: true,
      watch: false,
      out_file: "/dev/null",
      error_file: "/dev/null"
    }
  ]
};