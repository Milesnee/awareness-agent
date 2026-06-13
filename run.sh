#!/bin/bash
# 小澄觉察助手启动脚本
cd "$(dirname "$0")" || exit 1
export WECHAT_TOKEN=wechatmp
export WECHAT_APPID=wxabfba369c09c049e
export WECHAT_SECRET=e8395985a2763c5562a684c06dc744a4
export WECHAT_AES_KEY=RejaB5C6Goa3LKxJVFIOtFOI5nGhrKvJOCDhD4Kk10L
export LLM_CHAIN=glm
export GLM_API_KEY=9e025d42a42c4f31b65feaff7a9a56f8.BsYcGRPqxz7GjRWu
export GLM_MODEL=glm-5.1
# unreachable defaults
export LLM_EFFORT=max

nohup python3 -m uvicorn server.app:app --host 127.0.0.1 --port 8080 --workers 1 >> server.log 2>&1 &
echo "Started PID: $!"
