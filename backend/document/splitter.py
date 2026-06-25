"""
文档切分器 — chunk_document

将解析后的文本按语义切分为检索单元。
使用字符数切分（兼容中英文），保留段落结构。
"""
from __future__ import annotations

import re
from typing import List, Dict


def chunk_document(
    text: str,
    metadata: dict,
    chunk_size: int = 800,
    overlap: int = 120,
) -> List[Dict]:
    """将文档文本切分为 chunk 列表。

    切分策略：
        1. 先按双换行（段落）切分。
        2. 累积段落直到超过 chunk_size，输出当前 chunk。
        3. overlap 从上一个 chunk 尾部截取，与新段落拼接。
        4. ★ 修复 #5：单个段落超过 chunk_size 时，按句子递归切分。

    Args:
        text: 文档全文。
        metadata: 每个 chunk 附加的元数据（filename, course, doc_type 等）。
        chunk_size: 每个 chunk 的最大字符数。
        overlap: chunk 之间的重叠字符数。

    Returns:
        [{"content": str, "metadata": {..., "chunk_index": int}}, ...]
    """
    chunks: List[Dict] = []
    text = text.strip()
    if not text:
        return chunks

    paragraphs = re.split(r"\n{2,}", text)
    current_chunk = ""
    chunk_index = 0

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue

        # ── 情况 1：当前 chunk 加上新段落会超出限制 ──
        if len(current_chunk) + len(para) > chunk_size and current_chunk:
            chunks.append({
                "content": current_chunk.strip(),
                "metadata": {**metadata, "chunk_index": chunk_index},
            })
            chunk_index += 1

            # overlap 片段 + 新段落
            overlap_fragment = current_chunk[-overlap:] if overlap > 0 else ""
            combined = overlap_fragment + "\n\n" + para if overlap_fragment else para

            # ★ 修复 #5：如果 overlap+新段落 仍然过大，直接按超大段落切分
            if len(combined) > chunk_size:
                sub_chunks = _split_oversized_paragraph(combined, chunk_size, overlap)
                for sub in sub_chunks:
                    chunks.append({
                        "content": sub,
                        "metadata": {**metadata, "chunk_index": chunk_index},
                    })
                    chunk_index += 1
                current_chunk = ""
            else:
                current_chunk = combined

        # ── 情况 2：当前 chunk 为空，但单段落就超过了 chunk_size ──
        elif not current_chunk and len(para) > chunk_size:
            # ★ 修复 #5：递归切分超大段落（按句子或定长）
            sub_chunks = _split_oversized_paragraph(para, chunk_size, overlap)
            for sub in sub_chunks:
                chunks.append({
                    "content": sub,
                    "metadata": {**metadata, "chunk_index": chunk_index},
                })
                chunk_index += 1
            current_chunk = ""

        # ── 情况 3：正常追加 ──
        else:
            if current_chunk:
                current_chunk += "\n\n" + para
            else:
                current_chunk = para

    # 尾部剩余
    if current_chunk.strip():
        chunks.append({
            "content": current_chunk.strip(),
            "metadata": {**metadata, "chunk_index": chunk_index},
        })

    return chunks


def _split_oversized_paragraph(text: str, max_len: int, overlap: int) -> List[str]:
    """将超长段落切分为多个 ≤ max_len 的片段。

    策略：优先按句号/问号/感叹号切句，若句子本身超长则按定长切。
    """
    if len(text) <= max_len:
        return [text]

    # 1. 按句子切分（中英文句末标点）
    sentences = re.split(r"(?<=[。！？.!?])\s*", text)
    sentences = [s.strip() for s in sentences if s.strip()]

    # 2. 如果仅有一个超长句子（无标点），退化为定长切分
    if len(sentences) <= 1:
        return _split_by_fixed_length(text, max_len, overlap)

    # 3. 按句子累积
    result: List[str] = []
    buf = ""
    for sent in sentences:
        if len(buf) + len(sent) > max_len and buf:
            result.append(buf.strip())
            buf = buf[-overlap:] + sent if overlap > 0 else sent
        elif not buf and len(sent) > max_len:
            # 单句超长 → 定长切
            result.extend(_split_by_fixed_length(sent, max_len, overlap))
        else:
            buf = (buf + sent) if buf else sent

    if buf.strip():
        result.append(buf.strip())

    return result


def _split_by_fixed_length(text: str, max_len: int, overlap: int) -> List[str]:
    """定长切分（兜底策略）。"""
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + max_len, len(text))
        chunks.append(text[start:end])
        start = end - overlap if end < len(text) else len(text)
    return chunks
