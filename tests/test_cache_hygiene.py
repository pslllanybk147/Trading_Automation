# -*- coding: utf-8 -*-
"""Cache hygiene — จัดชั้นความสดของ symbol/tf ใน cache.db + prune"""
import sqlite3

import pytest

import cache_hygiene as ch


@pytest.fixture
def db(tmp_path):
    """cache.db จำลอง: 4 symbol ครอบคลุมทั้ง 4 ชั้น"""
    p = tmp_path / "cache.db"
    now = 1_800_000_000
    conn = sqlite3.connect(p)
    conn.execute("""CREATE TABLE candles (
        symbol TEXT, interval TEXT, ts INTEGER,
        o REAL, h REAL, l REAL, c REAL, v REAL,
        PRIMARY KEY (symbol, interval, ts))""")
    data = [
        # symbol, interval, last_age_days, bars
        ("FRESH", "4h", 1, 100),        # OK
        ("AGING1", "4h", 30, 100),      # AGING (เหมือน TON ตอนเพิ่ง delist)
        ("OLDXMR", "4h", 400, 200),     # ARCHIVE
        ("OLDRND", "1h", 500, 300),     # ARCHIVE
    ]
    for sym, tf, age, bars in data:
        t1 = now - age * ch.DAY
        t0 = t1 - (bars - 1) * 14400
        rows = [(sym, tf, t0 + i * 14400, 1.0, 1.0, 1.0, 1.0, 1.0)
                for i in range(bars)]
        conn.executemany("INSERT OR REPLACE INTO candles VALUES (?,?,?,?,?,?,?,?)",
                         rows)
    conn.commit()
    conn.close()
    return p, now


def test_classify_boundaries():
    assert ch.classify(0) == "OK"
    assert ch.classify(6.9) == "OK"
    assert ch.classify(7) == "AGING"
    assert ch.classify(179) == "AGING"
    assert ch.classify(180) == "STALE"
    assert ch.classify(364) == "STALE"
    assert ch.classify(365) == "ARCHIVE"


def test_sweep_classifies_all_four(db):
    p, now = db
    rows = ch.sweep(p, now_ts=now)
    by = {r["symbol"]: r for r in rows}
    assert by["FRESH"]["status"] == "OK"
    assert by["AGING1"]["status"] == "AGING"
    assert by["OLDXMR"]["status"] == "ARCHIVE"
    assert by["OLDRND"]["status"] == "ARCHIVE"
    assert by["AGING1"]["bars"] == 100
    assert by["OLDXMR"]["age_days"] == 400.0


def test_sweep_missing_db_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        ch.sweep(tmp_path / "nope.db")


def test_prune_dry_run_deletes_nothing(db):
    p, now = db
    rows = ch.sweep(p, now_ts=now)
    targets = ch.prune(rows, p, dry_run=True)
    assert {t["symbol"] for t in targets} == {"OLDXMR", "OLDRND"}
    # ข้อมูลยังอยู่ครบ
    assert len(ch.sweep(p, now_ts=now)) == 4


def test_prune_removes_archive_only(db):
    p, now = db
    rows = ch.sweep(p, now_ts=now)
    removed = ch.prune(rows, p)
    assert {r["symbol"] for r in removed} == {"OLDXMR", "OLDRND"}
    left = {r["symbol"] for r in ch.sweep(p, now_ts=now)}
    assert left == {"FRESH", "AGING1"}  # AGING ไม่ถูกแตะโดย default


def test_prune_also_stale(db):
    p, now = db
    # เพิ่ม STALE pair
    conn = sqlite3.connect(p)
    t1 = now - 200 * ch.DAY
    rows = [("STALE1", "4h", t1 + i * 14400, 1.0, 1.0, 1.0, 1.0, 1.0)
            for i in range(50)]
    conn.executemany("INSERT INTO candles VALUES (?,?,?,?,?,?,?,?)", rows)
    conn.commit()
    conn.close()
    all_rows = ch.sweep(p, now_ts=now)
    ch.prune(all_rows, p, also_stale=True)
    left = {r["symbol"] for r in ch.sweep(p, now_ts=now)}
    assert "STALE1" not in left and "FRESH" in left


def test_main_report_and_exit_code(db, capsys):
    p, now = db
    rc = ch.main(["--db", str(p)])
    out = capsys.readouterr().out
    assert "OLDXMR" in out and "ARCHIVE" in out
    assert rc == 1  # มี STALE/ARCHIVE


def test_main_clean_exit_zero(db, capsys):
    p, now = db
    ch.prune(ch.sweep(p, now_ts=now), p)  # เก็บก่อน
    rc = ch.main(["--db", str(p)])
    assert rc == 0
