#!/bin/bash

pm2 flush

pm2 start ecosystem.config.js

pm2 save

pm2 list