# -*- coding: utf-8 -*-
"""คำนวณเวลาจากเงินต้น 50,000 -> 1,000,000 บาท (ทบต้น + เงินเติมรายเดือน)"""

START = 50_000
TARGET = 1_000_000
MAX_MONTHS = 600


def months_to_target(monthly_rate, monthly_add=0):
    bal = START
    m = 0
    while bal < TARGET and m < MAX_MONTHS:
        m += 1
        bal = bal * (1 + monthly_rate) + monthly_add
    return m if bal >= TARGET else None


def fmt(m):
    if m is None:
        return "> 50 ปี"
    return f"{m} เดือน (~{m/12:.1f} ปี)"


print("=" * 70)
print("กรณีที่ 1: เงินต้น 50,000 ทบต้นอย่างเดียว (ไม่มีเงินเติม)")
print("=" * 70)
for r in [0.01, 0.02, 0.03, 0.04, 0.05, 0.06, 0.08, 0.10]:
    m = months_to_target(r)
    note = ""
    if r <= 0.02:
        note = "(ระดับคนทั่วไป ตามสถิติ CMC)"
    elif r <= 0.04:
        note = "(เทรดดี มีวินัย)"
    elif r <= 0.06:
        note = "(เก่งจริง top 10%)"
    else:
        note = "(ฝันกลางวัน — ไม่มีสถิติรองรับ)"
    print(f"  +{r*100:.0f}%/เดือน -> {fmt(m)}  {note}")

print()
print("=" * 70)
print("กรณีที่ 2: เงินต้น 50,000 + เงินเติมจากเงินเดือน (+4%/เดือน = ระดับดีมีวินัย)")
print("=" * 70)
for add in [0, 1000, 3000, 5000, 10000, 20000]:
    m = months_to_target(0.04, add)
    print(f"  เติม {add:>6,} บาท/เดือน -> {fmt(m)}")

print()
print("=" * 70)
print("กรณีที่ 3: เปรียบเทียบ 3,000 vs 50,000 (ทบต้นอย่างเดียว)")
print("=" * 70)
for r in [0.02, 0.03, 0.04, 0.05]:
    m3 = months_to_target(r)
    m50 = months_to_target(r)
    # คำนวณ 3,000 ใหม่แยก
    bal = 3000
    mm = 0
    while bal < TARGET and mm < MAX_MONTHS:
        mm += 1
        bal = bal * (1 + r)
    print(f"  +{r*100:.0f}%/เดือน: 3,000 บาท -> {fmt(mm)} | 50,000 บาท -> {fmt(m50)}")