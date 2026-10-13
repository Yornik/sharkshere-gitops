import contextlib, datetime as dt, unittest, urllib.error
from unittest import mock
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

class Deleting(unittest.TestCase):
    """delete_object repeats a transient failure and gives up on a real one."""

    CFG = dict(endpoint="https://fsn1.example.com", region="fsn1", bucket="b", access="A", secret="S")

    @staticmethod
    def _ok(status=204):
        res = mock.Mock(status=status)
        cm = mock.MagicMock()
        cm.__enter__.return_value = res
        return cm

    @staticmethod
    def _http(code):
        return urllib.error.HTTPError("https://fsn1.example.com/b/k", code, "boom", {}, None)

    @contextlib.contextmanager
    def _urlopen(self, side_effect):
        with mock.patch.object(prune.urllib.request, "urlopen", side_effect=side_effect) as m, \
             mock.patch.object(prune.time, "sleep") as slept:
            yield m, slept

    def test_a_504_is_retried_and_then_succeeds(self):
        # the failure seen on 2026-10-11: one 504, then the delete goes through
        with self._urlopen([self._http(504), self._ok()]) as (m, slept):
            self.assertEqual(prune.delete_object(self.CFG, "k"), 204)
        self.assertEqual(m.call_count, 2)
        slept.assert_called_once_with(1)

    def test_it_backs_off_between_attempts(self):
        with self._urlopen([self._http(503), self._http(500), self._ok()]) as (m, slept):
            prune.delete_object(self.CFG, "k")
        self.assertEqual([c.args[0] for c in slept.call_args_list], [1, 2])

    def test_a_403_is_not_retried(self):
        with self._urlopen([self._http(403), self._ok()]) as (m, slept):
            with self.assertRaises(urllib.error.HTTPError) as caught:
                prune.delete_object(self.CFG, "k")
        self.assertEqual(caught.exception.code, 403)
        self.assertEqual(m.call_count, 1, "a permission error must not be repeated")
        slept.assert_not_called()

    def test_it_gives_up_after_the_last_attempt(self):
        with self._urlopen([self._http(504)] * 4) as (m, slept):
            with self.assertRaises(urllib.error.HTTPError):
                prune.delete_object(self.CFG, "k", attempts=4)
        self.assertEqual(m.call_count, 4)
        self.assertEqual(slept.call_count, 3, "no sleep after the final attempt")

    def test_a_timeout_is_retried(self):
        with self._urlopen([urllib.error.URLError("timed out"), self._ok()]) as (m, slept):
            prune.delete_object(self.CFG, "k")
        self.assertEqual(m.call_count, 2)


unittest.main(verbosity=1)
