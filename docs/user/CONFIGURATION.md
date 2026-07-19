# Configuration

Create an API key in the Nutri Points web application, then provide:

- **Base URL:** full `http://` or `https://` server origin with no path, query, or fragment.
- **API key:** a current Nutri Points API key.
- **Poll interval:** 15–3600 seconds; default 60.
- **Low points threshold:** 0–50 points; default 5.
- **Verify TLS:** keep enabled unless the server intentionally uses a trusted local/self-signed setup.

Options can change the server URL, poll interval, low-points threshold, and TLS verification. Leave the replacement API-key field blank to retain the stored key.

If Nutri Points rejects the host or API-key network, update its `TRUSTED_HOSTS` or `API_KEY_HTTP_ALLOWED_CIDRS` configuration respectively.
