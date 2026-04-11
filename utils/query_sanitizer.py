"""
Query Sanitizer for Lanfanshu (烂番薯学术) Search

烂番薯学术是 Google Scholar 国内镜像，其索引偏向标题和高频摘要词。
当查询包含过多关键词（隐式 AND 逻辑）时，极易返回 0 结果。

本模块提供查询预处理，解决：
1. 关键词过载 (Keyword Overload) — 截断到 5 个核心词
2. 化学离子符号不统一 — Fe3+ → Fe(III)
3. 特殊字符匹配失败 — 连字符、引号
4. 中文填充词冗余 — 综述/文献 等
"""

import re
import logging

logger = logging.getLogger("query_sanitizer")

# ── 化学离子符号标准化 ──────────────────────────────────
# 使用通用正则一次性替换，覆盖常见金属离子
_ION_CHARGE_MAP = {
    "1": "I", "2": "II", "3": "III", "4": "IV", "5": "V", "6": "VI",
}


def _normalize_ion_notation(text: str) -> str:
    """将 Fe3+、Cu2+ 等简写统一为 Fe(III)、Cu(II) 格式"""
    def _replace_ion(m):
        element = m.group(1)
        charge = m.group(2)
        roman = _ION_CHARGE_MAP.get(charge, charge)
        return f"{element}({roman})"

    # 匹配: 元素符号 + 数字 + 加号 (如 Fe3+, Cu2+, Hg2+, Al3+)
    return re.sub(r'\b([A-Z][a-z]?)(\d)\+', _replace_ion, text)


# ── 停用词（学术检索无信息量的词） ──────────────────────
_STOP_WORDS = frozenset({
    # 英文功能词
    "a", "an", "the", "and", "or", "but", "not", "nor",
    "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "having",
    "do", "does", "did",
    "will", "would", "could", "should", "shall", "can", "may", "might",
    "in", "on", "at", "to", "for", "of", "by", "from", "with",
    "as", "into", "through", "via", "using", "based",
    "its", "their", "this", "that", "these", "those",
    "both", "each", "every", "between", "after", "before",
    "over", "under", "about", "above", "below",
    "so", "yet", "no", "if", "then", "than", "when", "where", "how",
    # 学术常见低信息词
    "study", "studies", "investigation", "investigations",
    "novel", "new", "recent", "highly", "excellent",
    "effect", "effects", "role",
})

# ── 中文填充词 ──────────────────────────────────────────
_CHINESE_FILLERS = frozenset({
    "综述", "文献", "论文", "研究", "分析", "进展", "最新",
    "应用", "方法", "技术", "基于",
})

# ── 核心参数 ──────────────────────────────────────────
MAX_LANFANSHU_KEYWORDS = 5


def sanitize_lanfanshu_query(query: str) -> str:
    """
    对查询字符串进行预处理，优化烂番薯学术的检索命中率。

    处理逻辑：
    1. 标准化化学离子记法 (Fe3+ → Fe(III))
    2. 移除引号强制匹配
    3. 将连字符替换为空格
    4. 移除中文填充词（当查询含英文时）
    5. 去除英文停用词
    6. 去重并截断到 MAX_LANFANSHU_KEYWORDS 个核心词

    Args:
        query: 原始查询字符串

    Returns:
        清理后的查询字符串
    """
    if not query or not query.strip():
        return query

    original = query.strip()

    # 1. 标准化化学离子符号
    query = _normalize_ion_notation(query)

    # 2. 移除引号（避免强制精确匹配）
    query = query.replace('"', '').replace("'", '')

    # 3. 将字母间的连字符替换为空格 (B-substituted → B substituted)
    #    但保留数字-字母组合 (B(9,12)-vertex → B(9,12) vertex)
    query = re.sub(r'(?<=[a-zA-Z)>])-(?=[a-zA-Z])', ' ', query)

    # 4. 移除中文填充词（仅当查询包含英文关键词时）
    has_english = bool(re.search(r'[a-zA-Z]{3,}', query))
    if has_english:
        for filler in _CHINESE_FILLERS:
            query = query.replace(filler, '')

    # 5. 分词 → 去停用词 → 去重 → 截断
    tokens = query.split()

    # 去除停用词
    tokens = [t for t in tokens if t.lower() not in _STOP_WORDS and t.strip()]

    # 去重（保留首次出现顺序）
    seen = set()
    unique_tokens = []
    for t in tokens:
        t_lower = t.lower().strip()
        if t_lower and t_lower not in seen:
            seen.add(t_lower)
            unique_tokens.append(t.strip())

    # 截断到最大关键词数
    if len(unique_tokens) > MAX_LANFANSHU_KEYWORDS:
        unique_tokens = unique_tokens[:MAX_LANFANSHU_KEYWORDS]

    result = ' '.join(unique_tokens).strip()

    # 兜底：如果清理后为空，返回原始查询（截断到前 5 个词）
    if not result:
        fallback_tokens = original.split()[:MAX_LANFANSHU_KEYWORDS]
        result = ' '.join(fallback_tokens)

    # 日志
    if result != original:
        logger.info(
            "[QuerySanitize] lanfanshu 查询优化: '%s' → '%s'",
            original[:80],
            result[:80],
        )

    return result
