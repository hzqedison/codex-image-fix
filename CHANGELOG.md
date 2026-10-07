# Codex 一键修复工具 — 版本记录

## v1.5（2026-10-01）

新增 Mac 支持：脚本跨平台适配（平台检测，杀进程用 pkill、环境变量用 launchctl、GPU 缓存路径适配 Mac）。新增 `修复Codex.command` 入口，Mac 用户双击运行（需 python3）。

## v1.4（2026-10-01）

修复：生图工具（imagegen 技能的 image_gen.py）用 openai SDK 默认调 OpenAI 官方 `api.openai.com`，sub2api 的 key 打官方地址返回 401 invalid_api_key。之前靠暴喵路由模式劫持才通、太脆弱。新增修复项：设置系统环境变量 `OPENAI_BASE_URL = https://aihao.6fast.com/v1`，让生图工具直接调 sub2api。

## v1.3（2026-10-01）

修复：生图工具真正读的是**系统环境变量** `OPENAI_API_KEY`，而之前脚本只写 auth.json、没设环境变量，导致 config.toml 补好 key 后生图仍报"未配置 OPENAI_API_KEY"。现在 `fix_api_key` 同时写 auth.json 和设置用户级系统环境变量（用 PowerShell SetEnvironmentVariable）。

## v1.2（2026-10-01）

修复：config.toml 里 `experimental_bearer_token`（API key）这一行**完全缺失**时，之前脚本检测不到、无法补上，导致生图工具报"未配置 OPENAI_API_KEY"。现在检测到缺失会自动补上（插在 base_url 行后，用交互输入或自动读到的 key）。

## v1.1（2026-10-01）

修复两个问题：

1. **生图开关插入失败**：原来插入 `http_headers` 只认 `experimental_bearer_token` 一个锚点，别人电脑上 config.toml 结构不同（没这行）就插不进去。改为多锚点兜底（experimental_bearer_token → base_url → requires_openai_auth → wire_api → name → provider 段头）。
2. **key 读不到时无法自动填**：新增交互式输入——当读不到 API key 时，主动停下来让用户粘贴自己的 key，而不是只提示"请用 --key 指定"。

## v1.0（2026-10-01）

首次发布。

**修复能力（7 项）**：
1. 杀死 Codex 僵死进程
2. 清空 GPU 缓存（解决窗口打不开）
3. 远程连接切回本地（解决启动卡在离线远程环境）
4. 补充 OPENAI_API_KEY（解决生图报"未配置 key"）
5. 改回直连地址和真实密钥（解决地址被暴喵管家改错）
6. 补充生图开关 http_headers
7. 检测并开启 AI 管家「路由模式」

**特性**：
- 双击即用（单文件 exe，无需 Python）
- 每步改文件前自动备份（.fixbak- 后缀）
- 幂等，重复运行不会出错
- 支持 `--dry-run` 预览、`--key sk-xxx` 指定密钥、`--version` 查版本
- 跑完停住显示结果，不会一闪而过

**交付物**：
- `dist/CodexFix-v1.0.exe`（分发给同事的就是这个）
- `codex_fix.py`（源码）
- `修复Codex.bat`（备选入口，需本机有 Python）
