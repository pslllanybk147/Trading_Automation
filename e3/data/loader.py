# -*- coding: utf-8 -*-
"""E3 loader — CSV/Parquet → normalized UTC bars → quality gate → cache.

- raw file ไม่เคยเข้า backtest ตรง — ผ่าน scan แล้วเก็บลง cache เท่านั้น
- cache invalidation: sha1(path, mtime, size, spec) — ไฟล์เปลี่ยน = scan ใหม่
- Bar ที่ได้มี .spread (float $/oz หรือ None) สำหรับ spread profile
- ไม่มี fill/smooth ใด ๆ — แท่งหาย = หายจริง (คุณภาพตัดสินที่ QualityScanner)
"""
from __future__ import annotations

import hashlib
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .schema import SourceSpec, to_spread_price

UTC = timezone.utc
M15 = 900


class Loader:
    def __init__(self, cache_path: str | None = "e3/data/cache_e3.db"):
        self.cache_path = cache_path
        if cache_path:
            Path(cache_path).parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(cache_path)
            self._conn.execute("""CREATE TABLE IF NOT EXISTS sources (
                sha TEXT PRIMARY KEY, path TEXT, loaded_at INTEGER, n_bars INTEGER)""")
            self._conn.execute("""CREATE TABLE IF NOT EXISTS bars_m15 (
                sha TEXT, ts INTEGER, o REAL, h REAL, l REAL, c REAL, v REAL, spread REAL,
                PRIMARY KEY (sha, ts))""")

    # ---- reading raw ----

    def _read_raw(self, spec: SourceSpec) -> list[dict]:
        p = Path(spec.path)
        if not p.exists():
            raise FileNotFoundError(spec.path)
        if p.suffix.lower() in (".parquet", ".pq"):
            return self._read_parquet(spec)
        return self._read_csv(spec)

    def _read_csv(self, spec: SourceSpec) -> list[dict]:
        import csv
        rows = []
        with open(spec.path, "r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            for r in reader:
                rows.append(r)
        return rows

    def _read_parquet(self, spec: SourceSpec) -> list[dict]:
        try:
            import pyarrow.parquet as pq  # type: ignore
        except ImportError as e:
            raise ImportError("pyarrow จำเป็นสำหรับ Parquet — pip install pyarrow") from e
        tbl = pq.read_table(spec.path)
        return tbl.to_pylist()

    # ---- normalize ----

    def _parse_ts(self, raw: str, spec: SourceSpec) -> int:
        """ts ดิบ → epoch UTC (ตาม source_tz) — รองรับ ISO และ epoch seconds/ms"""
        s = str(raw).strip()
        if s.replace(".", "", 1).isdigit():
            x = float(s)
            if x > 1e12:      # ms
                x /= 1000.0
            dt = datetime.fromtimestamp(x, tz=UTC)
        else:
            dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=spec.tz())   # naive → broker tz
            else:
                dt = dt.astimezone(spec.tz())
        return int(dt.timestamp())

    def normalize(self, spec: SourceSpec) -> list:
        from ..types import Bar
        rows = self._read_raw(spec)
        bars: list[Bar] = []
        for r in rows:
            ts = self._parse_ts(r[spec.time_column], spec)
            # align ลง grid M15 (bar เริ่มนาที 0/15/30/45)
            ts -= ts % M15
            o, h, l, c = (float(r["open"]), float(r["high"]),
                          float(r["low"]), float(r["close"]))
            v = float(r.get("volume") or 0.0)
            spread = None
            if spec.spread_column and spec.spread_column in r and r[spec.spread_column] != "":
                spread = to_spread_price(float(r[spec.spread_column]), spec)
            bars.append(Bar(ts, o, h, l, c, v, True, spread))
        bars.sort(key=lambda b: b.ts)
        return bars

    # ---- cache ----

    def _sha(self, spec: SourceSpec) -> str:
        p = Path(spec.path)
        st = p.stat()
        payload = f"{p.resolve()}|{st.st_mtime_ns}|{st.st_size}|{spec.source_tz}|{spec.spread_column}|{spec.spread_points}"
        return hashlib.sha1(payload.encode()).hexdigest()

    def load(self, spec: SourceSpec, force_rescan: bool = False):
        """คืน (bars, QualityReport) — ใช้ cache ถ้า sha ตรง"""
        from .quality import QualityScanner
        sha = self._sha(spec)
        if not force_rescan and self.cache_path and self._has_cache(sha):
            bars = self._from_cache(sha)
            rep = self._cached_report(bars)
            return bars, rep
        bars = self.normalize(spec)
        scanner = QualityScanner(spec)
        rep = scanner.scan(bars)
        if self.cache_path:
            self._to_cache(sha, spec, bars)
        return bars, rep

    def _has_cache(self, sha: str) -> bool:
        cur = self._conn.execute("SELECT n_bars FROM sources WHERE sha=?", (sha,))
        return cur.fetchone() is not None

    def _to_cache(self, sha: str, spec: SourceSpec, bars: list) -> None:
        self._conn.execute("INSERT OR REPLACE INTO sources VALUES (?,?,?,?)",
                           (sha, spec.path, int(datetime.now(tz=UTC).timestamp()), len(bars)))
        self._conn.executemany(
            "INSERT OR REPLACE INTO bars_m15 VALUES (?,?,?,?,?,?,?,?)",
            [(sha, b.ts, b.open, b.high, b.low, b.close, b.volume,
              getattr(b, "spread", None)) for b in bars])
        self._conn.commit()

    def _from_cache(self, sha: str) -> list:
        from ..types import Bar
        cur = self._conn.execute(
            "SELECT ts,o,h,l,c,v,spread FROM bars_m15 WHERE sha=? ORDER BY ts", (sha,))
        return [Bar(ts, o, h, l, c, v, True, sp)
                for ts, o, h, l, c, v, sp in cur.fetchall()]

    def _cached_report(self, bars: list):
        """report จาก cache — สร้างจาก bars (scan เร็วพอ ไม่ต้องเก็บ issues)"""
        from .quality import QualityScanner
        dummy = SourceSpec(path="(cache)", source_tz="UTC")
        return QualityScanner(dummy).scan(bars)

    def close(self):
        if self.cache_path:
            self._conn.close()


def load_bars(path: str, preset: str = "generic", **overrides):
    """helper เร็ว ๆ — อ่านไฟล์ + scan คืน (bars, report)"""
    from .quality import QualityScanner
    meta = dict(SourceSpec.__dataclass_fields__)  # noqa: F401
    kw = dict(path=path, source_tz=overrides.pop("source_tz", "UTC"))
    kw.update(overrides)
    spec = SourceSpec(**kw)
    loader = Loader(cache_path=None)
    bars = loader.normalize(spec)
    rep = QualityScanner(spec).scan(bars)
    return bars, rep


def spread_profile_from_bars(bars: list) -> dict[int, float]:
    """median spread ต่อชั่วโมง UTC — ใช้เป็น spread_profile ของ Backtester"""
    import statistics
    by_hour: dict[int, list[float]] = {}
    for b in bars:
        sp = getattr(b, "spread", None)
        if sp:
            by_hour.setdefault((b.ts // 3600) % 24, []).append(sp)
    return {h: statistics.median(v) for h, v in by_hour.items() if len(v) >= 5}
