"""
BDS Skin Studio 本地轻量化工作台服务端
提供可视化皮肤创作界面的 HTTP 服务与本地输入法热换肤、水杉皮肤导出 API。
"""

import os
import sys
import json
import base64
import shutil
import socket
import webbrowser
from pathlib import Path
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer


WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
STUDIO_HTML_DIR = WORKSPACE_ROOT / "tools" / "skin_studio"
CURRENT_SKIN_FILE = WORKSPACE_ROOT / "assets" / "current_skin.json"
MSIME_SKINS_DIR = WORKSPACE_ROOT / "msime_skins"


class SkinStudioHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(STUDIO_HTML_DIR), **kwargs)

    def do_GET(self):
        if self.path == "/api/status":
            self._send_json({"status": "running", "workspace": str(WORKSPACE_ROOT)})
            return
        elif self.path == "/api/current_skin":
            if CURRENT_SKIN_FILE.exists():
                try:
                    with open(CURRENT_SKIN_FILE, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    self._send_json({"status": "ok", "skin": data})
                    return
                except Exception as e:
                    self._send_json({"status": "error", "msg": str(e)})
                    return
            self._send_json({"status": "none"})
            return

        # 默认静态页面
        if self.path == "/" or self.path == "":
            self.path = "/index.html"
        return super().do_GET()

    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)

        try:
            payload = json.loads(body.decode("utf-8")) if body else {}
        except Exception:
            payload = {}

        if self.path == "/api/apply":
            # 一键应用皮肤到当前本地 BDS-IME
            try:
                CURRENT_SKIN_FILE.parent.mkdir(parents=True, exist_ok=True)
                with open(CURRENT_SKIN_FILE, "w", encoding="utf-8") as f:
                    json.dump(payload, f, ensure_ascii=False, indent=2)

                # 写入热重载信号标记
                flag_file = CURRENT_SKIN_FILE.parent / "skin_reload.flag"
                with open(flag_file, "w", encoding="utf-8") as f:
                    f.write(str(os.getpid()))

                print(f"[Studio] 成功应用皮肤「{payload.get('name', '未命名')}」到本地输入法！")
                self._send_json({"status": "ok", "msg": "已应用皮肤，输入法引擎将实时刷新！"})
            except Exception as e:
                self._send_json({"status": "error", "msg": str(e)})

        elif self.path == "/api/export_msime":
            # 导出水杉 skin.toml 与 assets
            try:
                skin_state = payload.get("state", {})
                toml_text = payload.get("toml", "")
                skin_id = skin_state.get("id", "bds_custom_theme")

                target_dir = MSIME_SKINS_DIR / skin_id
                assets_dir = target_dir / "assets"
                assets_dir.mkdir(parents=True, exist_ok=True)

                # 写入 skin.toml
                with open(target_dir / "skin.toml", "w", encoding="utf-8") as f:
                    f.write(toml_text)

                # 如果有 base64 背景图，保存为 background.png
                bg_b64 = skin_state.get("bgImage", "")
                if bg_b64 and "," in bg_b64:
                    raw_bg = base64.b64decode(bg_b64.split(",", 1)[1])
                    with open(assets_dir / "background.png", "wb") as f:
                        f.write(raw_bg)

                # 如果有 base64 立绘图，保存为 character.png
                mascot_data = skin_state.get("mascot", {})
                mascot_b64 = mascot_data.get("image", "")
                if mascot_b64 and "," in mascot_b64:
                    raw_mascot = base64.b64decode(mascot_b64.split(",", 1)[1])
                    with open(assets_dir / "character.png", "wb") as f:
                        f.write(raw_mascot)

                # 同步到系统水杉目录 %LOCALAPPDATA%\metasequoiaime\skins
                local_app_data = os.environ.get("LOCALAPPDATA")
                installed_path = ""
                if local_app_data:
                    sys_msime_skins = Path(local_app_data) / "metasequoiaime" / "skins" / skin_id
                    sys_msime_skins.mkdir(parents=True, exist_ok=True)
                    shutil.copytree(target_dir, sys_msime_skins, dirs_exist_ok=True)
                    installed_path = str(sys_msime_skins)

                print(f"[Studio] 成功导出水杉皮肤包: {target_dir}")
                self._send_json({
                    "status": "ok",
                    "local_dir": str(target_dir),
                    "path": installed_path or str(target_dir)
                })
            except Exception as e:
                self._send_json({"status": "error", "msg": str(e)})
        else:
            self._send_json({"status": "not_found"}, status=404)

    def _send_json(self, data, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))

    def log_message(self, format, *args):
        # 静默控制台高频请求，仅记录关键提示
        pass


def find_free_port(start_port=18888, max_attempts=10):
    for port in range(start_port, start_port + max_attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
    return start_port


def main():
    port = find_free_port(18888)
    server_address = ("127.0.0.1", port)
    httpd = ThreadingHTTPServer(server_address, SkinStudioHandler)

    url = f"http://127.0.0.1:{port}"
    print("=" * 60)
    print("🎨 BDS Skin Studio (皮肤创作工坊) 已成功启动！")
    print(f"🌐 本地访问地址: {url}")
    print("💡 在浏览器中自由调节背景、立绘、9-Patch 切片与 AI 联想")
    print("=" * 60)

    try:
        webbrowser.open(url)
    except Exception:
        pass

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[+] 皮肤创作工坊已安全退出。")
        httpd.server_close()


if __name__ == "__main__":
    main()
