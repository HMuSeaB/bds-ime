"""
BDS-IME 拼音解析与词库查询内核
特性：
1. 贪心最长合法汉语拼音音节切分算法 (Syllable Segmentation)；
2. 多音节贪心词组长句自动拼接 (如 kuai'jie'jian'yong'bu'liao -> 快捷键 + 用不了)；
3. 用户选词动态调频自学习 (User Learning)。
"""

import sqlite3
from collections import OrderedDict
from pathlib import Path


VALID_SYLLABLES = frozenset([
    'a', 'ai', 'an', 'ang', 'ao', 'ba', 'bai', 'ban', 'bang', 'bao', 'bei', 'ben', 'beng', 'bi', 'bian', 'biao', 'bie', 'bin', 'bing', 'bo', 'bu',
    'ca', 'cai', 'can', 'cang', 'cao', 'ce', 'cen', 'ceng', 'cha', 'chai', 'chan', 'chang', 'chao', 'che', 'chen', 'cheng', 'chi', 'chong', 'chou', 'chu', 'chua', 'chuai', 'chuan', 'chuang', 'chui', 'chun', 'chuo', 'ci', 'cong', 'cou', 'cu', 'cuan', 'cui', 'cun', 'cuo',
    'da', 'dai', 'dan', 'dang', 'dao', 'de', 'dei', 'den', 'deng', 'di', 'dia', 'dian', 'diao', 'die', 'ding', 'diu', 'dong', 'dou', 'du', 'duan', 'dui', 'dun', 'duo',
    'e', 'ei', 'en', 'eng', 'er', 'fa', 'fan', 'fang', 'fei', 'fen', 'feng', 'fiao', 'fo', 'fou', 'fu',
    'ga', 'gai', 'gan', 'gang', 'gao', 'ge', 'gei', 'gen', 'geng', 'gong', 'gou', 'gu', 'gua', 'guai', 'guan', 'guang', 'gui', 'gun', 'guo',
    'ha', 'hai', 'han', 'hang', 'hao', 'he', 'hei', 'hen', 'heng', 'hong', 'hou', 'hu', 'hua', 'huai', 'huan', 'huang', 'hui', 'hun', 'huo',
    'ji', 'jia', 'jian', 'jiang', 'jiao', 'jie', 'jin', 'jing', 'jiong', 'jiu', 'ju', 'juan', 'jue', 'jun',
    'ka', 'kai', 'kan', 'kang', 'kao', 'ke', 'kei', 'ken', 'keng', 'kong', 'kou', 'ku', 'kua', 'kuai', 'kuan', 'kuang', 'kui', 'kun', 'kuo',
    'la', 'lai', 'lan', 'lang', 'lao', 'le', 'lei', 'leng', 'li', 'lia', 'lian', 'liang', 'liao', 'lie', 'lin', 'ling', 'liu', 'lo', 'long', 'lou', 'lu', 'luan', 'lue', 'lun', 'luo', 'lv',
    'ma', 'mai', 'man', 'mang', 'mao', 'me', 'mei', 'men', 'meng', 'mi', 'mian', 'miao', 'mie', 'min', 'ming', 'miu', 'mo', 'mou', 'mu',
    'na', 'nai', 'nan', 'nang', 'nao', 'ne', 'nei', 'nen', 'neng', 'ni', 'nian', 'niang', 'niao', 'nie', 'nin', 'ning', 'niu', 'nong', 'nou', 'nu', 'nuan', 'nue', 'nuo', 'nv',
    'o', 'ou', 'pa', 'pai', 'pan', 'pang', 'pao', 'pei', 'pen', 'peng', 'pi', 'pian', 'piao', 'pie', 'pin', 'ping', 'po', 'pou', 'pu',
    'qi', 'qia', 'qian', 'qiang', 'qiao', 'qie', 'qin', 'qing', 'qiong', 'qiu', 'qu', 'quan', 'que', 'qun',
    'ran', 'rang', 'rao', 're', 'ren', 'reng', 'ri', 'rong', 'rou', 'ru', 'ruan', 'rui', 'run', 'ruo',
    'sa', 'sai', 'san', 'sang', 'sao', 'se', 'sen', 'seng', 'sha', 'shai', 'shan', 'shang', 'shao', 'she', 'shei', 'shen', 'sheng', 'shi', 'shou', 'shu', 'shua', 'shuai', 'shuan', 'shuang', 'shui', 'shun', 'shuo', 'si', 'song', 'sou', 'su', 'suan', 'sui', 'sun', 'suo',
    'ta', 'tai', 'tan', 'tang', 'tao', 'te', 'teng', 'ti', 'tian', 'tiao', 'tie', 'ting', 'tong', 'tou', 'tu', 'tuan', 'tui', 'tun', 'tuo',
    'wa', 'wai', 'wan', 'wang', 'wei', 'wen', 'weng', 'wo', 'wu',
    'xi', 'xia', 'xian', 'xiang', 'xiao', 'xie', 'xin', 'xing', 'xiong', 'xiu', 'xu', 'xuan', 'xue', 'xun',
    'ya', 'yan', 'yang', 'yao', 'ye', 'yi', 'yin', 'ying', 'yo', 'yong', 'you', 'yu', 'yuan', 'yue', 'yun',
    'za', 'zai', 'zan', 'zang', 'zao', 'ze', 'zei', 'zen', 'zeng', 'zha', 'zhai', 'zhan', 'zhang', 'zhao', 'zhe', 'zhen', 'zheng', 'zhi', 'zhong', 'zhou', 'zhu', 'zhua', 'zhuai', 'zhuan', 'zhuang', 'zhui', 'zhun', 'zhuo', 'zi', 'zong', 'zou', 'zu', 'zuan', 'zui', 'zun', 'zuo'
])


class PinyinEngine:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        if not self.db_path.exists():
            raise FileNotFoundError(f"词库不存在: {db_path}")
        self.conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        # SQLite 性能飞升配置 (WAL + 缓存)
        try:
            self.conn.execute("PRAGMA journal_mode = WAL;")
            self.conn.execute("PRAGMA synchronous = NORMAL;")
            self.conn.execute("PRAGMA cache_size = 5000;")
        except Exception:
            pass
        self._cache = OrderedDict()
        self._cache_max = 512

    @classmethod
    def segment(cls, pinyin_str: str) -> list[str]:
        """贪心切分合法汉语拼音音节"""
        s = pinyin_str.lower()
        res = []
        i = 0
        n = len(s)
        while i < n:
            matched = None
            for length in range(min(6, n - i), 0, -1):
                chunk = s[i : i + length]
                if chunk in VALID_SYLLABLES:
                    matched = chunk
                    break
            if matched:
                res.append(matched)
                i += len(matched)
            else:
                res.append(s[i])
                i += 1
        return res

    def query(self, raw_input: str, limit: int = 60) -> tuple[str, list[str]]:
        """输入拼音字母串，输出分词显示与候选词列表 (支持长句贪心智能拼接与 LRU 极速缓存)"""
        raw = raw_input.lower().strip()
        if not raw:
            return "", []

        # 命中 LRU 缓存直接返回 (0.01ms 纳秒级跟手)
        if raw in self._cache:
            self._cache.move_to_end(raw)
            return self._cache[raw]

        syllables = self.segment(raw)
        pinyin_display = "'".join(syllables)
        compact_py = "".join(syllables)

        cur = self.conn.cursor()
        # 1. 优先完全精准匹配 (获取全量匹配词汇)
        cur.execute(
            "SELECT word FROM words WHERE pinyin = ? ORDER BY weight DESC LIMIT ?",
            (compact_py, limit)
        )
        candidates = [r[0] for r in cur.fetchall()]

        # 2. 如果包含多个音节，执行贪心最长词组拼接
        if len(syllables) > 1:
            assembled_chunks = []
            idx = 0
            n_syl = len(syllables)
            while idx < n_syl:
                matched_word = None
                for span in range(min(4, n_syl - idx), 0, -1):
                    chunk_py = "".join(syllables[idx : idx + span])
                    cur.execute(
                        "SELECT word FROM words WHERE pinyin = ? ORDER BY weight DESC LIMIT 1",
                        (chunk_py,)
                    )
                    row = cur.fetchone()
                    if row:
                        matched_word = row[0]
                        idx += span
                        break
                if matched_word:
                    assembled_chunks.append(matched_word)
                else:
                    assembled_chunks.append(syllables[idx])
                    idx += 1
            if assembled_chunks:
                full_phrase = "".join(assembled_chunks)
                if full_phrase not in candidates:
                    candidates.insert(0, full_phrase)

        # 3. 不足时前缀模糊联想补全
        if len(candidates) < limit:
            needed = limit - len(candidates)
            placeholders = ",".join(["?"] * len(candidates)) if candidates else "''"
            sql = f"""
                SELECT word FROM words 
                WHERE pinyin LIKE ? AND word NOT IN ({placeholders}) 
                ORDER BY weight DESC LIMIT ?
            """
            cur.execute(sql, [f"{compact_py}%"] + candidates + [needed])
            more = [r[0] for r in cur.fetchall()]
            candidates.extend(more)

        result = (pinyin_display, candidates)
        self._cache[raw] = result
        if len(self._cache) > self._cache_max:
            self._cache.popitem(last=False)
        return result

    def learn_word(self, word: str, pinyin: str):
        """用户选词调频自学习 (已有词自动提频 +50，新词/长句自动入库记忆)"""
        try:
            self._cache.clear()
            compact = pinyin.replace("'", "").strip()
            if not compact or not word:
                return
            cur = self.conn.cursor()
            cur.execute(
                "UPDATE words SET weight = weight + 50 WHERE word = ? AND pinyin = ?",
                (word, compact)
            )
            if cur.rowcount == 0:
                cur.execute(
                    "INSERT OR IGNORE INTO words (pinyin, word, weight) VALUES (?, ?, 100)",
                    (compact, word)
                )
            self.conn.commit()
        except Exception:
            pass

