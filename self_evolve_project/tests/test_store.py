from self_evolve.store import JsonlStore


def test_jsonl_store(tmp_path) -> None:
    store = JsonlStore(tmp_path / "x.jsonl")
    store.append({"a": 1})
    store.append({"b": 2})

    rows = store.read_all()

    assert rows == [{"a": 1}, {"b": 2}]
