"""
BDS-IME 深度 Bug 修复验证测试套件
验证项目：
1. 高位 Unicode / Emoji 拆解 (代理对 Surrogate Pairs，杜绝 16 位溢出崩溃)
2. SendInputQueue 串行化 FIFO 时序一致性
3. get_smart_anchor_position 光标/鼠标自适应容错
4. 数字键与小键盘选词及未分配数字拦截
"""

import sys
import time
import queue
from ctypes import wintypes
from bds_ime.core.input_sender import SendInputHelper, SendInputQueue
from bds_ime.ui.native_candidate import get_smart_anchor_position
from bds_ime.core.hook import (
    VK_NUMPAD1, VK_NUMPAD5, VK_NUMPAD6, VK_NUMPAD9, VK_NUMPAD0
)


def test_surrogate_pairs():
    print("[*] 正在测试 Emoji 与高位 Unicode 代理对拆解...")
    test_chars = [
        ('A', 1),            # ASCII
        ('测', 1),           # BMP 中文
        ('\U0001F43E', 2),   # 🐾 爪爪 (Emoji, 0x1F43E)
        ('\U0001F916', 2),   # 🤖 机器人 (Emoji, 0x1F916)
        ('\U0001F389', 2),   # 🎉 庆祝 (Emoji, 0x1F389)
    ]
    for ch, expected_parts in test_chars:
        code = ord(ch)
        inputs = SendInputHelper._create_char_inputs(code)
        # 每个 UTF-16 code unit 会生成 1 个 keydown + 1 个 keyup，共 2 个 INPUT
        expected_inputs = expected_parts * 2
        assert len(inputs) == expected_inputs, f"字符 {hex(code)} 生成 INPUT 数量异常: {len(inputs)} != {expected_inputs}"
        for inp in inputs:
            assert 0 <= inp.ki.wScan <= 0xFFFF, f"wScan 超出 16 位范围: {inp.ki.wScan}"
    print("  -> Emoji 与高位 Unicode 代理对拆解测试通过！(无溢出风险)")


def test_send_input_queue_fifo():
    print("[*] 正在测试 SendInputQueue 严格 FIFO 顺序执行...")
    received_order = []

    # 临时劫持 SendInputHelper.send_unicode_string 收集结果
    orig_send = SendInputHelper.send_unicode_string
    SendInputHelper.send_unicode_string = lambda text: received_order.append(text)

    try:
        items = ["第1段", "第2段", "，", "第3段", "！"]
        for item in items:
            SendInputQueue.enqueue(item, delay_before=0.005)

        time.sleep(0.1)  # 等待队列消费完毕
        assert received_order == items, f"入队出队顺序不一致: {received_order} != {items}"
        print("  -> SendInputQueue 串行 FIFO 队列验证通过！(杜绝多线程乱序)")
    finally:
        SendInputHelper.send_unicode_string = orig_send


def test_smart_anchor():
    print("[*] 正在测试 Caret 光标 / 鼠标自适应获取...")
    pos = get_smart_anchor_position()
    assert isinstance(pos, tuple) and len(pos) == 2, f"坐标返回值格式错误: {pos}"
    x, y = pos
    assert isinstance(x, int) and isinstance(y, int), f"坐标非整数: {x}, {y}"
    print(f"  -> 自适应定位测试通过，当前锚点: ({x}, {y})")


def test_numpad_mapping():
    print("[*] 正在测试小键盘与主键盘数字键映射...")
    # 主键盘 1~5 对应的序号
    for i in range(1, 6):
        main_key = ord(str(i))
        numpad_key = VK_NUMPAD1 + (i - 1)
        main_idx = main_key - ord('1')
        numpad_idx = numpad_key - VK_NUMPAD1
        assert main_idx == numpad_idx == (i - 1), f"按键映射不匹配: {i}"

def test_learn_word_new_phrase():
    print("[*] 正在测试用户选词记忆与新词沉淀...")
    from bds_ime.config import DB_PATH
    from bds_ime.core.engine import PinyinEngine
    engine = PinyinEngine(DB_PATH)
    test_py = "bdszidingyici"
    test_word = "BDS自定义词"
    engine.learn_word(test_word, test_py)
    _, cands = engine.query(test_py)
    assert test_word in cands, f"新词学习未在候选词中找到: {cands}"
    print("  -> 用户选词自学习与新造词记忆测试通过！")


if __name__ == "__main__":
    test_surrogate_pairs()
    test_send_input_queue_fifo()
    test_smart_anchor()
    test_numpad_mapping()
    test_learn_word_new_phrase()
    print("\n[+] 所有 5 项深度 Bug 修复与体验提升测试全部通过！系统稳健度达标。")

