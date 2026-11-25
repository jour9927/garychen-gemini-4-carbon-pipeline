from __future__ import annotations

import re

DIGITS_ZH = "零一二三四五六七八九"

ACRONYM_SPOKEN_MAP = [
    (r"\bn8n\b", "N eight N"),
    (r"\bCI/CD\b", "C I C D"),
    (r"\bCI\b", "C I"),
    (r"\bCD\b", "C D"),
    (r"\bPRs\b", "P R"),
    (r"\bPR\b", "P R"),
    (r"\bAPIs\b", "A P I"),
    (r"\bAPI\b", "A P I"),
    (r"\bMCP\b", "M C P"),
    (r"\bA2A\b", "A two A"),
    (r"\bRAG\b", "R A G"),
    (r"\bLLMs\b", "大型語言模型"),
    (r"\bLLM\b", "L L M"),
    (r"\bGPUs\b", "G P U"),
    (r"\bGPU\b", "G P U"),
    (r"\bCPU\b", "C P U"),
    (r"\bCLI\b", "指令列工具"),
    (r"\bSDK\b", "S D K"),
    (r"\bVPN\b", "V P N"),
    (r"\bSSH\b", "S S H"),
    (r"\bJSON\b", "Jason"),
    (r"\bYAML\b", "Yamo"),
    (r"\bSQL\b", "Sequel"),
    (r"\bURL\b", "網址"),
    (r"\bUI\b", "介面"),
    (r"\bNVDA\b", "Nvidia"),
    (r"\bNVIDIA\b", "Nvidia"),
    (r"\bMETA\b", "Meta"),
    (r"\bGOOGL\b", "Google"),
    (r"\bAMZN\b", "Amazon"),
    (r"\bMSFT\b", "Microsoft"),
    (r"\bTSMC\b", "台積電"),
    (r"\bAWS\b", "A W S"),
    (r"\bSaaS\b", "SaaS 軟體服務"),
    (r"\bEV/EBITDA\b", "企業價值倍數"),
    (r"\bEBITDA\b", "EBITDA"),
    (r"\bDCF\b", "D C F 現金流折現"),
    (r"\bForward\s*PE\b", "預估本益比"),
    (r"\bP/E\b", "本益比"),
    (r"\bPE\b", "本益比"),
    (r"\bEPS\b", "E P S 每股盈餘"),
    (r"\bCapEx\b", "資本支出"),
    (r"\bFCF\b", "自由現金流"),
    (r"\bOCF\b", "營運現金流"),
    (r"\bYoY\b", "年增"),
    (r"\bQoQ\b", "季增"),
    (r"\bNode\.js\b", "Node J S"),
    (r"\bNext\.js\b", "Next J S"),
    (r"\bVue\.js\b", "Vue J S"),
    (r"\bGitHub\b", "GitHub"),
]


def _int_to_zh(n: int) -> str:
    if n == 0:
        return "零"
    if n < 0:
        return "負" + _int_to_zh(-n)
    if n >= 100_000_000:
        yi, rem = divmod(n, 100_000_000)
        if rem == 0:
            return f"{_int_to_zh(yi)}億"
        if rem < 10_000_000:
            return f"{_int_to_zh(yi)}億零{_int_to_zh(rem)}"
        return f"{_int_to_zh(yi)}億{_int_to_zh(rem)}"
    if n >= 10_000:
        wan, rem = divmod(n, 10_000)
        # Round large clean star/metric counts > 20,000 when exact last digits sound awkward? Keep exact up to 9999, round >10000 if non-zero tail > 3 digits
        if rem == 0:
            return f"{_int_to_zh(wan)}萬"
        if wan >= 10 and rem % 1000 != 0:
            # Natural spoken approximation like Gary Chen ("二十一萬兩千" instead of "二十一萬一千九百九十五")
            approx_q = round(rem / 1000)
            if approx_q == 10:
                return f"{_int_to_zh(wan + 1)}萬"
            if approx_q > 0:
                q_word = "兩" if approx_q == 2 else DIGITS_ZH[approx_q]
                return f"{_int_to_zh(wan)}萬{q_word}千"
            return f"{_int_to_zh(wan)}萬"
        if rem < 1000:
            return f"{_int_to_zh(wan)}萬零{_int_to_zh(rem)}"
        return f"{_int_to_zh(wan)}萬{_int_to_zh(rem)}"
    if n >= 1000:
        q, rem = divmod(n, 1000)
        q_word = "兩" if q == 2 else DIGITS_ZH[q]
        if rem == 0:
            return f"{q_word}千"
        if rem < 100:
            return f"{q_word}千零{_int_to_zh(rem)}"
        return f"{q_word}千{_int_to_zh(rem)}"
    if n >= 100:
        b, rem = divmod(n, 100)
        b_word = "兩" if b == 2 else DIGITS_ZH[b]
        if rem == 0:
            return f"{b_word}百"
        if rem < 10:
            return f"{b_word}百零{DIGITS_ZH[rem]}"
        sh, ge = divmod(rem, 10)
        return f"{b_word}百{DIGITS_ZH[sh]}十" + (DIGITS_ZH[ge] if ge else "")
    if n >= 10:
        sh, ge = divmod(n, 10)
        prefix = "十" if sh == 1 else f"{DIGITS_ZH[sh]}十"
        return prefix + (DIGITS_ZH[ge] if ge else "")
    if n == 2:
        return "兩"
    return DIGITS_ZH[n]


def _num_str_to_zh(num_s: str) -> str:
    clean = num_s.replace(",", "").strip()
    if "." in clean:
        left, right = clean.split(".", 1)
        left_zh = _int_to_zh(int(left)) if left.isdigit() else left
        right_zh = "".join(DIGITS_ZH[int(ch)] for ch in right[:2] if ch.isdigit())
        return f"{left_zh}點{right_zh}" if right_zh else left_zh
    if clean.isdigit():
        val = int(clean)
        # Preserve 4-digit years 2015..2035 as year digits ("二零二六")
        if 2015 <= val <= 2035:
            return "".join(DIGITS_ZH[int(c)] for c in clean)
        return _int_to_zh(val)
    return num_s


def to_spoken_tts_text(display_text: str) -> str:
    """
    Transforms display subtitle text (containing $, %, commas, versions, CLI commands, and English acronyms)
    into smooth, 100% natural Taiwan Mandarin spoken text for PyTorch F5-TTS voice cloning!
    """
    s = str(display_text or "").strip()
    if not s:
        return ""

    # 1. Strip raw URLs or CLI pipelines so TTS never reads slashes/flags aloud
    s = re.sub(r"https?://\S+", "官方網站", s)
    s = re.sub(r"`[^`]+`", "這行指令", s)
    s = re.sub(r"\b(?:curl|pip|npm|npx|docker|git)\s+-[a-zA-Z]+\s+\S+.*", "終端機安裝指令", s)

    # 2. Arrows & ranges (e.g. $20-$200, 24%→30%)
    s = re.sub(
        r"\$(\d[\d,]*(?:\.\d+)?)\s*[-–~至到]\s*\$?(\d[\d,]*(?:\.\d+)?)",
        lambda m: f"{_num_str_to_zh(m.group(1))}到{_num_str_to_zh(m.group(2))}美金",
        s,
    )
    s = re.sub(
        r"(\d+(?:\.\d+)?)%\s*[→\->]+\s*(\d+(?:\.\d+)?)%",
        lambda m: f"百分之{_num_str_to_zh(m.group(1))}變到百分之{_num_str_to_zh(m.group(2))}",
        s,
    )

    # 3. Dollar amounts with Chinese units ($1,158 億 -> 一千一百五十八億美金, $0 -> 零元免費)
    s = re.sub(r"\$0(?:\b|/月)", "零元免費", s)
    s = re.sub(
        r"\$(\d[\d,]*(?:\.\d+)?)\s*(億|萬|兆)",
        lambda m: f"{_num_str_to_zh(m.group(1))}{m.group(2)}美金",
        s,
    )
    s = re.sub(
        r"\$(\d[\d,]*(?:\.\d+)?)\s*B\b",
        lambda m: f"{_num_str_to_zh(m.group(1))}十億美金",
        s,
    )
    s = re.sub(
        r"\$(\d[\d,]*(?:\.\d+)?)",
        lambda m: f"{_num_str_to_zh(m.group(1))}美金",
        s,
    )

    # 4. Percentages (+94%, -10%, 37.6%) — avoid double verb after 年增/上漲/下跌
    s = re.sub(r"(年增|季增|成長|上漲|增加|提升|飆升|高達)\s*\+", r"\1 ", s)
    s = re.sub(r"(年減|季減|下跌|下滑|減少|縮水)\s*-", r"\1 ", s)
    s = re.sub(
        r"\+(\d+(?:\.\d+)?)%",
        lambda m: f"成長百分之{_num_str_to_zh(m.group(1))}",
        s,
    )
    s = re.sub(
        r"-(\d+(?:\.\d+)?)%",
        lambda m: f"下滑百分之{_num_str_to_zh(m.group(1))}",
        s,
    )
    s = re.sub(
        r"(\d+(?:\.\d+)?)%",
        lambda m: f"百分之{_num_str_to_zh(m.group(1))}",
        s,
    )

    # 5. Multipliers (28x, 18x -> 二十八倍) & K/M star counts (212K -> 二十一萬)
    s = re.sub(
        r"\b(\d+(?:\.\d+)?)[xX]\b",
        lambda m: f"{_num_str_to_zh(m.group(1))}倍",
        s,
    )
    s = re.sub(
        r"\b(\d+(?:\.\d+)?)[kK]\+?\s*(?:Stars|stars|顆星)?",
        lambda m: _int_to_zh(int(float(m.group(1)) * 1000)),
        s,
    )

    # 6. Version numbers (v2.49.5 -> 二點四九版)
    s = re.sub(
        r"\bv?(\d+)\.(\d+)(?:\.\d+)?\b",
        lambda m: f"{_num_str_to_zh(m.group(1))}點{''.join(DIGITS_ZH[int(c)] for c in m.group(2))}版",
        s,
    )

    # 7. Acronyms & brand pronunciations (case-insensitive where safe, exact word boundaries)
    for pat, repl in ACRONYM_SPOKEN_MAP:
        s = re.sub(pat, f" {repl} ", s)

    # 8. Standalone numbers (211,995 -> 二十一萬兩千, 400 -> 四百)
    s = re.sub(
        r"\d[\d,]*(?:\.\d+)?",
        lambda m: _num_str_to_zh(m.group(0)),
        s,
    )

    # 9. Clean up symbols & extra spaces
    s = s.replace("★", "顆星").replace("/", "、").replace("｜", "，").replace("|", "，")
    s = re.sub(r"[#@*_~<>[\]{}()]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s
