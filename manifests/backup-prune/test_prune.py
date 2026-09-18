import datetime as dt, unittest
import prune
UTC = dt.timezone.utc
NOW = dt.datetime(2030, 6, 30, 12, 0, tzinfo=UTC)

def daily(days):   # one backup a day at 03:30, going back `days` days
    return [(f"b{d:03d}", (NOW - dt.timedelta(days=d)).replace(hour=3, minute=30)) for d in range(days)]

POLICY = dict(keep_all_days=14, daily_days=14, weekly_weeks=8, monthly_months=6, min_keep=7)

class Policy(unittest.TestCase):
    def test_everything_recent_is_kept(self):
        keep = prune.keep_set(daily(200), NOW, **POLICY)
        for d in range(14):
            self.assertIn(f"b{d:03d}", keep)

    def test_older_backups_thin_to_one_a_week_then_one_a_month(self):
        objs = daily(200); keep = prune.keep_set(objs, NOW, **POLICY)
        when = dict(objs)
        weekly = [k for k in keep if 14 < (NOW - when[k]).days <= 56]
        monthly = [k for k in keep if 56 < (NOW - when[k]).days <= 186]
        beyond = [k for k in keep if (NOW - when[k]).days > 186]
        self.assertIn(len(weekly), (6, 7))          # six or seven ISO weeks touch that band
        self.assertIn(len(monthly), (4, 5))
        self.assertEqual(beyond, [])
        weeks = {when[k].isocalendar()[:2] for k in weekly}
        self.assertEqual(len(weeks), len(weekly), "two survivors in one week")
        # the survivor of each week is that week's newest backup inside the band
        for k in weekly:
            w = when[k].isocalendar()[:2]
            same = [m for kk, m in objs if m.isocalendar()[:2] == w and 14 < (NOW - m).days <= 56]
            self.assertEqual(when[k], max(same))

    def test_steady_state_is_small(self):
        keep = prune.keep_set(daily(400), NOW, **POLICY)
        self.assertLess(len(keep), 30)
        self.assertGreater(len(keep), 20)

    def test_the_newest_few_survive_even_when_everything_is_old(self):
        old = [(f"o{i}", NOW - dt.timedelta(days=400 + i)) for i in range(20)]
        keep = prune.keep_set(old, NOW, **POLICY)
        self.assertEqual(keep, {f"o{i}" for i in range(7)})

    def test_three_hourly_snapshots(self):
        snaps = [(f"s{i:04d}", NOW - dt.timedelta(hours=3 * i)) for i in range(8 * 190)]
        keep = prune.keep_set(snaps, NOW, keep_all_days=3, daily_days=14, weekly_weeks=8, monthly_months=6, min_keep=8)
        recent = [k for k in keep if (NOW - dict(snaps)[k]).total_seconds() <= 3 * 86400]
        self.assertEqual(len(recent), 25)            # every snapshot of the last three days
        self.assertLessEqual(len(keep), 52)          # 25 recent + 11 daily + about 7 weekly + about 5 monthly
        # Ages as the policy measures them, in fractions of a day. Counting in
        # whole days here put a 14.5-day-old weekly survivor into the daily
        # band and reported a day with two survivors that the policy never made.
        age = lambda k: (NOW - dict(snaps)[k]).total_seconds() / 86400
        days = [dict(snaps)[k].date() for k in keep if 3 < age(k) <= 14]
        self.assertEqual(len(days), len(set(days)), "two survivors on one day")

    def test_running_it_twice_deletes_nothing_more(self):
        objs = daily(200); keep = prune.keep_set(objs, NOW, **POLICY)
        survivors = [o for o in objs if o[0] in keep]
        self.assertEqual(prune.keep_set(survivors, NOW, **POLICY), keep)

class Signing(unittest.TestCase):
    def test_the_published_aws_example(self):
        url = prune.presign("GET", "https://examplebucket.s3.amazonaws.com", "us-east-1", "AKIAIOSFODNN7EXAMPLE",
                            "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY", "/test.txt",
                            now=dt.datetime(2013, 5, 24, tzinfo=UTC), ttl=86400)
        self.assertTrue(url.endswith("aeeed9bbccd4d02ee5c0109b86d86835f995330da4c265957d157751f604d404"), url)

unittest.main(verbosity=1)
