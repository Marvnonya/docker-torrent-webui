#!/bin/bash

# ================= 配置区 =================
DEFAULT_IMAGE_NAME="seaside111/torrent-webui"
# ==========================================

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}   🚀 种子工厂 发布脚本 (本地主导版)${NC}"
echo -e "${GREEN}========================================${NC}"

# --- 函数：错误处理 ---
function check_error() {
    if [ $? -ne 0 ]; then
        echo -e "${RED}❌ 上一步操作失败: $1${NC}"
        read -p "🔄 是否重试该步骤? (y/n): " retry
        if [[ "$retry" == "y" ]]; then return 1; else exit 1; fi
    fi
    return 0
}

# --- 1. Git 流程 (本地优先) ---
echo -e "\n${YELLOW}---------- [1/4] Git 同步 (Local First) ----------${NC}"

# 1.1 先处理本地提交
if [ -n "$(git status --porcelain)" ]; then
    echo "📝 检测到本地有代码修改，准备提交..."
    
    read -p "请输入版本号 (例如 v1.2): " VERSION
    if [ -z "$VERSION" ]; then echo -e "${RED}❌ 版本号不能为空${NC}"; exit 1; fi

    read -p "请输入更新说明 (Commit Message): " MSG
    if [ -z "$MSG" ]; then MSG="Update to $VERSION"; fi

    git add .
    git commit -m "$MSG"
    echo "✅ 本地代码已提交。"
else
    echo "⚠️  本地工作区干净，无新代码需要提交。"
    if [ -z "$VERSION" ]; then
        read -p "请输入构建用的版本号 (例如 v1.2): " VERSION
    fi
fi

# 1.2 尝试推送到远程
echo "⬆️  正在尝试推送到 GitHub (origin main)..."

if git push origin main; then
    echo "✅ GitHub 推送成功！"
else
    echo -e "\n${RED}⚠️  普通推送被拒绝！${NC}"
    echo "这通常意味着远程仓库(GitHub)包含你本地没有的提交。"
    echo "由于你的策略是【本地比远程新】，请选择处理方式："
    echo "------------------------------------------------"
    echo "  1) 强制推送 (git push --force)"
    echo "     👉 [危险] 这将用你的本地代码 完全覆盖 远程代码。"
    echo "     👉 适用于：你确定本地是最新的，远程的修改可以丢弃。"
    echo "  2) 拉取合并 (git pull --rebase)"
    echo "     👉 [安全] 尝试把远程的改动合并到你的本地。"
    echo "     👉 适用于：远程有别人提交的代码，你想保留它们。"
    echo "  3) 取消发布 (Exit)"
    echo "------------------------------------------------"
    
    read -p "请选择 [1/2/3]: " CONFLICT_CHOICE
    
    case $CONFLICT_CHOICE in
        1)
            echo "🔥 正在执行强制推送..."
            git push origin main --force
            if [ $? -eq 0 ]; then echo "✅ 强制推送成功！远程已与本地一致。"; else echo "❌ 强制推送失败。"; exit 1; fi
            ;;
        2)
            echo "⬇️  正在拉取并合并..."
            git pull --rebase origin main
            echo "⬆️  合并完成，再次尝试推送..."
            git push origin main
            if [ $? -eq 0 ]; then echo "✅ 推送成功！"; else echo "❌ 推送失败，请手动解决冲突。"; exit 1; fi
            ;;
        *)
            echo "🚫以此取消操作。"; exit 1 ;;
    esac
fi


# --- 2. 选择仓库 ---
echo -e "\n${YELLOW}---------- [2/4] 选择目标仓库 ----------${NC}"
echo "1) Docker Hub (默认: $DEFAULT_IMAGE_NAME)"
echo "2) 阿里云 (Registry)"
echo "3) GitHub Packages (ghcr.io)"
echo "4) 自定义"
read -p "请选择 [1-4] (回车默认 Docker Hub): " REGISTRY_CHOICE

case $REGISTRY_CHOICE in
    2) read -p "输入阿里云镜像地址: " FULL_IMAGE_NAME; REGISTRY_DOMAIN=$(echo "$FULL_IMAGE_NAME" | cut -d/ -f1) ;;
    3) read -p "输入 GitHub 用户名: " GH_USER; FULL_IMAGE_NAME="ghcr.io/$GH_USER/torrent-webui"; REGISTRY_DOMAIN="ghcr.io" ;;
    4) read -p "输入完整镜像名: " FULL_IMAGE_NAME; REGISTRY_DOMAIN=$(echo "$FULL_IMAGE_NAME" | cut -d/ -f1) ;;
    *) FULL_IMAGE_NAME=$DEFAULT_IMAGE_NAME; REGISTRY_DOMAIN="index.docker.io" ;;
esac
echo -e "🎯 目标: ${GREEN}$FULL_IMAGE_NAME${NC}"

# --- 3. 构建 ---
echo -e "\n${YELLOW}---------- [3/4] 构建 Docker 镜像 ----------${NC}"
# 登录检查
if ! docker login $REGISTRY_DOMAIN 2>&1 | grep -q "Login Succeeded"; then
    echo -e "${YELLOW}🔑 需要登录 $REGISTRY_DOMAIN ...${NC}"; 
    if [ "$REGISTRY_DOMAIN" == "index.docker.io" ]; then docker login; else docker login $REGISTRY_DOMAIN; fi
fi

while true; do
    echo "🔨 构建版本: $VERSION ..."
    docker build --pull -t "$FULL_IMAGE_NAME:$VERSION" .
    if check_error "Docker 构建"; then continue; fi
    
    echo "🏷️  标记 Latest ..."
    docker tag "$FULL_IMAGE_NAME:$VERSION" "$FULL_IMAGE_NAME:latest"
    break
done

# --- 4. 推送 ---
echo -e "\n${YELLOW}---------- [4/4] 推送镜像 ----------${NC}"
while true; do
    echo "🚀 推送版本 $VERSION ..."
    docker push "$FULL_IMAGE_NAME:$VERSION" || { echo "❌ 失败"; read -p "重试? (y/n): " r; if [[ $r == "y" ]]; then continue; else exit 1; fi; }
    
    echo "🚀 推送 Latest ..."
    docker push "$FULL_IMAGE_NAME:latest" || { echo "❌ Latest 失败"; read -p "重试? (y/n): " r; if [[ $r == "y" ]]; then continue; else exit 1; fi; }
    
    break
done

echo -e "\n${GREEN}🎉 发布完成！$FULL_IMAGE_NAME:$VERSION${NC}"