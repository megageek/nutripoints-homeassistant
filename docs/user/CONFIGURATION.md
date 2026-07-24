# Configuration

Create an API key in the Nutri Points web application, then provide:

- **Base URL:** full `http://` or `https://` server origin with no path, query, or fragment.
- **API key:** a current Nutri Points API key.
- **Verify TLS:** keep enabled unless the server intentionally uses a trusted local/self-signed setup.

After setup:

- **Reconfigure** changes the base URL and TLS verification after validating the new connection.
- **Reconfigure authentication** replaces an expired or revoked API key.
- **Options** changes the poll interval (15–3600 seconds, default 60) and low-points threshold (0–50, default 5).

The integration polls as a fallback and requests immediate refreshes from the authenticated
event stream. Polling and streaming health are tracked independently. If Nutri Points
rejects the host or API-key network, update its `TRUSTED_HOSTS` or
`API_KEY_HTTP_ALLOWED_CIDRS` configuration respectively.

Download diagnostics from **Settings → Devices & services → Nutri Points** when
troubleshooting. Diagnostics include connection and contract health but redact the API key
and omit nutrition, weight, and drink state.
