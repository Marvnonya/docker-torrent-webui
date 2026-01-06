#!/bin/bash

# ================= Configuration =================
DEFAULT_IMAGE_NAME="Marvnonya/torrent-webui"
# ==========================================

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}   🚀 Torrent maker script release (stable version)${NC}"
echo -e "${GREEN}========================================${NC}"

# --- 1. Git Synchronisation (Local Priority Policy) ---
echo -e "\n${YELLOW}---------- [1/4] Git Synchronisation (Local First) ----------${NC}"

# 1.1 Submit local code
if [ -n "$(git status --porcelain)" ]; then
    echo "📝 Code changes detected, preparing to commit..."
    read -p "Please enter the version number (e.g. v1.3): " VERSION
    if [ -z "$VERSION" ]; then echo -e "${RED}❌ The version number cannot be left blank.${NC}"; exit 1; fi
    
    read -p "Please enter the update notes: " MSG
    if [ -z "$MSG" ]; then MSG="Update to $VERSION"; fi

    git add .
    git commit -m "$MSG"
    echo "✅ Submitted locally"
else
    echo "⚠️  No local changes"
    if [ -z "$VERSION" ]; then read -p "Please enter the build version number (e.g. v1.3): " VERSION; fi
fi

# 1.2 Push to GitHub
echo "⬆️  Pushing code to GitHub..."
if git push origin main; then
    echo "✅ GitHub push notification sent successfully"
else
    echo -e "\n${RED}⚠️  Push rejected (typically due to new code on the remote)${NC}"
    echo "1) Forced push (git push --force) -> Coverage may vary; local conditions prevail."
    echo "2) Pull merge (git pull --rebase) -> Retain remote code, merge to local"
    echo "3) Exit"
    read -p "Please select [1/2/3]: " choice
    case $choice in
        1) git push origin main --force ;;
        2) git pull --rebase origin main && git push origin main ;;
        *) exit 1 ;;
    esac
fi

# --- 2. Select repository ---
echo -e "\n${YELLOW}---------- [2/4] Select target repository ----------${NC}"
echo "1) Docker Hub (Default: $DEFAULT_IMAGE_NAME)"
echo "2) Alibaba Cloud / Tencent Cloud / Other"
read -p "Selection [1/2] (Press Enter by default 1): " reg_choice

if [ "$reg_choice" == "2" ]; then
    read -p "Enter the full image name (e.g., registry.cn-hangzhou.../xxx:tag prefix): " FULL_IMAGE_NAME
    REGISTRY_DOMAIN=$(echo "$FULL_IMAGE_NAME" | cut -d/ -f1)
else
    FULL_IMAGE_NAME=$DEFAULT_IMAGE_NAME
    REGISTRY_DOMAIN="index.docker.io"
fi

# --- 3. Build (Fixed infinite loop bug) ---
echo -e "\n${YELLOW}---------- [3/4] Build a Docker image ----------${NC}"

# Login verification
echo -e "🔑 Verify login status..."
if [ "$REGISTRY_DOMAIN" == "index.docker.io" ]; then
    docker login
else
    docker login $REGISTRY_DOMAIN
fi

while true; do
    echo "🔨 Version under construction: $VERSION ..."
    docker build --pull -t "$FULL_IMAGE_NAME:$VERSION" .
    
    # Core fix: Directly evaluate the build outcome; if successful, break out of the loop.
    if [ $? -eq 0 ]; then
        echo "✅ Building Success！"
        echo "🏷️  In progress Latest tag..."
        docker tag "$FULL_IMAGE_NAME:$VERSION" "$FULL_IMAGE_NAME:latest"
        break 
    else
        echo -e "${RED}❌ Build failed${NC}"
        read -p "🔄 Should we retry?? (y/n): " retry
        if [[ "$retry" != "y" ]]; then exit 1; fi
    fi
done

# --- 4. Dual Push (Version Number + Latest) ---
echo -e "\n${YELLOW}---------- [4/4] 推送镜像到仓库 ----------${NC}"

while true; do
    # Step 1: Deploy a specific version (e.g., v1.3)
    echo -e "🚀 [1/2] Pushing version tags: ${GREEN}$VERSION${NC} ..."
    docker push "$FULL_IMAGE_NAME:$VERSION"
    if [ $? -ne 0 ]; then
        read -p "❌ Version push failed. Retry? (y/n): " r
        if [[ "$r" == "y" ]]; then continue; else exit 1; fi
    fi

    # Step Two: Push Latest
    echo -e "🚀 [2/2] Currently being pushed ${GREEN}latest${NC} 标签..."
    docker push "$FULL_IMAGE_NAME:latest"
    if [ $? -ne 0 ]; then
        read -p "❌ Latest Push failed. Retry? (y/n): " r
        if [[ "$r" == "y" ]]; then continue; else exit 1; fi
    fi
    
    # All successful, exit loop
    break
done

echo -e "\n${GREEN}🎉 All done! The image has been released:${NC}"
echo -e "   1. $FULL_IMAGE_NAME:$VERSION"
echo -e "   2. $FULL_IMAGE_NAME:latest"
