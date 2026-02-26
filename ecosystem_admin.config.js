module.exports = [
  {
    name: 'Admin_API',
    script: '/root/vless-vpn-bot/start_admin_api.sh',
    cwd: '/root/vless-vpn-bot',
    interpreter: 'bash',
    instances: 1,
    autorestart: true,
    watch: false,
    max_memory_restart: '500M'
  }
]
