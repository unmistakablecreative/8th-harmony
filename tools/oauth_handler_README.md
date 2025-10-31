# OAuth Handler - YouTube & Google Drive API Authentication

## Overview

`oauth_handler.py` is a CLI tool that manages OAuth2 authentication for YouTube Data API v3 and Google Drive API. It eliminates the need for manual token management in the Google Developer Console.

## Features

- ✅ **One-time browser authentication** - Authenticate once via browser
- ✅ **Automatic token refresh** - Tokens refresh automatically before expiry
- ✅ **Token status monitoring** - Check when tokens expire
- ✅ **Multi-scope support** - Manage YouTube and Drive tokens separately
- ✅ **CLI-only** - No execution_hub integration needed

## Setup

### Prerequisites

The OAuth client credentials must be configured in `/data/google_oauth.json`:

```json
{
  "installed": {
    "client_id": "YOUR_CLIENT_ID.apps.googleusercontent.com",
    "project_id": "your-project-id",
    "client_secret": "YOUR_CLIENT_SECRET",
    "redirect_uris": ["http://localhost"]
  }
}
```

### Token Storage

Tokens are automatically stored in `/data/oauth_credentials.json` with:
- Access tokens
- Refresh tokens
- Expiration timestamps
- Scope information

## Usage

### 1. Initial Authentication

Authenticate with both YouTube and Google Drive APIs:

```bash
python3 tools/oauth_handler.py auth --scopes youtube drive
```

Or authenticate with a specific scope:

```bash
python3 tools/oauth_handler.py auth --scopes youtube
```

**What happens:**
1. Opens browser to Google OAuth consent screen
2. You authorize the application
3. Callback server receives authorization code
4. Exchanges code for access + refresh tokens
5. Stores tokens in `/data/oauth_credentials.json`

### 2. Refresh Tokens

Refresh all expired tokens:

```bash
python3 tools/oauth_handler.py refresh
```

Refresh specific scope:

```bash
python3 tools/oauth_handler.py refresh --scope youtube
```

### 3. Get Valid Token

Get a valid access token (auto-refreshes if expired):

```bash
python3 tools/oauth_handler.py get_token --scope youtube
```

Returns the access token to stdout for use in API calls.

### 4. Check Status

View status of all stored tokens:

```bash
python3 tools/oauth_handler.py status
```

Example output:
```
🔐 OAuth Token Status

============================================================

📋 Scope: youtube
   Status: ✅ Valid
   Expires: 2025-10-28 18:30:45
   Time remaining: 2h 15m
   Has refresh token: ✅

📋 Scope: drive
   Status: ✅ Valid
   Expires: 2025-10-28 18:30:45
   Time remaining: 2h 15m
   Has refresh token: ✅

============================================================
```

## Integration with Other Tools

### Using in Python Scripts

```python
import subprocess
import json

# Get valid access token
result = subprocess.run(
    ["python3", "tools/oauth_handler.py", "get_token", "--scope", "youtube"],
    capture_output=True,
    text=True
)
access_token = result.stdout.strip()

# Use token in API requests
headers = {
    "Authorization": f"Bearer {access_token}",
    "Content-Type": "application/json"
}

# Make API call
import requests
response = requests.get(
    "https://www.googleapis.com/youtube/v3/channels",
    headers=headers,
    params={"part": "snippet", "mine": "true"}
)
```

### Using in Shell Scripts

```bash
#!/bin/bash

# Get valid YouTube token
TOKEN=$(python3 tools/oauth_handler.py get_token --scope youtube)

# Use in curl request
curl -H "Authorization: Bearer $TOKEN" \
     "https://www.googleapis.com/youtube/v3/channels?part=snippet&mine=true"
```

## Scopes

The handler supports two scopes:

| Scope Name | API | Full Scope URL |
|------------|-----|----------------|
| `youtube` | YouTube Data API v3 | `https://www.googleapis.com/auth/youtube` |
| `drive` | Google Drive API | `https://www.googleapis.com/auth/drive` |

## Token Lifecycle

1. **Initial Authentication**: User authorizes via browser, receives access + refresh token
2. **Token Usage**: Access token valid for ~1 hour
3. **Auto-Refresh**: Handler automatically refreshes tokens 5 minutes before expiry
4. **Refresh Token**: Stored permanently, used to get new access tokens without re-authentication

## Troubleshooting

### "No tokens found" error
Run initial authentication:
```bash
python3 tools/oauth_handler.py auth --scopes youtube drive
```

### "Invalid OAuth config" error
Check that `/data/google_oauth.json` exists and has valid client credentials.

### "Token expired" message
The handler will automatically refresh. If refresh fails:
```bash
python3 tools/oauth_handler.py refresh
```

If refresh token is invalid, re-run authentication:
```bash
python3 tools/oauth_handler.py auth --scopes youtube drive
```

### Browser doesn't open during auth
Manually visit the URL printed in the terminal.

## Security Notes

- **Never commit** `/data/oauth_credentials.json` to git
- **Never commit** `/data/google_oauth.json` to git
- Tokens are stored locally in plaintext - secure your filesystem
- The redirect URI must match what's configured in Google Developer Console
- Local callback server runs on port 8080 during authentication

## Dependencies

```bash
pip install requests
```

All other dependencies are Python standard library.

## Exit Codes

- `0`: Success
- `1`: Configuration error, authentication failure, or missing tokens

## Future Enhancements

Possible additions:
- Token encryption at rest
- Support for additional Google API scopes
- Token revocation command
- Multi-account support
- Automatic token refresh daemon
