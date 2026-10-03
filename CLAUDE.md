# Agent instructions: PaceGuard Home Assistant integration

Custom integration `trailsafe` (HACS): one `device_tracker` per PaceGuard
device, polled from the PaceGuard backend with a user API key.

## Where things live
- **This repo is the source of truth**: `custom_components/trailsafe/`.
  - Remote `origin` = GitLab `git.2552.nl/2555/trailsafe-homeassistant`.
  - Remote `github` = `github.com/JackEsBauer/trailsafe-homeassistant`.
    HACS installs from **GitHub releases**, so that is what users get.
- `/docker/trailsafe/integrations/ha/` in the backend repo is an old copy
  (v1.1.0). Don't edit it. If it's kept at all, sync it from here.
- Backend code: `/docker/trailsafe` (Go). The integration endpoints live in
  `internal/app/app.go` (`makeIntegrationPositionsHandler`) and
  `internal/apikeys/`.

## Backend contract
`GET {server}/api/integration/positions` with `Authorization: Bearer <api key>`.
API keys are created in the dashboard (`ts_…`) and only for paid plans.

| Status | Meaning | Integration must… |
|---|---|---|
| 200 | `{"plan": "...", "positions": [...]}` | update entities |
| 401 | key invalid or revoked | raise `ConfigEntryAuthFailed` → reauth flow |
| 403 | key owner is no longer on a paid plan | `UpdateFailed` + a repair issue (not reauth) |
| 429 / 5xx / network | transient (deploys briefly give 503) | `UpdateFailed`, retry next poll |

Each position: `user_sub, display_name, device_id, device_name, lat, lng,
accuracy, recorded_at (ms), online, sos, avatar_url`.
- `device_id == "user:<sub>"` is the per-user fallback row → key it by
  `user_sub` (legacy entity identity).
- A device can disappear from the feed (removed, merged into another device,
  re-linked with a new id). Its entity must go **unavailable**, not freeze on
  the last fix, and the user must be able to delete it.
- `avatar_url` (`/api/users/{sub}/avatar`) currently needs a **JWT**, so it
  answers 401 with an API key, and the browser can't load it either. Don't
  set `entity_picture` until the backend accepts the API key there (open
  backend item).

## Rules
- **Never change `unique_id`s** (`trailsafe_<device_id or user_sub>`) or the
  config-entry unique id (`api_key[:16]`): existing installs would lose their
  entities and history. Generated `entity_id`s only apply to NEW entities.
- Use the HA APIs current for the minimum version in `hacs.json`, not the
  deprecated aliases:
  - `from homeassistant.components.device_tracker import TrackerEntity`
    (the `.config_entry` alias is removed in 2027.6)
  - pass `config_entry=` to `DataUpdateCoordinator`
  - `entry.runtime_data`
  - `async_get_clientsession(hass)`, never a new `aiohttp.ClientSession`
- No blocking I/O in the event loop. No new requirements unless unavoidable.
- Every user-facing string goes into `strings.json` AND
  `translations/en.json` (keep them identical).
- Version: bump `manifest.json` `version` for every release (semver).

## Test before every release (real HA, not just py_compile)
Run a throwaway HA of the version users run, against the **dev** backend:

```sh
S=/tmp/hatest; rm -rf $S; mkdir -p $S/config/custom_components
cp -r custom_components/trailsafe $S/config/custom_components/
printf 'default_config:\nlogger:\n  default: warning\n  logs:\n    custom_components.trailsafe: debug\n' > $S/config/configuration.yaml
docker run -d --name hatest -v $S/config:/config -p 127.0.0.1:18123:8123 \
  --add-host=host.docker.internal:host-gateway ghcr.io/home-assistant/home-assistant:<version>
```

- Onboard through the REST API:
  1. `POST /api/onboarding/users` → `auth_code`
  2. `POST /auth/token` → access token
- Add the entry:
  1. `POST /api/config/config_entries/flow {"handler":"trailsafe"}`
  2. Submit `server_url=http://host.docker.internal:8082` and a dev API key.
- **Getting a dev API key:** mint an owner JWT; the recipe is in the backend
  memory "Backend build gotcha". Then
  `POST localhost:8082/api/me/api-keys {"name":"ha-test"}`. Revoke it
  afterwards with `DELETE /api/me/api-keys/{id}`.

Check all of these:
- [ ] `GET /api/states`: trackers have coordinates.
- [ ] Logs show no errors and no deprecation warnings from `trailsafe`.
- [ ] **Reauth:** revoke the key → next poll → the entry shows "Reauthentication
  required" → submitting a new key fixes it without losing entities.
- [ ] **Upgrade path:** install the previous release first, then the new one.
  Entity ids and unique ids must be unchanged.
- [ ] `docker rm -f hatest` afterwards.

## Release
1. Bump `manifest.json` `version` and update the README changelog/features.
2. Commit on a branch → GitLab MR on `origin`. No Claude attribution lines in
   commits.
3. After merge: tag `vX.Y.Z`, push the branch and tag to `github`, and create a
   GitHub release `vX.Y.Z`. HACS picks it up from there.
   **Ask the user before pushing to GitHub**: it is public.

## Known open items
- Avatars: the backend should accept the integration API key on the avatar
  route, or the integration should proxy the avatar.
- Possible extra entities: battery / speed / online as sensors, if the feed
  starts carrying them (the backend has them per frame, but not in this feed).
