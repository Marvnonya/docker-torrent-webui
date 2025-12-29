#!/bin/bash

# ================= 配置区 =================
DEFAULT_IMAGE_NAME="seaside111/torrent-webui"
# ==========================================

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}   🚀 种子工厂 发布脚本 (稳定版)${NC}"
echo -e "${GREEN}========================================${NC}"

# --- 1. Git 同步 (本地优先策略) ---
echo -e "\n${YELLOW}---------- [1/4] Git 同步 (Local First) ----------${NC}"

# 1.1 提交本地代码
if [ -n "$(git status --porcelain)" ]; then
    echo "📝 检测到代码变更，准备提交..."
    read -p "请输入版本号 (例如 v1.3): " VERSION
    if [ -z "$VERSION" ]; then echo -e "${RED}❌ 版本号不能为空${NC}"; exit 1; fi
    
    read -p "请输入更新说明: " MSG
    if [ -z "$MSG" ]; then MSG="Update to $VERSION"; fi

    git add .
    git commit -m "$MSG"
    echo "✅ 本地已提交"
else
    echo "⚠️  无本地变更"
    if [ -z "$VERSION" ]; then read -p "请输入构建版本号 (例如 v1.3): " VERSION; fi
fi

# 1.2 推送到 GitHub
echo "⬆️  正在推送代码到 GitHub..."
if git push origin main; then
    echo "✅ GitHub 推送成功"
else
    echo -e "\n${RED}⚠️  推送被拒绝 (通常是因为远程有新代码)${NC}"
    echo "1) 强制推送 (git push --force) -> 覆盖远程，以本地为准"
    echo "2) 拉取合并 (git pull --rebase) -> 保留远程代码，合并到本地"
    echo "3) 退出"
    read -p "请选择 [1/2/3]: " choice
    case $choice in
        1) git push origin main --force ;;
        2) git pull --rebase origin main && git push origin main ;;
        *) exit 1 ;;
    esac
fi

# --- 2. 选择仓库 ---
echo -e "\n${YELLOW}---------- [2/4] 选择目标仓库 ----------${NC}"
echo "1) Docker Hub (默认: $DEFAULT_IMAGE_NAME)"
echo "2) 阿里云 / 腾讯云 / 其他"
read -p "选择 [1/2] (回车默认 1): " reg_choice

if [ "$reg_choice" == "2" ]; then
    read -p "输入完整镜像名 (如 registry.cn-hangzhou.../xxx:tag 前缀): " FULL_IMAGE_NAME
    REGISTRY_DOMAIN=$(echo "$FULL_IMAGE_NAME" | cut -d/ -f1)
else
    FULL_IMAGE_NAME=$DEFAULT_IMAGE_NAME
    REGISTRY_DOMAIN="index.docker.io"
fi

# --- 3. 构建 (修复了死循环 BUG) ---
echo -e "\n${YELLOW}---------- [3/4] 构建 Docker 镜像 ----------${NC}"

# 登录检测
echo -e "🔑 验证登录状态..."
if [ "$REGISTRY_DOMAIN" == "index.docker.io" ]; then
    docker login
else
    docker login $REGISTRY_DOMAIN
fi

while true; do
    echo "🔨 正在构建版本: $VERSION ..."
    docker build --pull -t "$FULL_IMAGE_NAME:$VERSION" .
    
    # 核心修复：直接判断构建结果，成功则 break 跳出循环
    if [ $? -eq 0 ]; then
        echo "✅ 构建成功！"
        echo "🏷️  正在打 Latest 标签..."
        docker tag "$FULL_IMAGE_NAME:$VERSION" "$FULL_IMAGE_NAME:latest"
        break 
    else
        echo -e "${RED}❌ 构建失败${NC}"
        read -p "🔄 是否重试? (y/n): " retry
        if [[ "$retry" != "y" ]]; then exit 1; fi
    fi
done

# --- 4. 双重推送 (版本号 + Latest) ---
echo -e "\n${YELLOW}---------- [4/4] 推送镜像到仓库 ----------${NC}"

while true; do
    # 第一步：推送具体版本 (如 v1.3)
    echo -e "🚀 [1/2] 正在推送版本标签: ${GREEN}$VERSION${NC} ..."
    docker push "$FULL_IMAGE_NAME:$VERSION"
    if [ $? -ne 0 ]; then
        read -p "❌ 版本推送失败，是否重试? (y/n): " r
        if [[ "$r" == "y" ]]; then continue; else exit 1; fi
    fi

    # 第二步：推送 Latest
    echo -e "🚀 [2/2] 正在推送 ${GREEN}latest${NC} 标签..."
    docker push "$FULL_IMAGE_NAME:latest"
    if [ $? -ne 0 ]; then
        read -p "❌ Latest 推送失败，是否重试? (y/n): " r
        if [[ "$r" == "y" ]]; then continue; else exit 1; fi
    fi
    
    # 全部成功，跳出循环
    break
done

echo -e "\n${GREEN}🎉 全部完成！镜像已发布：${NC}"
echo -e "   1. $FULL_IMAGE_NAME:$VERSION"
echo -e "   2. $FULL_IMAGE_NAME:latest"