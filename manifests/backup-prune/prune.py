#!/usr/bin/env python3
"""Thin the backups in one S3 bucket by age.

Backups that are kept forever cost money and are never looked at; backups that
are all the same age are no use the day you need last month's. This keeps
everything recent, then one a day, then one a week, then one a month, and
deletes the rest.

It deletes backups, so it is careful about when it does not:

  * Nothing is deleted unless PRUNE_APPLY is exactly "true". Otherwise it
    prints what it would do and exits.
  * Only keys matching KEY_REGEX are considered at all. Anything else in the
    bucket is somebody else's, and is neither counted nor touched.
  * The newest MIN_KEEP backups are kept whatever their age.
  * If the newest backup is older than STALE_DAYS, the thing making backups has
    stopped, and thinning what is left would be the wrong response. It deletes
    nothing and exits non-zero, so the failed Job is what gets noticed.

Standard library only. The S3 calls are presigned URLs (Signature Version 4,
query-string form) fetched with urllib, which is a list and a delete and needs
no SDK.
"""
import datetime as dt
import hashlib
import hmac
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

UTC = dt.timezone.utc


# --------------------------------------------------------------- the policy

def keep_set(objects, now, keep_all_days, daily_days, weekly_weeks, monthly_months, min_keep):
    """Returns the keys to keep. `objects` is [(key, modified_utc)].

    Bands are measured from `now` and do not overlap: an object is judged by
    the first band its age falls in. Within the daily, weekly and monthly
    bands the NEWEST object of each day, ISO week or month survives.
    """
    ordered = sorted(objects, key=lambda o: o[1], reverse=True)
    keep = {key for key, _ in ordered[:min_keep]}

    daily_end = max(daily_days, keep_all_days)
    weekly_end = max(weekly_weeks * 7, daily_end)
    monthly_end = max(monthly_months * 31, weekly_end)

    seen = set()
    for key, modified in ordered:                       # newest first
        age = (now - modified).total_seconds() / 86400
        if age <= keep_all_days:
            keep.add(key)
            continue
        if age <= daily_end:
            bucket = ("day", modified.date())
        elif age <= weekly_end:
            iso = modified.isocalendar()
            bucket = ("week", iso[0], iso[1])
        elif age <= monthly_end:
            bucket = ("month", modified.year, modified.month)
        else:
            continue
        if bucket not in seen:
            seen.add(bucket)
            keep.add(key)
    return keep


# ------------------------------------------------------------------- S3

def _sign(key, msg):
    return hmac.new(key, msg.encode(), hashlib.sha256).digest()


def _enc(s, slash=False):
    return urllib.parse.quote(s, safe="-_.~" + ("/" if slash else ""))


def presign(method, endpoint, region, access, secret, path, query=None, now=None, ttl=300):
    now = now or dt.datetime.now(UTC)
    host = urllib.parse.urlsplit(endpoint).netloc
    date, stamp = now.strftime("%Y%m%d"), now.strftime("%Y%m%dT%H%M%SZ")
    scope = f"{date}/{region}/s3/aws4_request"
    q = dict(query or {})
    q.update({"X-Amz-Algorithm": "AWS4-HMAC-SHA256", "X-Amz-Credential": f"{access}/{scope}",
              "X-Amz-Date": stamp, "X-Amz-Expires": str(ttl), "X-Amz-SignedHeaders": "host"})
    canonical_query = "&".join(f"{_enc(k)}={_enc(v)}" for k, v in sorted(q.items()))
    canonical = "\n".join([method, _enc(path, slash=True), canonical_query, f"host:{host}\n", "host", "UNSIGNED-PAYLOAD"])
    to_sign = "\n".join(["AWS4-HMAC-SHA256", stamp, scope, hashlib.sha256(canonical.encode()).hexdigest()])
    k = _sign(_sign(_sign(_sign(("AWS4" + secret).encode(), date), region), "s3"), "aws4_request")
    signature = hmac.new(k, to_sign.encode(), hashlib.sha256).hexdigest()
    return f"{endpoint.rstrip('/')}{_enc(path, slash=True)}?{canonical_query}&X-Amz-Signature={signature}"


def list_objects(cfg):
    token, out = None, []
    while True:
        query = {"list-type": "2", "max-keys": "1000"}
        if cfg["prefix"]:
            query["prefix"] = cfg["prefix"]
        if token:
            query["continuation-token"] = token
        url = presign("GET", cfg["endpoint"], cfg["region"], cfg["access"], cfg["secret"], "/" + cfg["bucket"], query)
        with urllib.request.urlopen(url, timeout=60) as res:
            root = ET.fromstring(res.read())
        ns = {"s": root.tag.split("}")[0].strip("{")} if root.tag.startswith("{") else {}
        find = (lambda el, name: el.find("s:" + name, ns)) if ns else (lambda el, name: el.find(name))
        for c in (root.findall("s:Contents", ns) if ns else root.findall("Contents")):
            modified = dt.datetime.fromisoformat(find(c, "LastModified").text.replace("Z", "+00:00"))
            out.append((find(c, "Key").text, modified, int(find(c, "Size").text)))
        nxt = find(root, "NextContinuationToken")
        if nxt is None or not nxt.text:
            return out
        token = nxt.text


def delete_object(cfg, key):
    url = presign("DELETE", cfg["endpoint"], cfg["region"], cfg["access"], cfg["secret"], f"/{cfg['bucket']}/{key}")
    req = urllib.request.Request(url, method="DELETE")
    with urllib.request.urlopen(req, timeout=60) as res:
        return res.status


# ------------------------------------------------------------------ main

def env_int(name, default):
    raw = os.environ.get(name, "").strip()
    return int(raw) if raw else default


def gb(n):
    return f"{n / 1e9:,.2f} GB"


def main():
    cfg = {
        "endpoint": os.environ["S3_ENDPOINT"], "region": os.environ["S3_REGION"],
        "bucket": os.environ["S3_BUCKET"], "prefix": os.environ.get("S3_PREFIX", ""),
        "access": os.environ["S3_ACCESS_KEY_ID"], "secret": os.environ["S3_SECRET_ACCESS_KEY"],
    }
    pattern = re.compile(os.environ["KEY_REGEX"])
    apply = os.environ.get("PRUNE_APPLY", "").strip() == "true"
    policy = dict(keep_all_days=env_int("KEEP_ALL_DAYS", 14), daily_days=env_int("KEEP_DAILY_DAYS", 14),
                  weekly_weeks=env_int("KEEP_WEEKLY_WEEKS", 8), monthly_months=env_int("KEEP_MONTHLY_MONTHS", 6),
                  min_keep=env_int("MIN_KEEP", 7))
    stale_days = env_int("STALE_DAYS", 3)

    everything = list_objects(cfg)
    ours = [o for o in everything if pattern.search(o[0])]
    print(f"{cfg['bucket']}: {len(everything)} objects, {len(ours)} of them backups matching {pattern.pattern!r}")
    print(f"policy: {policy}, stale after {stale_days} days, apply={apply}")
    if not ours:
        print("nothing to do")
        return 0

    now = dt.datetime.now(UTC)
    newest = max(o[1] for o in ours)
    if (now - newest).total_seconds() / 86400 > stale_days:
        print(f"REFUSING: the newest backup is from {newest:%Y-%m-%d %H:%M} UTC, more than {stale_days} days ago. "
              "Backups have stopped; deleting nothing.")
        return 2

    keep = keep_set([(k, m) for k, m, _ in ours], now, **policy)
    doomed = sorted((o for o in ours if o[0] not in keep), key=lambda o: o[1])
    kept_bytes = sum(s for k, _, s in ours if k in keep)
    print(f"keep   {len(keep):>5} backups, {gb(kept_bytes)}")
    print(f"delete {len(doomed):>5} backups, {gb(sum(s for _, _, s in doomed))}")
    for key, modified, size in doomed:
        print(f"  {'delete ' if apply else 'would delete'} {modified:%Y-%m-%d %H:%M}  {size / 1e6:>9,.1f} MB  {key}")

    if not apply:
        print("dry run: nothing was deleted. Set PRUNE_APPLY=true to delete.")
        return 0

    failed = 0
    for key, _, _ in doomed:
        try:
            delete_object(cfg, key)
        except urllib.error.URLError as err:
            failed += 1
            print(f"  could not delete {key}: {err}")
    print(f"deleted {len(doomed) - failed}, failed {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
