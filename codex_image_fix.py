# -*- coding: utf-8 -*-
"""
Codex 生图修复工具

修复 Codex 桌面版的常见问题：
  1. 打不开（远程连接卡死 + GPU 缓存损坏）
  2. 生图失败（缺 OPENAI_API_KEY / 地址被改错 / 生图开关缺失）
  3. 路由模式未开启

用法：
  python codex_fix.py               # 自动检测并修复
  python codex_fix.py --key sk-xxx  # 指定 API key
  python codex_fix.py --dry-run     # 只检查不修改
"""
VERSION = "1.7"

import argparse
import glob
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime

# 确保 Windows cmd 下中文输出不乱码
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

CODEX_HOME = os.path.expanduser(r"~/.codex")

IS_MAC = sys.platform == "darwin"
IS_WIN = sys.platform == "win32"


def find_codex_pkg():
    """动态查找 Codex 桌面版的数据目录（含 GPU 缓存，Mac/Windows 路径不同）"""
    if IS_MAC:
        candidates = [
            os.path.expanduser("~/Library/Application Support/Codex"),
            os.path.expanduser("~/Library/Caches/Codex"),
            os.path.expanduser("~/Library/Application Support/OpenAI/Codex"),
        ]
        for p in candidates:
            if os.path.isdir(p):
                return p
        return candidates[0]
    # Windows：Store 应用包目录
    base = os.path.expanduser(r"~/AppData/Local/Packages")
    for d in glob.glob(os.path.join(base, "OpenAI.Codex_*")):
        p = os.path.join(d, "LocalCache", "Roaming", "Codex")
        if os.path.isdir(p):
            return p
    return os.path.expanduser(
        r"~/AppData/Local/Packages/OpenAI.Codex_2p2nqsd0c76g0/LocalCache/Roaming/Codex")

PKG = find_codex_pkg()

def backup(path):
    """改文件前备份"""
    if os.path.exists(path):
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        dst = f"{path}.fixbak-{ts}"
        shutil.copy2(path, dst)
        return dst
    return None

def report(title, status, detail=""):
    mark = {"ok": "✅", "skip": "⏭️", "fixed": "🔧", "warn": "⚠️"}.get(status, "❓")
    line = f"{mark} {title}"
    if detail:
        line += f"  — {detail}"
    print(line)

# ---------- 修复 1：杀死僵死进程 ----------
def fix_zombie_process(dry=False):
    if dry:
        return ("Codex 进程", "skip", "预览模式不操作进程")
    try:
        if IS_MAC:
            r = subprocess.run(["pkill", "-f", "ChatGPT"],
                               capture_output=True, text=True)
            # pkill 返回 0=杀到了，1=没找到进程
            if r.returncode == 0:
                return ("已终止 Codex 僵死进程", "fixed")
            return ("Codex 进程", "skip", "没有僵死进程")
        else:
            r = subprocess.run(["taskkill", "/F", "/IM", "ChatGPT.exe"],
                               capture_output=True, encoding="gbk", errors="replace")
            if r.returncode == 0:
                return ("已终止 Codex 僵死进程", "fixed")
            return ("Codex 进程", "skip", "没有僵死进程")
    except Exception as e:
        return ("终止进程", "warn", str(e))

# ---------- 修复 2：清空 GPU 缓存 ----------
def fix_gpu_cache(dry=False):
    dirs = ["GPUCache", "DawnWebGPUCache", "DawnGraphiteCache", "Code Cache", "Cache"]
    cleaned = []
    for d in dirs:
        p = os.path.join(PKG, d)
        if os.path.isdir(p):
            cleaned.append(d)
            if not dry:
                shutil.rmtree(p, ignore_errors=True)
    if cleaned:
        return ("清空 GPU 缓存", "fixed", "、".join(cleaned))
    return ("GPU 缓存", "skip", "无需清理")

# ---------- 修复 3：远程连接切回本地 ----------
def fix_remote_control(dry=False):
    p = os.path.join(CODEX_HOME, ".codex-global-state.json")
    if not os.path.exists(p):
        return ("远程连接配置", "skip", "文件不存在")
    try:
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
    except Exception as e:
        return ("远程连接配置", "warn", f"读取失败 {e}")

    changed = []
    # 3a. 选中的远程主机切回本地
    if d.get("selected-remote-host-id", "").startswith("remote-control:"):
        old = d["selected-remote-host-id"]
        d["selected-remote-host-id"] = "local"
        changed.append(f"选中主机 {old[-12:]} → local")

    # 3b. 删除远程环境的自动连接标记
    auto = d.get("remote-connection-auto-connect-by-host-id") or {}
    removed = [k for k in list(auto) if k.startswith("remote-control:")]
    for k in removed:
        del auto[k]
    if removed:
        d["remote-connection-auto-connect-by-host-id"] = auto
        changed.append(f"删除 {len(removed)} 个远程自动连接")

    if changed and not dry:
        backup(p)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=2)

    if changed:
        return ("远程连接切回本地", "fixed", "；".join(changed))
    return ("远程连接", "skip", "已指向本地")

# ---------- 修复 4：补 OPENAI_API_KEY ----------
def get_user_env(name):
    """读持久化环境变量（Mac 用 launchctl，Windows 用注册表）"""
    try:
        if IS_MAC:
            r = subprocess.run(["launchctl", "getenv", name],
                               capture_output=True, text=True, timeout=10)
            return (r.stdout or "").strip()
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             f"[Environment]::GetEnvironmentVariable('{name}','User')"],
            capture_output=True, encoding="gbk", errors="replace", timeout=10)
        return (r.stdout or "").strip()
    except Exception:
        return None


def set_user_env(name, value):
    """设置持久化环境变量（Mac 用 launchctl，Windows 用注册表）"""
    try:
        if IS_MAC:
            r = subprocess.run(["launchctl", "setenv", name, value],
                               capture_output=True, text=True, timeout=15)
            return r.returncode == 0
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             f"[Environment]::SetEnvironmentVariable('{name}', '{value}', 'User')"],
            capture_output=True, encoding="gbk", errors="replace", timeout=15)
        return r.returncode == 0
    except Exception:
        return False


def fix_api_key(dry=False, key=None):
    # 1. 读 auth.json
    p = os.path.join(CODEX_HOME, "auth.json")
    d = {}
    if os.path.exists(p):
        try:
            with open(p, encoding="utf-8") as f:
                d = json.load(f)
        except Exception:
            d = {}
    auth_ok = bool(d.get("OPENAI_API_KEY"))

    # 2. 读系统环境变量（生图工具真正读的是这个）
    env_val = get_user_env("OPENAI_API_KEY")
    env_ok = bool(env_val and env_val.startswith("sk-"))

    if auth_ok and env_ok:
        return ("OPENAI_API_KEY", "skip", "已配置")

    # 确定 key
    if not key:
        key = get_key()
    if not key:
        return ("OPENAI_API_KEY", "warn", "未找到可用的 key，请用 --key sk-xxx 指定")

    changed = []
    # 写 auth.json
    if not auth_ok and not dry:
        backup(p)
        d["OPENAI_API_KEY"] = key
        with open(p, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=2)
        changed.append("auth.json")
    elif not auth_ok:
        changed.append("auth.json(待写)")

    # 设系统环境变量（生图工具读这个，需重启 Codex 生效）
    if not env_ok and not dry:
        if set_user_env("OPENAI_API_KEY", key):
            changed.append("系统环境变量")
        else:
            changed.append("环境变量设置失败")
    elif not env_ok:
        changed.append("系统环境变量(待设)")

    if changed:
        return ("OPENAI_API_KEY", "fixed", "；".join(changed))
    return ("OPENAI_API_KEY", "skip", "已配置")


# ---------- 修复 4b：设置 OPENAI_BASE_URL 指向 sub2api ----------
def fix_base_url_env(dry=False):
    """生图工具用 openai SDK 默认调 api.openai.com，需设 OPENAI_BASE_URL 指向 sub2api"""
    target = "https://aihao.6fast.com/v1"
    val = get_user_env("OPENAI_BASE_URL")
    if val == target:
        return ("OPENAI_BASE_URL", "skip", "已指向 sub2api")
    if not dry:
        if set_user_env("OPENAI_BASE_URL", target):
            return ("OPENAI_BASE_URL", "fixed", f"已设为 {target}")
        return ("OPENAI_BASE_URL", "warn", "设置失败")
    return ("OPENAI_BASE_URL", "fixed", f"待设为 {target}")

def read_key_from_config():
    """从 config.toml 读 experimental_bearer_token"""
    p = os.path.join(CODEX_HOME, "config.toml")
    try:
        with open(p, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("experimental_bearer_token") and "sk-" in line:
                    m = line.split("=", 1)[1].strip().strip('"')
                    if m.startswith("sk-"):
                        return m
    except Exception:
        pass
    return None

# ---------- 修复 5：补 http_headers 生图开关 ----------
def fix_image_header(dry=False):
    p = os.path.join(CODEX_HOME, "config.toml")
    if not os.path.exists(p):
        return ("config.toml", "warn", "文件不存在")
    with open(p, encoding="utf-8") as f:
        content = f.read()

    if "x-openai-actor-authorization" in content:
        return ("生图开关 http_headers", "skip", "已存在")

    header_line = 'http_headers = { "x-openai-actor-authorization" = "local-image-extension" }\n'

    def try_insert(anchor_kws):
        """尝试在某个锚点行后插入，成功返回 True"""
        lines = content.splitlines(keepends=True)
        out = []
        inserted = False
        for line in lines:
            out.append(line)
            if not inserted and line.strip().startswith(anchor_kws):
                out.append(header_line)
                inserted = True
        return (inserted, "".join(out))

    # 锚点按优先级尝试：provider 段内的常见字段
    for kws in (
        ("experimental_bearer_token",),
        ("base_url",),
        ("requires_openai_auth",),
        ("wire_api",),
        ("name",),
    ):
        inserted, new_content = try_insert(kws)
        if inserted:
            break

    # 最后兜底：插到 [model_providers.custom] 段头后
    if not inserted:
        lines = content.splitlines(keepends=True)
        out = []
        for line in lines:
            out.append(line)
            if not inserted and line.strip().startswith("[model_providers") and "custom" in line:
                out.append(header_line)
                inserted = True
        new_content = "".join(out)

    if not inserted:
        return ("生图开关 http_headers", "warn", "config.toml 结构异常，无法自动插入")

    if not dry:
        backup(p)
        with open(p, "w", encoding="utf-8") as f:
            f.write(new_content)

    return ("生图开关 http_headers", "fixed", "已插入")

def get_key(prefer=None):
    """按优先级取 API key：参数 > 环境变量 > auth.json > config.toml"""
    if prefer and prefer.startswith("sk-"):
        return prefer
    if os.environ.get("OPENAI_API_KEY", "").startswith("sk-"):
        return os.environ["OPENAI_API_KEY"]
    ap = os.path.join(CODEX_HOME, "auth.json")
    try:
        with open(ap, encoding="utf-8") as f:
            k = json.load(f).get("OPENAI_API_KEY")
        if k and k.startswith("sk-"):
            return k
    except Exception:
        pass
    return read_key_from_config()

# ---------- 修复 6：改回直连地址和真实密钥 ----------
def fix_provider_endpoint(dry=False, key=None):
    p = os.path.join(CODEX_HOME, "config.toml")
    if not os.path.exists(p):
        return ("config.toml", "warn", "文件不存在")
    with open(p, encoding="utf-8") as f:
        content = f.read()

    changed = []
    new = content

    # 改 base_url（任何非 aihao 的都改回直连）
    import re
    m = re.search(r'base_url\s*=\s*"([^"]*)"', new)
    if m and "aihao.6fast.com" not in m.group(1):
        new = re.sub(r'base_url\s*=\s*"[^"]*"',
                     'base_url = "https://aihao.6fast.com"', new, count=1)
        changed.append(f"base_url {m.group(1)} → aihao.6fast.com")

    # 处理密钥：PROXY_MANAGED 占位 → 改真实 key；缺失 → 补上
    if 'experimental_bearer_token = "PROXY_MANAGED"' in new:
        k = get_key(key)
        if k:
            new = new.replace('experimental_bearer_token = "PROXY_MANAGED"',
                              f'experimental_bearer_token = "{k}"')
            changed.append("密钥 PROXY_MANAGED → 真实key")
        else:
            changed.append("密钥仍是 PROXY_MANAGED（未找到可用 key）")
    elif 'experimental_bearer_token' not in new:
        # 这一行完全缺失，补上（插在 base_url 行后）
        k = get_key(key)
        if k:
            lines = new.splitlines(keepends=True)
            out = []
            inserted = False
            for line in lines:
                out.append(line)
                if not inserted and line.strip().startswith("base_url"):
                    out.append(f'experimental_bearer_token = "{k}"\n')
                    inserted = True
            if inserted:
                new = "".join(out)
                changed.append("补上缺失的 experimental_bearer_token")
            else:
                changed.append("缺少 experimental_bearer_token（无法定位插入点）")
        else:
            changed.append("缺少 experimental_bearer_token（未找到可用 key）")

    if changed and not dry:
        backup(p)
        with open(p, "w", encoding="utf-8") as f:
            f.write(new)

    if changed:
        return ("直连地址与密钥", "fixed", "；".join(changed))
    return ("直连地址与密钥", "skip", "已正确")


# ---------- 修复 7：检测并开启 AI 管家的路由模式 ----------
def fix_route_mode(dry=False):
    """检测 AI 管家（暴喵管家）的路由模式，未开启则自动开启"""
    settings_path = os.path.expanduser("~/.ai-manager/config/settings.json")
    db_path = os.path.expanduser("~/.ai-manager/config/cc-switch.db")

    enable_local = None
    codex_enabled = None

    # 1. 全局开关 settings.json 的 enableLocalProxy
    try:
        with open(settings_path, encoding="utf-8") as f:
            enable_local = json.load(f).get("enableLocalProxy", False)
    except Exception:
        pass

    # 2. Codex 专属开关 proxy_config 表的 enabled
    try:
        db = sqlite3.connect(db_path)
        row = db.execute(
            "SELECT enabled FROM proxy_config WHERE app_type='codex'").fetchone()
        codex_enabled = bool(row[0]) if row else None
        db.close()
    except Exception:
        pass

    # 已全部开启
    if enable_local and codex_enabled:
        return ("AI管家路由模式", "skip", "已启用")

    changed = []
    # 3. 自动开启
    if not dry:
        # 3a. 改 settings.json
        if not enable_local:
            try:
                with open(settings_path, encoding="utf-8") as f:
                    s = json.load(f)
                s["enableLocalProxy"] = True
                backup(settings_path)
                with open(settings_path, "w", encoding="utf-8") as f:
                    json.dump(s, f, ensure_ascii=False, indent=2)
                changed.append("全局开关 enableLocalProxy → 开启")
            except Exception as e:
                changed.append(f"全局开关开启失败({e})")

        # 3b. 改 cc-switch.db
        if not codex_enabled:
            try:
                db = sqlite3.connect(db_path)
                db.execute("UPDATE proxy_config SET enabled=1 WHERE app_type='codex'")
                db.commit()
                db.close()
                changed.append("Codex 路由 enabled → 1")
            except Exception as e:
                changed.append(f"Codex 路由开启失败({e})")

    if changed:
        detail = "；".join(changed) + "（需重启 AI 管家生效）"
        return ("AI管家路由模式", "fixed", detail)
    # 检测到未开启但 dry-run
    return ("AI管家路由模式", "warn", "未开启，需在 AI 管家界面开启「路由模式」")


# ---------- 主流程 ----------
def check_ai_manager_running():
    """检查暴喵AI管家是否在运行（路由转发依赖它，必须先开）"""
    try:
        if IS_MAC:
            r = subprocess.run(["pgrep", "-f", "ai-manager"],
                               capture_output=True, text=True, timeout=10)
            return r.returncode == 0
        r = subprocess.run(["tasklist", "/FI", "IMAGENAME eq ai-manager.exe"],
                           capture_output=True, encoding="gbk", errors="replace", timeout=10)
        return "ai-manager" in (r.stdout or "")
    except Exception:
        return None  # 检测不了，不拦用户


def main():
    ap = argparse.ArgumentParser(description="Codex 生图修复工具")
    ap.add_argument("--key", help="指定 API key（不传则自动从环境变量/auth.json/config.toml 读）")
    ap.add_argument("--dry-run", action="store_true", help="只检查不修改")
    ap.add_argument("--version", action="version", version=f"CodexImageFix v{VERSION}")
    args = ap.parse_args()

    print("=" * 50)
    print(f"Codex 生图修复工具 v{VERSION}")
    print("=" * 50)
    if args.dry_run:
        print("【预览模式】不会实际修改任何文件\n")

    # ★ 前置检查：暴喵AI管家 + 「需要路由」开关（修复生效的前提）
    if not args.dry_run:
        running = check_ai_manager_running()
        if running is False:
            print()
            print("❗ 检测不到暴喵AI管家在运行")
            print("   路由转发依赖管家，请先完成下面两步再回来：")
            print("   1. 打开暴喵AI管家")
            print("   2. 左侧「模型管理」→ 找到你的供应商（俊云AI-xxx）")
            print("      → 打开它旁边的「需要路由」开关")
            print()
            try:
                input("   都打开后，按回车继续（直接回车=忽略并继续）...")
            except (EOFError, KeyboardInterrupt):
                pass
            print()

    # 交互式获取 key（读不到时主动让用户输入，否则无法自动填 key）
    key = args.key
    if not args.dry_run and not key and not get_key():
        print()
        print("⚠️ 未检测到你的 API key")
        print("  （常见原因：用 ChatGPT 账号登录 + 代理托管，key 没明文存储）")
        print("  你的 key 可以在后台 /keys 页面查到，格式 sk- 开头")
        print()
        try:
            k = input("请输入你的 API key（粘贴后回车，直接回车则跳过）：").strip()
            if k.startswith("sk-"):
                key = k
                print(f"  已获取 key（尾号 {k[-6:]}）\n")
            else:
                print("  未输入有效 key，将跳过 key 相关修复（其他修复照常）\n")
        except (EOFError, KeyboardInterrupt):
            print("  无法交互输入，将跳过 key 相关修复\n")

    results = [
        fix_zombie_process(args.dry_run),
        fix_gpu_cache(args.dry_run),
        fix_remote_control(args.dry_run),
        fix_api_key(args.dry_run, key),
        fix_base_url_env(args.dry_run),
        fix_provider_endpoint(args.dry_run, key),
        fix_image_header(args.dry_run),
        fix_route_mode(args.dry_run),
    ]
    print()
    for r in results:
        report(*r)

    print()
    if args.dry_run:
        print("预览完成，去掉 --dry-run 参数即可真正执行。")
    else:
        print("=" * 50)
        print("修复完成！后续三步（缺一不可）：")
        print("  1. 暴喵AI管家 → 模型管理 → 你的供应商 →")
        print("     确认「需要路由」开关已打开（修复前就该开着）")
        print("  2. 彻底重启 Codex（托盘退出，不是关窗口）")
        print("  3. 在 Codex 里【新开一个对话框】再使用")
        print("=" * 50)
        print()
        print("┌─────────────────────────────────────┐")
        print(f"│  CodexImageFix  v{VERSION}")
        print("│  如仍有问题，截图上方修复结果")
        print("│  连同本版本号发给管理员")
        print("└─────────────────────────────────────┘")
        # 双击运行时停住，避免窗口一闪而过
        try:
            input("\n按回车键关闭...")
        except (EOFError, KeyboardInterrupt):
            pass

if __name__ == "__main__":
    main()
