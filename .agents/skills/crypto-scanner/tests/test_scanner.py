import unittest
from scripts.scanner import calculate_wilder_rsi, calculate_risk_reward, is_valid_long, is_valid_short

class TestCryptoScanner(unittest.TestCase):
    def test_wilder_rsi_uptrend(self):
        closes = [float(i) for i in range(1, 25)]
        rsi = calculate_wilder_rsi(closes, period=14)
        self.assertEqual(rsi, 100.0)

    def test_wilder_rsi_downtrend(self):
        closes = [float(100 - i) for i in range(1, 25)]
        rsi = calculate_wilder_rsi(closes, period=14)
        self.assertEqual(rsi, 0.0)

    def test_wilder_rsi_flat(self):
        closes = [50.0] * 25
        self.assertEqual(calculate_wilder_rsi(closes), 50.0)

    def test_wilder_rsi_insufficient_data(self):
        closes = [10.0, 12.0, 11.0]
        rsi = calculate_wilder_rsi(closes, period=14)
        self.assertEqual(rsi, 50.0)

    def test_calculate_risk_reward_long(self):
        # Entry 100, TP 110, SL 95 -> Risk 5, Reward 10 -> R:R = 2.0
        rr = calculate_risk_reward(entry=100.0, target=110.0, stop=95.0, is_short=False)
        self.assertEqual(rr, 2.0)

    def test_calculate_risk_reward_short(self):
        # Entry 100, TP 90, SL 105 -> Risk 5, Reward 10 -> R:R = 2.0
        rr = calculate_risk_reward(entry=100.0, target=90.0, stop=105.0, is_short=True)
        self.assertEqual(rr, 2.0)

    def test_is_valid_long_accepts_good_setup(self):
        valid = is_valid_long(
            entry=100.0,
            tp1=110.0,
            sl=95.0,
            rr=2.0,
            trend_4h=True,
            rsi_1h=55.0,
            trend_1h=True,
            vol_spike=True
        )
        self.assertTrue(valid)

    def test_is_valid_long_rejects_without_volume_spike(self):
        valid = is_valid_long(
            entry=100.0,
            tp1=110.0,
            sl=95.0,
            rr=2.0,
            trend_4h=True,
            rsi_1h=55.0,
            trend_1h=True,
            vol_spike=False
        )
        self.assertFalse(valid)

    def test_is_valid_short_accepts_good_setup(self):
        valid = is_valid_short(
            entry=100.0,
            tp1=90.0,
            sl=105.0,
            rr=2.0,
            trend_4h=False,  # Bearish 4H trend
            rsi_1h=40.0,
            trend_1h=True,
            vol_spike=True
        )
        self.assertTrue(valid)

if __name__ == '__main__':
    unittest.main()
