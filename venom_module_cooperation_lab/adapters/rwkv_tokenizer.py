"""Pinned RWKV byte tokenizer without upstream eval or sys.path mutation."""

from __future__ import annotations

import ast
from pathlib import Path


class SafeRwkvTokenizer:
    def __init__(self, vocabulary: Path) -> None:
        self.by_id: dict[int, bytes] = {}
        self.tree: dict = {}
        for line in vocabulary.read_text(encoding="utf-8").splitlines():
            first, last = line.index(" "), line.rindex(" ")
            token = ast.literal_eval(line[first + 1 : last])
            if isinstance(token, str):
                token = token.encode("utf-8")
            index, length = int(line[:first]), int(line[last + 1 :])
            if not isinstance(token, bytes) or len(token) != length or not token:
                raise ValueError("invalid_vocabulary")
            if index in self.by_id:
                raise ValueError("duplicate_vocabulary_id")
            self.by_id[index] = token
            node = self.tree
            for byte in token:
                node = node.setdefault(byte, {})
            node[None] = index

    def encode(self, text: str) -> list[int]:
        source, start, result = text.encode("utf-8"), 0, []
        while start < len(source):
            node, end, match = self.tree, start, None
            while end < len(source) and source[end] in node:
                node = node[source[end]]
                end += 1
                if None in node:
                    match = (end, node[None])
            if match is None:
                raise ValueError("unencodable_text")
            start, index = match
            result.append(index)
        return result

    def decode(self, tokens: list[int]) -> str:
        return b"".join(self.by_id[token] for token in tokens).decode(
            "utf-8", errors="replace"
        )


def clean_message(text: str) -> str:
    """Normalize round separators exactly as the author's prompt guide requires."""
    return "\n".join(
        line for line in text.replace("\r\n", "\n").split("\n") if line
    ).strip()


def chat_prompt(user: str, system: str = "") -> str:
    prefix = f"System: {clean_message(system)}\n\n" if system.strip() else ""
    return f"{prefix}User: {clean_message(user)}\n\nAssistant:"
