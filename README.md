# CodexImageFix — Codex 生图修复工具

一键修复 Codex 桌面版「无法生图」「打不开」等常见问题。

## 下载

前往 [Releases 页面](../../releases) 下载最新版：

- **Windows**：`CodexImageFix-Windows.exe` → 下载后直接双击
- **Mac**：`CodexImageFix-macOS` → 下载后终端执行 `chmod +x CodexImageFix-macOS`（仅首次），之后直接运行

> Mac 首次打开如提示"无法验证开发者"：右键 → 打开，或「系统设置 → 隐私与安全性」→「仍要打开」

## 能修什么

1. Codex 打不开（远程连接卡死 / GPU 缓存损坏）
2. 生图报"未配置 OPENAI_API_KEY"
3. 生图 401（地址被指向 OpenAI 官方而非内网网关）
4. 生图开关缺失（config.toml 缺 http_headers）
5. AI 管家路由模式未开启（自动检测并开启）

## 修复后三步

1. 彻底重启 Codex（托盘退出，不是关窗口）
2. AI 管家里确认「路由模式」已启用
3. Codex 里【新开一个对话框】再使用

## 发新版

改代码 → 升 VERSION → `git tag v1.x && git push origin v1.x` → Actions 自动打包双平台并发布 Release
