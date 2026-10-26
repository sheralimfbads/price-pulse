import csv
import hashlib

import pytest

from scripts import replay_snapshot
from scripts.load_snapshot_history import SEMANTIC_HASH_VERSION


class FakeCursor:
    def __init__(self, registered_row):
        self.registered_row = registered_row
        self.query = None
        self.params = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, query, params=None):
        self.query = query
        self.params = params

    def fetchone(self):
        return self.registered_row


class FakeConnection:
    def __init__(self, registered_row):
        self.registered_row = registered_row

    def cursor(self):
        return FakeCursor(self.registered_row)


def make_snapshot_fixture(monkeypatch, tmp_path):
    filename = "official_prices_20261020T105154Z.json"
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    (raw_dir / filename).write_bytes(b"test snapshot bytes")

    raw_hash = "a" * 64
    semantic_hash = "b" * 64

    snapshot = {
        "raw_sha256": raw_hash,
        "semantic_sha256": semantic_hash,
        "products": {f"{i:04d}": {} for i in range(41)},
        "period_count": 69,
        "observation_count": 2829,
    }

    registered = (
        7,
        raw_hash,
        semantic_hash,
        SEMANTIC_HASH_VERSION,
        41,
        69,
        2829,
    )

    monkeypatch.setattr(replay_snapshot, "RAW_DIR", raw_dir)
    monkeypatch.setattr(
        replay_snapshot,
        "read_snapshot",
        lambda path: snapshot,
    )

    return filename, snapshot, registered, raw_dir


def write_csv(path, headers, rows):
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)


def test_sha256_file_matches_standard_hash(tmp_path):
    path = tmp_path / "example.txt"
    path.write_bytes(b"PricePulse deterministic replay")

    expected = hashlib.sha256(path.read_bytes()).hexdigest()

    assert replay_snapshot.sha256_file(path) == expected


def test_csv_row_count_and_lineage_pass(tmp_path):
    path = tmp_path / "prices.csv"
    write_csv(
        path,
        ["product_code", "source_snapshot"],
        [
            {
                "product_code": "0001",
                "source_snapshot": "snapshot.json",
            },
            {
                "product_code": "0002",
                "source_snapshot": "snapshot.json",
            },
        ],
    )

    assert replay_snapshot.csv_row_count(
        path,
        expected_snapshot="snapshot.json",
    ) == 2


def test_csv_row_count_rejects_wrong_lineage(tmp_path):
    path = tmp_path / "prices.csv"
    write_csv(
        path,
        ["product_code", "source_snapshot"],
        [{"product_code": "0001", "source_snapshot": "other.json"}],
    )

    with pytest.raises(ValueError, match="lineage mismatch"):
        replay_snapshot.csv_row_count(
            path,
            expected_snapshot="expected.json",
        )


def test_csv_row_count_requires_lineage_column(tmp_path):
    path = tmp_path / "prices.csv"
    write_csv(path, ["product_code"], [{"product_code": "0001"}])

    with pytest.raises(ValueError, match="missing source_snapshot"):
        replay_snapshot.csv_row_count(
            path,
            expected_snapshot="snapshot.json",
        )


def test_csv_row_count_rejects_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        replay_snapshot.csv_row_count(tmp_path / "missing.csv")


def test_validate_snapshot_accepts_registered_snapshot(
    monkeypatch, tmp_path
):
    filename, snapshot, registered, raw_dir = make_snapshot_fixture(
        monkeypatch, tmp_path
    )

    result = replay_snapshot.validate_snapshot(
        filename,
        FakeConnection(registered),
    )

    assert result["snapshot_id"] == 7
    assert result["raw_sha256"] == snapshot["raw_sha256"]
    assert result["semantic_sha256"] == snapshot["semantic_sha256"]
    assert result["semantic_hash_version"] == SEMANTIC_HASH_VERSION
    assert result["observation_count"] == 2829
    assert result["raw_path"] == (raw_dir / filename).resolve()


def test_validate_snapshot_rejects_path_traversal():
    with pytest.raises(ValueError, match="timestamped snapshot filename"):
        replay_snapshot.validate_snapshot(
            "../outside.json",
            FakeConnection(None),
        )


def test_validate_snapshot_rejects_unregistered_snapshot(
    monkeypatch, tmp_path
):
    filename, _, _, _ = make_snapshot_fixture(monkeypatch, tmp_path)

    with pytest.raises(ValueError, match="not registered"):
        replay_snapshot.validate_snapshot(
            filename,
            FakeConnection(None),
        )


def test_validate_snapshot_rejects_raw_hash_mismatch(
    monkeypatch, tmp_path
):
    filename, snapshot, registered, _ = make_snapshot_fixture(
        monkeypatch, tmp_path
    )
    snapshot["raw_sha256"] = "c" * 64

    with pytest.raises(ValueError, match="Raw SHA-256 mismatch"):
        replay_snapshot.validate_snapshot(
            filename,
            FakeConnection(registered),
        )


def test_validate_snapshot_rejects_semantic_hash_mismatch(
    monkeypatch, tmp_path
):
    filename, snapshot, registered, _ = make_snapshot_fixture(
        monkeypatch, tmp_path
    )
    snapshot["semantic_sha256"] = "c" * 64

    with pytest.raises(ValueError, match="Semantic SHA-256 mismatch"):
        replay_snapshot.validate_snapshot(
            filename,
            FakeConnection(registered),
        )


def test_validate_snapshot_rejects_old_hash_version(
    monkeypatch, tmp_path
):
    filename, _, registered, _ = make_snapshot_fixture(
        monkeypatch, tmp_path
    )
    registered = (
        *registered[:3],
        SEMANTIC_HASH_VERSION - 1,
        *registered[4:],
    )

    with pytest.raises(ValueError, match="semantic-hash version"):
        replay_snapshot.validate_snapshot(
            filename,
            FakeConnection(registered),
        )


def test_validate_snapshot_rejects_count_mismatch(
    monkeypatch, tmp_path
):
    filename, snapshot, registered, _ = make_snapshot_fixture(
        monkeypatch, tmp_path
    )
    snapshot["observation_count"] = 100

    with pytest.raises(ValueError, match="Snapshot count mismatch"):
        replay_snapshot.validate_snapshot(
            filename,
            FakeConnection(registered),
        )
