# Manual Checks

These scripts call real external APIs and are not part of CI.

- `check_valorant_integrations.py` requires `HENRIK_VALO_KEY`.
- `check_twitch_integration.py` requires `TWITCH_CLIENT_ID` and `TWITCH_CLIENT_SECRET`.

Run them only when you need to validate live integration credentials or vendor
API behavior.
