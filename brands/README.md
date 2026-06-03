# Home Assistant brand assets

These icons are **not** used by this integration directly. Home Assistant
fetches integration logos from the central
[`home-assistant/brands`](https://github.com/home-assistant/brands) repo
via `https://brands.home-assistant.io/<domain>/...`. Until the icon is
registered there, HA shows a white-square placeholder in
**Settings → Devices & Services**.

## Files

| File         | Size    | Brands requirement                  |
|--------------|---------|-------------------------------------|
| `icon.png`   | 256×256 | square, transparent, trimmed        |
| `icon@2x.png`| 512×512 | exactly 2× of `icon.png`            |

(A wide `logo.png` / `logo@2x.png` is optional — HA falls back to the icon
when no logo is registered.)

## How to publish

1. Fork <https://github.com/home-assistant/brands>.
2. Copy these two files into the fork at:
   ```
   custom_integrations/trailsafe/icon.png
   custom_integrations/trailsafe/icon@2x.png
   ```
   The folder name **must** equal this integration's manifest `domain`
   (`trailsafe`).
3. Open a PR titled `Add Trail-Safe (trailsafe)`.
4. After merge + CDN refresh, restart Home Assistant — the Trail-Safe
   icon replaces the white square for all users.

Source: generated (trimmed + resized) from the Trail-Safe app icon.
