<p align="center">
  <img src="images/logo.png" alt="Trail-Safe" width="160">
</p>

<h1 align="center">Trail-Safe GPS Tracker for Home Assistant</h1>

<p align="center">
  <a href="https://github.com/hacs/integration"><img src="https://img.shields.io/badge/HACS-Default-41BDF5.svg" alt="HACS"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-green.svg" alt="License"></a>
  <a href="https://trail-safe.app"><img src="https://img.shields.io/badge/Trail--Safe-trail--safe.app-2E7D32.svg" alt="Trail-Safe"></a>
</p>

A Home Assistant custom integration that brings live GPS positions from
[Trail-Safe](https://trail-safe.app) onto your Home Assistant map. Each
family member appears as a `device_tracker` entity with real-time
coordinates, accuracy, online state, and SOS alerts.

<p align="center">
  <img src="images/map-preview.png" alt="Trail-Safe trackers on the Home Assistant map" width="700">
</p>

## Features

- One `device_tracker` entity per family member (or single user)
- GPS coordinates with accuracy circle on the HA map
- Online/offline state with automatic icon changes
- SOS alert detection (icon switches to `mdi:alert`)
- Avatar support via `entity_picture`
- 30-second polling interval
- Config flow UI (no YAML needed)

## Requirements

| Requirement      | Value                                    |
|------------------|------------------------------------------|
| Home Assistant   | 2024.1.0 or later                        |
| Trail-Safe plan   | Single or Family (Free is not supported) |
| HACS             | Installed and running                    |

## Installation

### Via HACS (recommended)

1. Open **HACS** in your Home Assistant.
2. Go to **Integrations**.
3. Click **Explore & Download Repositories**.
4. Search for **Trail-Safe GPS Tracker**.
5. Click **Download**.
6. Restart Home Assistant.

### Manual

1. Download or clone this repository.
2. Copy the `custom_components/trailsafe/` folder into your Home
   Assistant `config/custom_components/` directory.
3. Restart Home Assistant.

## Configuration

### 1. Create an API key

1. Sign in to the [Trail-Safe dashboard](https://trail-safe.app).
2. Switch to the **Integrations** tab (requires a paid plan).
3. Click **Create key**, give it a name, and copy the token.
4. The token starts with `ts_` and is shown only once.

### 2. Add the integration

1. In Home Assistant, go to **Settings > Devices & Services**.
2. Click **Add Integration** and search for **Trail-Safe**.
3. Enter your **Server URL** (e.g. `https://trail-safe.app`).
4. Paste your **API Key**.
5. Click **Submit** — the integration validates the key and shows your
   plan and member count.

<p align="center">
  <img src="images/config-flow.png" alt="Trail-Safe integration setup dialog" width="450">
</p>

## Entities

A `device_tracker` entity is created **per device**. Because a Trail-Safe
member can carry several devices (a Family plan covers up to four devices,
which may all belong to one person), every device gets its own tracker.
All of a member's devices are grouped under a single Home Assistant device
named after that member, so a member with three watches shows up as one
device holding three trackers (e.g. *Sander – Watch*, *Sander – Phone*).

Members who haven't reported a live device fix yet appear as a single
fallback tracker keyed by their account, so nobody drops off the map.

Each entity exposes:

| Attribute          | Description                                      |
|--------------------|--------------------------------------------------|
| `latitude`         | Last-known latitude                              |
| `longitude`        | Last-known longitude                             |
| `gps_accuracy`     | Accuracy in meters                               |
| `source_type`      | Always `gps`                                     |
| `icon`             | `mdi:walk` (online), `mdi:account-clock` (offline), `mdi:alert` (SOS) |
| `entity_picture`   | Avatar URL (if uploaded in Trail-Safe)            |

### Extra state attributes

| Attribute      | Type    | Description                                 |
|----------------|---------|---------------------------------------------|
| `user_sub`     | string  | Google account subject identifier of the owner |
| `device_id`    | string  | Identifier of this specific device (per-device trackers only) |
| `device_name`  | string  | This device's name from Trail-Safe           |
| `online`       | boolean | True when this device has an active connection |
| `sos`          | boolean | True when the owner is signalling SOS       |
| `recorded_at`  | integer | Unix milliseconds of the last GPS fix       |

> **Upgrading from 1.0.x:** entities are now keyed per device. A member
> with a live device fix moves from `device_tracker.trailsafe_<user_sub>`
> to `device_tracker.trailsafe_<device_id>`. Update any dashboards or
> automations that referenced the old per-user entity IDs.

## Showing trackers on the map

Because every entity is a `device_tracker` with `source_type: gps` and
live `latitude`/`longitude`, Home Assistant places it on the map
automatically — no extra configuration is required.

### Default map

The built-in **Map** panel (left sidebar) shows every entity that has a
location, including your Trail-Safe trackers. Each member appears with an
accuracy circle and, if an avatar was uploaded in Trail-Safe, their photo
as the marker.

<p align="center">
  <img src="images/map-card.png" alt="Trail-Safe map card on a dashboard" width="700">
</p>

### Map card on a dashboard

To add the trackers to a specific dashboard:

1. Open the dashboard and click **Edit Dashboard** (top-right).
2. Click **+ Add Card** and choose **Map**.
3. Under **Entities**, add your Trail-Safe trackers, e.g.
   `device_tracker.trailsafe_116658255524685545000`.
4. Click **Save**.

Or paste the YAML directly:

```yaml
type: map
title: Trail-Safe
default_zoom: 12
hours_to_show: 6
entities:
  - device_tracker.trailsafe_116658255524685545000
  - device_tracker.trailsafe_103847562918374650000
```

> **Tip:** Set `hours_to_show` to draw a recent location history trail
> for each member. Use `default_zoom` to frame your usual area.

### Not seeing a marker?

- The entity must have a GPS fix — if `latitude`/`longitude` are
  `unknown`, the watch hasn't reported a position yet.
- Confirm the entity isn't hidden under
  **Settings > Devices & Services > Entities**.

## Example automations

### Alert when a hiker goes offline

```yaml
automation:
  - alias: "Hiker offline alert"
    trigger:
      - platform: state
        entity_id: device_tracker.trailsafe_116658255524685545000
        to: "not_home"
        for: "00:05:00"
    action:
      - service: notify.mobile_app
        data:
          title: "Trail-Safe"
          message: >
            {{ state_attr('device_tracker.trailsafe_116658255524685545000',
               'friendly_name') }} went offline 5 minutes ago.
```

### SOS notification

```yaml
automation:
  - alias: "SOS alert"
    trigger:
      - platform: state
        entity_id: device_tracker.trailsafe_116658255524685545000
        attribute: sos
        to: true
    action:
      - service: notify.all_phones
        data:
          title: "SOS from Trail-Safe"
          message: "Emergency signal received. Check the map."
```

## Troubleshooting

| Problem                         | Solution                                     |
|---------------------------------|----------------------------------------------|
| Integration not found in search | Restart HA after installation                |
| "Invalid API key" during setup  | Re-copy the key; check for trailing spaces   |
| "Paid plan required"            | Your subscription lapsed; check Billing page |
| Entities show `unknown`         | Watches haven't sent a fix yet; wait for GPS |
| Stale positions                 | Check watch app connectivity                 |

## Security

- API keys are hashed (SHA-256) server-side. The raw token is never
  stored.
- Keys grant **read-only** access to position data only.
- Revoking a key takes effect immediately.

## License

MIT
