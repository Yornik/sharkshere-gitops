# Loki chunks cache reserved 9.8 GiB for a 0.3 % hit rate

**Date:** 2026-07-10
**Component:** `loki` Application, chart `loki`, SingleBinary mode
**Severity:** capacity finding, no user-facing effect

## Effect

The chart default `chunksCache` memcached reserved 9830 MiB of memory as request and limit. This is `allocatedMemory 8192` plus 20 % overhead. The cluster has 128 GiB in total. One cache took 7.5 % of it.

## Cause

Loki runs in SingleBinary mode with a filesystem store on this cluster. The chunks cache sits in front of that store. Measurement on 2026-07-10 showed 632 MiB in use, 37 hits and 12092 misses. The hit rate was 0.3 %. The cache did no useful work.

The `resultsCache` had the same pattern at a smaller scale. The default request was 1229 MiB. The measured use was 24 MiB.

## Correction

- Set `chunksCache.enabled: false`.
- Keep `resultsCache` for repeated Grafana range queries. Set its allocated memory to 256 MB, which gives a request of about 307 MiB.

## Prevention

Measure a cache before you accept the chart default. The metrics to read are memory in use, hits and misses. If the hit rate is near zero, disable the cache.

## Evidence

- `apps/values.yaml`, comments above `chunksCache` and `resultsCache` in the `loki` values.
