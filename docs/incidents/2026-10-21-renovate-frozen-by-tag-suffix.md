# Renovate opened no bump for a pinned image for 8 months

**Date:** 2026-10-21
**Component:** `qbittorrent` Application, `renovate.json5`
**Severity:** update gap, no user-facing effect

## Effect

qBittorrent ran an image built on 2026-02-08 until 2026-10-21. Renovate opened no pull request for it in that time. Upstream shipped 5.2.0, 5.2.1, 5.2.2, 5.2.3, 5.2.4 and 5.3.0.

Nothing reported the gap. Renovate logged no error. No CI check failed. No alert fired. An operator found it by asking why 5.3.0 had not arrived.

This is the 3rd time this fault class reached this repository.

| Package | What moved in the tag | Found |
|---|---|---|
| `quay.io/argoproj/argocd` | the `-rc7` prerelease suffix | before this |
| `jellyfin/jellyfin` | the number of version segments, `10.11.11` to `12.0` | before this |
| `lscr.io/linuxserver/qbittorrent` | the `-ls440` build counter | 2026-10-21 |

## Cause

The default docker versioning reads the text after the first hyphen in a tag as a compatibility suffix. Renovate keeps that suffix on an update. It offers `1.2.1-alpine` for `1.2.0-alpine`, and it offers neither `1.2.1` nor `1.2.1-stretch`.

The pin was `lscr.io/linuxserver/qbittorrent:5.1.4-r2-ls440`, so the suffix was `r2-ls440`. `ls440` is a LinuxServer build counter and it changes on every build. No later tag carried `r2-ls440`. Renovate therefore found no candidate, and it also rejected the rebuilds `ls441` to `ls446` of the same release.

LinuxServer changed the scheme at 5.2.0 as well. `-r<N>-ls<build>` became `_v<libtorrent>-ls<build>`. The pin then named a shape that upstream had left, so a versioning rule alone could not reach it either.

NOTE: `haproxy:3.4.7-alpine` and `python:3.15-alpine` bump on time. `alpine` is a suffix that stays the same, which is the case this behaviour exists for. The fault needs a suffix that moves.

NOTE: before 2026-08-31 the pin read `latest`. The running build then changed on each pull, and no file recorded which build served.

## Correction

1. Move the pin by hand to the current scheme. A versioning rule cannot repair a tag that matches no pattern.
2. Add a `packageRule` with a `regex` versioning that reads the current scheme. Anchor the pattern, so it takes the plain release tags and rejects `latest`, the per-arch tags and the other libtorrent line.
3. Set `automerge: false` and `groupName: null` for the package. The LinuxServer tag carries the libtorrent version. It changes inside a bump that the regex reads as a build bump. libtorrent writes the resume data.

See the comments on the 2 qBittorrent rules in `renovate.json5`.

CAUTION: `labels` and `groupName` need care in a later rule. A later rule replaces `labels` rather than merging them, so it drops a label that an earlier rule set. It also keeps the `groupName` of an earlier rule unless it sets its own. A grouped pull request takes the labels of each bump in it.

## Prevention

Detection is the hard part. Renovate reports nothing when it opens no pull request, so a frozen pin reads the same as a current one. The 3 occurrences were each found by a person who asked about a version.

These checks would find the next one:

1. Compare each pinned image against the versioning regex of its own `packageRule`. The qBittorrent pin stopped matching its scheme at 5.2.0.
2. Compare each pin against the newest tag upstream. A pin that is many releases behind is the signal.
3. Read the Renovate dashboard issue. It lists a dependency that Renovate cannot resolve.

CAUTION: read a new pin for a moving suffix before you commit it. The 3 known shapes are a build counter, a prerelease and a changed segment count. The examples are `-ls440`, `-rc7` and `10.11.11` to `12.0`. A tag that holds a build number or a date freezes Renovate.

CAUTION: `latest` hides the same gap in a different way. The build changes with no change in git, so the cluster runs an image that no file names.

## Evidence

- `renovate.json5`, the 2 `packageRules` for `lscr.io/linuxserver/qbittorrent`, and the rules for `quay.io/argoproj/argocd` and `jellyfin/jellyfin`.
- `manifests/qbittorrent/deployment.yaml`, the image tag.
- Commit `871f661` on 2026-02-12 added the app pinned to `latest`. Commit `7251802` on 2026-08-31 replaced `latest` with `5.1.4-r2-ls440`, a build from 2026-02-08.
- The image labels read on 2026-10-21 give the build dates: `5.1.4-r2-ls440` is from 2026-02-08, and `5.3.0_v2.1.2-ls484` is from 2026-10-20.
- Renovate documentation on docker versioning: "Renovate treats the text after the first hyphen as a type of platform/compatibility indicator."
