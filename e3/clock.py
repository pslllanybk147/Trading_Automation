# -*- coding: utf-8 -*-
"""E3 clock — session windows + DST.

หลักการ spec §3: เก็บทุกอย่างเป็น UTC ภายในระบบ; ห้าม hardcode offset —
ใช้ tz database (Europe/London, America/New_York) แล้ว resolve DST ต่อวัน
โดย `localize()` เป็นจุดเดียวที่แตะ timezone ทั้งระบบ (test_dst_transition ยิงที่ฟังก์ชันนี้)

Sessions (spec §3 ตาราง Winter/Summer — derive จาก tz database ไม่ hardcode offset):
  Asian range  = 00:00–07:00 Europe/London local (Winter 00:00-07:00 UTC / Summer 23:00(D-1)-06:00)
  London window = 08:00–10:00 Europe/London local (08:00-10:00 UTC winter / 07:00-09:00 summer)
  NY overlap   = 08:30–11:00 America/New_York local (13:30-16:00 UTC winter / 12:30-15:00 summer)
  Flat-by      = 20:00 Europe/London local (20:00 UTC winter / 19:00 summer)
แกนของ "วันเทรด" = วันตาม Europe/London (ทุก session ของวันเดียวกันอยู่ใน London date เดียว)
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

UTC = timezone.utc
_LONDON = ZoneInfo("Europe/London")
_NY = ZoneInfo("America/New_York")

# ช่วงเวลาท้องถิ่น (คงที่ตลอดปี — DST จัดการตอนแปลง)
ASIAN_LOCAL = (0, 0, 7, 0)        # London 00:00–07:00
LONDON_LOCAL = (8, 0, 10, 0)      # London 08:00–10:00
NY_LOCAL = (8, 30, 11, 0)         # New York 08:30–11:00
FLAT_BY_LOCAL = (20, 0)           # London 20:00

# FX/gold weekend: ตลาดปิดศุกร์ 22:00 UTC → เปิดอาทิตย์ 23:00 UTC (ประมาณ CME/OTC)
WEEKEND_CLOSE_DOW = 4             # Friday
WEEKEND_CLOSE_UTC = (22, 0)
WEEKEND_OPEN_DOW = 6              # Sunday
WEEKEND_OPEN_UTC = (23, 0)


def localize(dt_utc: datetime, tz_name: str) -> datetime:
    """จุดเดียวที่แตะ timezone — แปลง aware UTC dt ไปโซนที่กำหนด (DST resolve ต่อวัน)"""
    if dt_utc.tzinfo is None:
        dt_utc = dt_utc.replace(tzinfo=UTC)
    return dt_utc.astimezone(ZoneInfo(tz_name))


@dataclass(frozen=True)
class SessionWindow:
    start: datetime  # aware UTC
    end: datetime    # aware UTC
    kind: str        # "asian" | "london" | "ny" | "flat_by"

    def contains(self, ts: int) -> bool:
        t = datetime.fromtimestamp(ts, tz=UTC)
        return self.start <= t < self.end


def _local_window_utc(d_utc: datetime, tz: ZoneInfo, sh: int, sm: int, eh: int, em: int) -> SessionWindow:
    """หา window ของ 'วันตามโซน tz' ที่ตรงกับวัน UTC ของ d_utc แล้วคืนขอบเขตเป็น UTC"""
    local_date = d_utc.astimezone(tz).date()
    start = datetime(local_date.year, local_date.month, local_date.day, sh, sm, tzinfo=tz)
    end = datetime(local_date.year, local_date.month, local_date.day, eh, em, tzinfo=tz)
    return SessionWindow(start.astimezone(UTC), end.astimezone(UTC), "")


def sessions_for_day(ts: int) -> dict[str, SessionWindow]:
    """คืน session windows ทั้งหมดของ 'วันเทรด' ที่ ts อยู่ (แกน = วันตาม Europe/London)"""
    t = datetime.fromtimestamp(ts, tz=UTC)
    lon_date = t.astimezone(_LONDON).date()
    day_lon = datetime(lon_date.year, lon_date.month, lon_date.day, tzinfo=_LONDON)

    a_sh, a_sm, a_eh, a_em = ASIAN_LOCAL
    asian = SessionWindow(day_lon, day_lon + timedelta(hours=a_eh, minutes=a_em), "asian")
    lon = SessionWindow(day_lon + timedelta(hours=LONDON_LOCAL[0], minutes=LONDON_LOCAL[1]),
                        day_lon + timedelta(hours=LONDON_LOCAL[2], minutes=LONDON_LOCAL[3]), "london")
    # NY อยู่คนละโซน — anchor ด้วย London date เดียวกัน (เช้า ET ของวันเดียวกัน
    # ตรงกับบ่าย UTC ของ London date นั้นเสมอ; ใช้ NY-local date ตรง ๆ จะ lag ไปวันก่อน)
    ny_day = datetime(lon_date.year, lon_date.month, lon_date.day, tzinfo=_NY)
    ny = SessionWindow(ny_day + timedelta(hours=NY_LOCAL[0], minutes=NY_LOCAL[1]),
                       ny_day + timedelta(hours=NY_LOCAL[2], minutes=NY_LOCAL[3]), "ny")
    fb_h, fb_m = FLAT_BY_LOCAL
    fb = day_lon + timedelta(hours=fb_h, minutes=fb_m)
    flat_by = SessionWindow(fb, fb, "flat_by")  # instant marker
    return {"asian": asian, "london": lon, "ny": ny, "flat_by": flat_by}


def trade_window_for(ts: int) -> SessionWindow | None:
    """คืน trade window ที่ ts อยู่ (London หรือ NY) — None ถ้านอก window"""
    s = sessions_for_day(ts)
    if s["london"].contains(ts):
        return s["london"]
    if s["ny"].contains(ts):
        return s["ny"]
    return None


def is_asian(ts: int) -> bool:
    return sessions_for_day(ts)["asian"].contains(ts)


def at_flat_by(ts: int) -> bool:
    """ts อยู่ช่วง >= flat-by ของ London-date ปัจจุบัน (หรือหลังจากนั้น)"""
    s = sessions_for_day(ts)
    fb = s["flat_by"].start
    return datetime.fromtimestamp(ts, tz=UTC) >= fb


def next_flat_by(ts: int) -> datetime:
    return sessions_for_day(ts)["flat_by"].start


def classify_gap(prev_ts: int, ts: int) -> str:
    """DQ012 — จำแนกช่องว่างระหว่างแท่ง M15: ok / daily_break / weekend / outage"""
    if prev_ts is None:
        return "ok"
    gap_min = (ts - prev_ts) / 60.0
    if gap_min <= 15:
        return "ok"
    prev_dt = datetime.fromtimestamp(prev_ts, tz=UTC)
    dt = datetime.fromtimestamp(ts, tz=UTC)
    # weekend: ข้ามปิดศุกร์ 22:00 → เปิดอาทิตย์ 23:00 UTC
    if prev_dt.weekday() == WEEKEND_CLOSE_DOW and prev_dt.hour >= WEEKEND_CLOSE_UTC[0] \
            and dt.weekday() >= WEEKEND_OPEN_DOW:
        return "weekend"
    if dt.date() != prev_dt.date() and gap_min <= 24 * 60 + 120:
        return "daily_break"
    return "outage"   # ช่องว่างผิดปกติในสัปดาห์ = feed outage (spec §2: กันวันนั้นออก)
