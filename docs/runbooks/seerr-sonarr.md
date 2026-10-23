# Seerr, Sonarr and Jellyfin Enhanced

Seerr takes media requests from Jellyfin users. Sonarr finds the series and hands the download to qBittorrent. Jellyfin Enhanced adds the request screens to the Jellyfin web UI. This file says how the parts connect, how to set them up and how to check them.

| Part | Address | Public route |
|---|---|---|
| Seerr | `https://requests.hedgehog-wage.ts.net` | none |
| Sonarr | `https://sonarr.hedgehog-wage.ts.net` | none |
| qBittorrent | `https://qbittorrent.hedgehog-wage.ts.net` | none |
| Jellyfin | `https://jelly.yornik.eu` | yes, as before |

## How the parts connect

```text
Jellyfin Enhanced (in Jellyfin) -> Seerr -> Sonarr -> qBittorrent (behind Mullvad)
                                                 \-> /media/series -> Jellyfin
```

All calls between the parts stay in the `jellyfin` namespace.

| From | To | Address in the cluster |
|---|---|---|
| Jellyfin Enhanced | Seerr | `http://seerr:5055` |
| Seerr | Jellyfin | `http://jellyfin:8096` |
| Seerr | Sonarr | `http://sonarr:8989` |
| Sonarr | qBittorrent | `http://qbittorrent:8080` |

Jellyfin stays on its public address. Jellyfin Enhanced calls Seerr from the Jellyfin server, not from the browser. A user without the tailnet can request media in the Jellyfin web UI. Only the links that open the Seerr UI need the tailnet.

NOTE: Seerr has no download client. It sends a request to Sonarr or Radarr, and that program picks the client. This setup has Sonarr, so a request for a series works. A request for a film has no target. See [Films](#films).

## What the repository sets

- `manifests/seerr/` and `manifests/sonarr/` run in the `jellyfin` namespace, next to Jellyfin and qBittorrent.
- Sonarr mounts the `qbittorrent-series-rw` volume at `/media/series`, the same path as qBittorrent. A download needs no remote path mapping.
- Sonarr forces its login on for every address. Without this setting, Sonarr skips the login for a pod address, and the Tailscale proxy connects from one.
- Jellyfin is unchanged.

## How to activate the 2 new tailnet devices

Follow [`tailnet-only-admin-uis.md`](tailnet-only-admin-uis.md#after-the-merge). Sign the devices `requests` and `sonarr`.

WARNING: Each address is unreachable until you sign its device. The 2 Applications still sync in the meantime.

## How to set up Seerr

1. Open `https://requests.hedgehog-wage.ts.net`.
2. Choose Jellyfin as the media server.
3. Enter `http://jellyfin:8096` and sign in as a Jellyfin administrator.
4. Enable the Jellyfin libraries for series and films.
5. Open Settings, then Network, and turn on Enable Proxy Support.
6. Open Settings, then Users, and turn on Enable Jellyfin Sign-In.
7. Import the Jellyfin users.

WARNING: The first visitor to a new Seerr completes the setup wizard and becomes the administrator. Do steps 1 to 4 before you tell anyone the address.

Each person who requests media needs a Seerr account that links to the Jellyfin user.

## How to set up qBittorrent

Do this once. qBittorrent keeps its categories in its own config, not in git.

1. Open the qBittorrent WebUI.
2. Add a category named `tv`.
3. Set the save path of `tv` to `/media/series/downloads/`.

Expected result: a finished download of category `tv` sits under `/media/series/downloads/`. The Sonarr init container creates that folder and puts an empty `.ignore` file in it, so Jellyfin does not scan it as a library folder.

## How to set up Sonarr

1. Open `https://sonarr.hedgehog-wage.ts.net`.
2. Create the administrator account.
3. Open Settings, then Media Management, and add the root folder `/media/series`.
4. Open Settings, then Download Clients, and add qBittorrent.
5. Enter host `qbittorrent`, port `8080` and the WebUI user and password of qBittorrent.
6. Enter category `tv`.
7. Open Settings, then Indexers, and add your indexers.
8. Open Settings, then General, and copy the API key.

NOTE: Sonarr needs an indexer to find a release. Without one, a request stays open.

## How to connect Seerr to Sonarr

1. In Seerr, open Settings, then Services, and add a Sonarr server.
2. Enter host `sonarr`, port `8989` and the API key from Sonarr.
3. Choose the root folder `/media/series` and a quality profile.
4. Turn on Enable Automatic Search.
5. Press Test, then Save.

## How to install Jellyfin Enhanced

Jellyfin Enhanced works with Jellyfin 10.11 and 12.x.

1. In Jellyfin, open Dashboard, then Plugins, then Repositories.
2. Add the repository `https://raw.githubusercontent.com/n00bcodr/jellyfin-plugins/main/manifest.json`.
3. Open the Catalog, choose Jellyfin Enhanced and install it.
4. Restart Jellyfin. A browser refresh does not load the plugin.
5. Open Dashboard, then Plugins, then Jellyfin Enhanced, then Seerr.
6. Turn on Enable Seerr integration.
7. Enter `http://seerr:5055` as the Seerr URL.
8. Enter the API key from Seerr, Settings, General.
9. Press Test, then Save Settings.
10. Under Advanced URL Mappings, map `http://seerr:5055` to `https://requests.hedgehog-wage.ts.net`.

Expected result: the Jellyfin web UI shows a request button on titles that are not in the library. The mapping in step 10 makes the links that open Seerr use an address a browser can reach.

NOTE: The plugin stores its settings in the Jellyfin config volume. A restore of that volume brings them back. The plugin itself is not in git.

CAUTION: The plugin changes the Jellyfin web UI. If Jellyfin does not start after step 4, remove the Jellyfin Enhanced folder from `/config/plugins` on the Jellyfin config volume and start Jellyfin again.

## Films

Seerr cannot send a film request to qBittorrent. To fulfil film requests, add Radarr in the same way as Sonarr. Mount `qbittorrent-movies-rw` at `/media/movies`, give it a tailnet Ingress, and add it to Seerr under Services.

## How to check

1. Check that the pods run:

   ```sh
   kubectl -n jellyfin get pods -l 'app in (seerr,sonarr)'
   ```

2. Check that Seerr answers:

   ```sh
   curl -sS https://requests.hedgehog-wage.ts.net/api/v1/status
   ```

3. Check that Sonarr asks for a login. The command must return a redirect or a 401, not the Sonarr page:

   ```sh
   curl -sSI https://sonarr.hedgehog-wage.ts.net/api/v3/system/status
   ```

## How to undo

WARNING: ArgoCD deletes `seerr-config-ssd` and `sonarr-config-ssd` with the Applications. They hold the settings and the SQLite database of each program. Copy the files out of the volumes first if you want to keep them.

1. Remove the `seerr` and `sonarr` entries from `apps/values.yaml`.
2. Merge the change. ArgoCD prunes both Applications.
3. Remove the 2 devices from the Tailscale admin console.

The `qbittorrent-series-rw` volume stays. The `qbittorrent` Application owns it.
