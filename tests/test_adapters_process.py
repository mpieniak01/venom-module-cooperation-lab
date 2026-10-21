from __future__ import annotations

import json
from pathlib import Path

import pytest

from venom_module_cooperation_lab.adapters.rwkv_process import (
    RwkvAdapter,
    RwkvConfig,
    RwkvError,
    RwkvParameters,
)
from venom_module_cooperation_lab.adapters.rwkv_tokenizer import (
    SafeRwkvTokenizer,
    chat_prompt,
)


@pytest.mark.parametrize(
    "values",
    [
        {"max_new_tokens": 0},
        {"max_new_tokens": 257},
        {"max_new_tokens": True},
        {"seed": -1},
        {"temperature": float("nan")},
        {"top_p": float("inf")},
        {"max_context_tokens": 2049},
        {"temperature": 2.1},
        {"top_p": -0.1},
    ],
)
def test_invalid_parameters(values):
    with pytest.raises(RwkvError, match="invalid_parameters"):
        RwkvParameters(**values)


def test_safe_tokenizer_and_longest_match(tmp_path):
    vocab = tmp_path / "vocab"
    vocab.write_text("1 b'a' 1\n2 b'b' 1\n3 b'ab' 2\n")
    tokenizer = SafeRwkvTokenizer(vocab)
    assert tokenizer.encode("aba") == [3, 1]
    assert tokenizer.decode([3, 1]) == "aba"
    with pytest.raises(ValueError, match="unencodable_text"):
        tokenizer.encode("c")


def test_vocab_cannot_execute_code(tmp_path):
    vocab = tmp_path / "vocab"
    vocab.write_text("1 __import__('os').getpid() 1\n")
    with pytest.raises(ValueError):
        SafeRwkvTokenizer(vocab)


def test_vocab_duplicate_and_wrong_length(tmp_path):
    vocab = tmp_path / "vocab"
    vocab.write_text("1 b'ab' 1\n")
    with pytest.raises(ValueError, match="invalid_vocabulary"):
        SafeRwkvTokenizer(vocab)
    vocab.write_text("1 b'a' 1\n1 b'b' 1\n")
    with pytest.raises(ValueError, match="duplicate"):
        SafeRwkvTokenizer(vocab)


def test_prompt_template():
    assert (
        chat_prompt(" hi\n\nthere ", " help\r\n\r\nme ")
        == "System: help\nme\n\nUser: hi\nthere\n\nAssistant:"
    )


class Process:
    pid = 10
    alive = True
    terminated = False
    killed = False
    unkillable = False

    def is_alive(self):
        return self.alive

    def terminate(self):
        self.terminated = True

    def kill(self):
        self.killed = True

    def join(self, timeout):
        if not self.unkillable and self.killed:
            self.alive = False


class Connection:
    def __init__(self, response):
        self.response = response
        self.closed = False
        self.sent = []

    def poll(self, timeout):
        return self.response is not None

    def recv_bytes(self, limit):
        return json.dumps(self.response).encode()

    def send_bytes(self, body):
        self.sent.append(body)

    def close(self):
        self.closed = True


def adapter(response=None):
    item = RwkvAdapter(RwkvConfig(Path("/missing"), Path("/missing")))
    item._state = "ready"
    item._process = Process()
    item._connection = Connection(response)
    return item


def test_no_load_on_constructor():
    item = RwkvAdapter(RwkvConfig(Path("/missing"), Path("/missing")))
    assert item.status() == {
        "state": "available",
        "busy": False,
        "quiescent": True,
        "cancel_requested": False,
    }
    assert item._process is None


def test_missing_or_unsupported_config():
    with pytest.raises(RwkvError, match="artifact_missing"):
        RwkvConfig(Path("/missing"), Path("/missing")).validate()
    with pytest.raises(RwkvError, match="unsupported_precision"):
        RwkvConfig(Path("/missing"), Path("/missing"), "cuda auto").validate()


def test_request_identity_and_effective_params():
    item = adapter({"request_id": 1, "text": "hello"})
    assert item.generate("A", "User: hello\n\nAssistant:")["text"] == "hello"
    command = json.loads(item._connection.sent[0])
    assert command["participant"] == "A"
    assert command["parameters"]["max_context_tokens"] == 2048
    assert item.status()["quiescent"]


def test_malformed_reply_forces_worker_exit():
    item = adapter({"request_id": 99})
    with pytest.raises(RwkvError, match="worker_protocol_error"):
        item.generate("B", "prompt")
    assert item._process.killed
    assert not item._process.is_alive()


def test_timeout_does_not_leave_worker_alive():
    item = adapter()
    with pytest.raises(RwkvError, match="generation_timeout"):
        item._request("state", {}, 0.001)
    assert item._process.terminated and item._process.killed
    assert item.status()["quiescent"]


def test_uncertain_quiescence_is_not_reported_as_safe():
    item = adapter()
    item._process.unkillable = True
    with pytest.raises(RwkvError, match="worker_not_quiescent"):
        item._terminate()
    assert not item.status()["quiescent"]


def test_cancel_is_sticky_and_blocks_next_turn():
    item = adapter()
    item._busy.set()
    item.cancel()
    assert item.status()["state"] == "cancelling"
    with pytest.raises(RwkvError, match="invalid_state"):
        item.generate("A", "prompt")


def test_concurrent_request_is_busy():
    item = adapter()
    with item._lock:
        with pytest.raises(RwkvError, match="runtime_busy"):
            item.state()


@pytest.mark.parametrize(
    "participant,prompt,deadline",
    [
        ("C", "text", 1),
        ("A", "", 1),
        ("A", "x" * 17000, 1),
        ("A", "text", float("nan")),
        ("A", "text", 361),
    ],
)
def test_bounded_request(participant, prompt, deadline):
    item = adapter()
    with pytest.raises(RwkvError):
        item.generate(participant, prompt, timeout_s=deadline)


def test_shutdown_joins_process_and_closes_connection():
    item = adapter()
    assert item.close()
    assert not item._process.is_alive()
    assert item._connection.closed
    assert item.status()["state"] == "closed"


def test_artifact_validation_hash_and_load(tmp_path, monkeypatch):
    import hashlib
    import types

    from venom_module_cooperation_lab.adapters import rwkv_process as module

    path = tmp_path / "model.pth"
    path.write_bytes(b"weights")
    runtime = tmp_path / "runtime" / "rwkv"
    runtime.mkdir(parents=True)
    (runtime / "model.py").write_bytes(b"model")
    (runtime / "rwkv_vocab_v20230424.txt").write_bytes(b"vocab")
    for name, body in [
        ("MODEL_SHA256", b"weights"),
        ("RUNTIME_SHA256", b"model"),
        ("TOKENIZER_SHA256", b"vocab"),
    ]:
        monkeypatch.setattr(module, name, hashlib.sha256(body).hexdigest())
    config = RwkvConfig(path, runtime.parent)
    config.validate()
    item = RwkvAdapter(config)
    parent = Connection({"state": "ready"})
    child = Connection(None)

    class Started(Process):
        def start(self):
            pass

    item._context = types.SimpleNamespace(
        Pipe=lambda: (parent, child), Process=lambda **kw: Started()
    )
    assert item.load()["state"] == "ready"
    assert child.closed
    with pytest.raises(RwkvError, match="invalid_state"):
        item.load()
    item.close()
    path.write_bytes(b"bad")
    with pytest.raises(RwkvError, match="artifact_hash_mismatch"):
        config.validate()


def test_load_failure_is_cleaned(monkeypatch):
    import types

    config = RwkvConfig(Path("/unused"), Path("/unused"))
    monkeypatch.setattr(RwkvConfig, "validate", lambda self: None)
    item = RwkvAdapter(config)

    class Started(Process):
        def start(self):
            pass

    item._context = types.SimpleNamespace(
        Pipe=lambda: (Connection({"error": "unsupported"}), Connection(None)),
        Process=lambda **kw: Started(),
    )
    with pytest.raises(RwkvError, match="unsupported"):
        item.load()
    assert not item._process.is_alive()


@pytest.mark.parametrize("response", [[], {"error": "out_of_memory"}])
def test_receive_bad_or_failed_response(response):
    item = adapter(response)
    with pytest.raises(RwkvError):
        item._receive(1)


def test_reset_and_closed_state_validation():
    item = adapter({"request_id": 1, "state": "reset"})
    assert item.reset("B")["state"] == "reset"
    with pytest.raises(RwkvError, match="invalid_input"):
        item.reset("C")
    item.close()
    assert item.status()["state"] == "closed"
