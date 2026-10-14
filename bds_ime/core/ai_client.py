"""
水杉同款大模型长句联想推测客户端 (兼容 OpenAI/DeepSeek/Ollama 规范)
非阻塞异步设计，超时保护。
"""

import json
import re
import threading
import urllib.request


class AICandidateHelper:
    def __init__(self, config_getter, debounce_sec: float = 0.22):
        self.config_getter = config_getter
        self.debounce_sec = debounce_sec
        self.current_req_id = 0
        self.debounce_timer = None
        self.lock = threading.Lock()

    def async_predict(self, pinyin_str: str, on_success_callback):
        cfg = self.config_getter() or {}
        ai_cfg = cfg.get("ai", {})
        if not ai_cfg.get("enabled", False):
            return

        base_url = ai_cfg.get("baseUrl", "https://api.deepseek.com/v1").rstrip("/")
        api_key = ai_cfg.get("apiKey", "")
        model = ai_cfg.get("model", "deepseek-chat")

        # 若无 key 且不是本地 ollama，直接跳过
        if not api_key and "127.0.0.1" not in base_url and "localhost" not in base_url:
            return

        with self.lock:
            self.current_req_id += 1
            req_id = self.current_req_id
            if self.debounce_timer:
                self.debounce_timer.cancel()

        def _do_request():
            try:
                url = f"{base_url}/chat/completions"
                payload = {
                    "model": model,
                    "messages": [
                        {
                            "role": "system",
                            "content": "你是一个输入法整句联想引擎。根据拼音输出最可能的一句自然中文（控制在2-10字内），严禁任何解释、前缀或标点。"
                        },
                        {"role": "user", "content": f"拼音: {pinyin_str}"}
                    ],
                    "temperature": 0.3,
                    "max_tokens": 24
                }
                headers = {
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {api_key}" if api_key else "Bearer ollama"
                }
                req = urllib.request.Request(
                    url,
                    data=json.dumps(payload).encode("utf-8"),
                    headers=headers,
                    method="POST"
                )
                with urllib.request.urlopen(req, timeout=1.6) as resp:
                    if resp.status == 200:
                        data = json.loads(resp.read().decode("utf-8"))
                        text = data["choices"][0]["message"]["content"].strip()
                        # 清洗前缀废话、引号与末尾标点
                        text = re.sub(r'^(好的|当然|为您联想|补全结果|提示|联想词|AI)[:：\s]*', '', text)
                        text = re.sub(r'[\r\n"\'`。！，？]+', '', text).strip()
                        with self.lock:
                            if req_id == self.current_req_id and text:
                                on_success_callback(text)
            except Exception:
                pass

        with self.lock:
            self.debounce_timer = threading.Timer(self.debounce_sec, _do_request)
            self.debounce_timer.daemon = True
            self.debounce_timer.start()
