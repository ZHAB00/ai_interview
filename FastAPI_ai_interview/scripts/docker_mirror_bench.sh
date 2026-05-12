#!/bin/bash
# 测速并选用最快的 Docker 镜像源

MIRRORS=(
  "https://docker.1ms.run"
  "https://docker.xuanyuan.me"
  "https://hub-mirror.c.163.com"
  "https://mirror.baidubce.com"
  "https://docker.m.daocloud.io"
  "https://registry.cn-hangzhou.aliyuncs.com"
)

TEST_IMAGE="library/alpine:latest"

echo "=== 测速中，请稍候... ==="
declare -A RESULTS

for mirror in "${MIRRORS[@]}"; do
  start=$(date +%s%N)
  curl -s -o /dev/null -w "%{http_code}" --connect-timeout 5 --max-time 10 "${mirror}/v2/" > /dev/null 2>&1
  ret=$?
  end=$(date +%s%N)
  elapsed=$(( (end - start) / 1000000 ))
  if [ $ret -eq 0 ]; then
    RESULTS["${mirror}"]=$elapsed
    echo "  ${mirror} -> ${elapsed}ms"
  else
    echo "  ${mirror} -> 超时/不可达"
  fi
done

echo ""
echo "=== 最快镜像 ==="

BEST=""
BEST_TIME=999999
for mirror in "${!RESULTS[@]}"; do
  if [ "${RESULTS[$mirror]}" -lt "$BEST_TIME" ]; then
    BEST=$mirror
    BEST_TIME=${RESULTS[$mirror]}
  fi
done

if [ -z "$BEST" ]; then
  echo "所有镜像均不可达，使用默认源"
  exit 1
fi

echo "选用: ${BEST} (${BEST_TIME}ms)"

sudo tee /etc/docker/daemon.json <<EOF
{
  "registry-mirrors": ["${BEST}"]
}
EOF

sudo systemctl restart docker
echo "Docker 已重启，镜像源已切换为 ${BEST}"
