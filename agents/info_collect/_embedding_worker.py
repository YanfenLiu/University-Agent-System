"""常驻子进程 embedding 计算（ONNX Runtime，无需 torch）。

两种模式:
    1) 常驻模式（无参数）: 从 stdin 逐行读 JSON，输出到 stdout
       stdin:  {"candidates": [...], "intent": "..."}
       stdout: [score1, score2, ...]

    2) 单次模式（向后兼容）: python _embedding_worker.py <input.json>
"""

import json
import os as _os
import sys

_os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
# 抑制 fastembed 的 loguru 日志，避免污染 stdout
_os.environ.setdefault("LOGURU_LEVEL", "WARNING")

import numpy as np
from fastembed import TextEmbedding

MODEL_NAME = "BAAI/bge-small-zh-v1.5"


def _compute(model: TextEmbedding, candidates: list[dict], intent: str) -> list[float]:
    texts = [
        (c.get("title") or "") + " " + (c.get("description") or "")[:200]
        for c in candidates
    ]
    intent_emb = list(model.query_embed([intent]))[0]
    doc_embs = list(model.embed(texts))

    scores = []
    for emb in doc_embs:
        sim = np.dot(intent_emb, emb) / (
            np.linalg.norm(intent_emb) * np.linalg.norm(emb) + 1e-9
        )
        scores.append(float(sim * 100))
    return scores


def _daemon():
    """常驻模式：模型只加载一次，循环处理 stdin 的每一行。"""
    model = TextEmbedding(model_name=MODEL_NAME)

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
            scores = _compute(model, data["candidates"], data["intent"])
        except Exception as e:
            # 错误信息写入 stderr 而非 stdout，避免污染 JSON 输出
            sys.stderr.write(f"embedding daemon error: {e}\n")
            sys.stderr.flush()
            scores = None

        json.dump(scores, sys.stdout)
        sys.stdout.write("\n")
        sys.stdout.flush()


if __name__ == "__main__":
    if len(sys.argv) > 1:
        # 单次模式：从文件读取，输出到 stdout
        with open(sys.argv[1], "r", encoding="utf-8") as f:
            data = json.load(f)
        model = TextEmbedding(model_name=MODEL_NAME)
        scores = _compute(model, data["candidates"], data["intent"])
        json.dump(scores, sys.stdout)
    else:
        _daemon()
