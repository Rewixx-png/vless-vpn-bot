#!/bin/bash
ssh -o StrictHostKeyChecking=no user1@37.18.102.249 "/usr/bin/sudo systemctl restart xray && /usr/bin/sudo systemctl status xray --no-pager"
