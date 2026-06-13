#!/bin/bash
# 小澄觉察助手启动脚本
cd "$(dirname "$0")" || exit 1

# 优先加载.env文件（如果存在）
if [ -f .env ]; then
    set -a  # 自动导出所有变量
    source .env
    set +a
fi

# 硬编码备用默认值（如果.env中没有设置）
export WECHAT_TOKEN=${WECHAT_TOKEN:-wechatmp}
export WECHAT_APPID=${WECHAT_APPID:-wxabfba369c09c049e}
export WECHAT_SECRET=${WECHAT_SECRET:-e8395985a2763c5562a684c06dc744a4}
export WECHAT_AES_KEY=${WECHAT_AES_KEY:-RejaB5C6Goa3LKxJVFIOtFOI5nGhrKvJOCDhD4Kk10L}
export LLM_CHAIN=${LLM_CHAIN:-deepseek}
export DEEPSEEK_API_KEY=${DEEPSEEK_API_KEY:-}
export DEEPSEEK_MODEL=${DEEPSEEK_MODEL:-deepseek-chat}
export GLM_API_KEY=${GLM_API_KEY:-}
export GLM_MODEL=${GLM_MODEL:-glm-4-flash}
export LLM_EFFORT=${LLM_EFFORT:-max}

# 启动服务
nohup python3 -m uvicorn server.app:app --host 127.0.0.1 --port 8080 --workers 1 >> server.log 2>&1 &
echo "Started PID: $!"