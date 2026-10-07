#!/bin/bash
# Codex 一键修复工具 — Mac 版入口
# 双击运行（若提示无权限，先在终端执行一次：chmod +x 修复Codex.command）
cd "$(dirname "$0")"

# 优先用系统 python3，找不到就提示
if command -v python3 >/dev/null 2>&1; then
    python3 codex_image_fix.py
else
    echo "未找到 python3，请先安装：在终端执行 xcode-select --install"
    echo "安装完成后重新双击本文件。"
    read -n 1 -s -r -p "按任意键关闭..."
fi
