# Error Notes Archive

Historical notes moved from the old root `code_erreur.txt`.

## ERREUR 101

- File: `utils/request_manager.py`
- Old line reference: `82`
- Cause: do not call `await interaction.response.defer(ephemeral=True)` directly
  inside cogs when the request manager already handles deferring.

## ERREUR 001

- File: `cogs/moderation/moderation.py`
- Old line reference: `172`

## Unknown Webhook

`discord.errors.NotFound: 404 Not Found (error code: 10015): Unknown Webhook`

This usually happens when the bot attempts to use `followup.send` without a
valid initial interaction response.
