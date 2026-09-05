# -*- coding: utf-8 -*-
"""คำนวณเวลาที่ต้องใช้จาก 3,000 -> 1,000,000 บาท (ทบต้น + เงินเติมรายเดือน)"""

START = 3000
TARGET = 1_000_000
MAX_MONTHS = 600  # 50 ปี


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
    years = m / 12
    return f"{m} เดือน (~{years:.1f} ปี)"


print("=" * 70)
print("กรณีที่ 1: ทบต้นอย่างเดียวจาก 3,000 บาท (ไม่มีเงินเติม)")
print("=" * 70)
for r in [0.01, 0.02, 0.03, 0.04, 0.05, 0.06, 0.08, 0.10]:
    m = months_to_target(r)
    # สถิติจริงบอกว่าเท่าไหร่สมเหตุสมผล
    note = ""
    if r <= 0.02:
        note = "(ระดับคนทั่วไป/เทรดกลาง ๆ ตามสถิติ CMC)"
    elif r <= 0.04:
        note = "(เทรดดี มีวินัย — เป้าหมายที่ทำได้จริง)"
    elif r <= 0.06:
        note = "(เก่งจริง top 10% — ต้องระบบดีมาก)"
    else:
        note = "(ฝันกลางวัน — ไม่มีสถิติรองรับการทำได้ยั่งยืน)"
    print(f"  +{r*100:.0f}%/เดือน -> {fmt(m)}  {note}")

print()
print("=" * 70)
print("กรณีที่ 2: ทบต้น + เงินเติมจากเงินเดือนทุกเดือน (สมมติผลตอบแทน +4%/เดือน = ระดับดีมีวินัย)")
print("=" * 70)
for add in [0, 1000, 3000, 5000, 10000, 20000]:
    m = months_to_target(0.04, add)
    print(f"  เติม {add:>6,} บาท/เดือน -> {fmt(m)}")

print()
print("=" * 70)
print("กรณีที่ 3: เงินเติม + อัตราผลตอบแทน 2 ระดับ (อนุรักษ์นิยม +2% vs สมดุล +4%)")
print("=" * 70)
for r in [0.02, 0.04]:
    for add in [3000, 5000, 10000]:
        m = months_to_target(r, add)
        print(f"  {r*100:.0f}%/เดือน + เติม {add:>6,} บาท/เดือน -> {fmt(m)}")