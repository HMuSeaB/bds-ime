"""
BDS Skin Studio 内置轻量服务端模块
可作为后台守护线程嵌入输入法主进程中运行，提供可视化创作、热换肤与 API 支持。
"""

import os
import json
import base64
import shutil
import socket
import webbrowser
import threading
from pathlib import Path
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

from bds_ime.config import STUDIO_HTML_DIR, CURRENT_SKIN_FILE, SKIN_FLAG_FILE, APP_ROOT


class SkinStudioHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(STUDIO_HTML_DIR), **kwargs)

    def do_GET(self):
        if self.path == "/api/status":
            self._send_json({"status": "running", "root": str(APP_ROOT)})
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
            try:
                CURRENT_SKIN_FILE.parent.mkdir(parents=True, exist_ok=True)
                with open(CURRENT_SKIN_FILE, "w", encoding="utf-8") as f:
                    json.dump(payload, f, ensure_ascii=False, indent=2)

                # 写入热重载信号标记
                with open(SKIN_FLAG_FILE, "w", encoding="utf-8") as f:
                    f.write("reload")

                self._send_json({"status": "ok", "msg": "已应用皮肤，输入法引擎实时刷新！"})
            except Exception as e:
                self._send_json({"status": "error", "msg": str(e)})

        elif self.path == "/api/export_msime":
            try:
                skin_state = payload.get("state", {})
                toml_text = payload.get("toml", "")
                skin_id = skin_state.get("id", "bds_custom_theme")

                local_app_data = os.environ.get("LOCALAPPDATA")
                installed_path = ""
                if local_app_data:
                    sys_msime_skins = Path(local_app_data) / "metasequoiaime" / "skins" / skin_id
                    assets_dir = sys_msime_skins / "assets"
                    assets_dir.mkdir(parents=True, exist_ok=True)

                    with open(sys_msime_skins / "skin.toml", "w", encoding="utf-8") as f:
                        f.write(toml_text)

                    bg_b64 = skin_state.get("bgImage", "")
                    if bg_b64 and "," in bg_b64:
                        raw_bg = base64.b64decode(bg_b64.split(",", 1)[1])
                        with open(assets_dir / "background.png", "wb") as f:
                            f.write(raw_bg)

                    mascot_data = skin_state.get("mascot", {})
                    mascot_b64 = mascot_data.get("image", "")
                    if mascot_b64 and "," in mascot_b64:
                        raw_mascot = base64.b64decode(mascot_b64.split(",", 1)[1])
                        with open(assets_dir / "character.png", "wb") as f:
                            f.write(raw_mascot)

                    installed_path = str(sys_msime_skins)

                self._send_json({
                    "status": "ok",
                    "path": installed_path
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
        pass


def find_free_port(start_port=18888, max_attempts=10):
    for port in range(start_port, start_port + max_attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
    return start_port


class EmbeddedStudioServer:
    """嵌入式皮肤工坊服务端控制器"""
    def __init__(self, port: int = 18888):
        self.port = find_free_port(port)
        self.httpd = None
        self.thread = None

    def start_background(self):
        server_address = ("127.0.0.1", self.port)
        self.httpd = ThreadingHTTPServer(server_address, SkinStudioHandler)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def open_in_browser(self):
        url = f"http://127.0.0.1:{self.port}"
        try:
            webbrowser.open(url)
        except Exception:
            pass
        return url
