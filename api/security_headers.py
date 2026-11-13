"""Browser protection headers sent with every response (see ``add_security_headers`` in api.main).

The Content-Security-Policy lists exactly what the frontend loads: its own scripts and styles,
inline styles (the UI uses ``style={{...}}`` and react-hot-toast injects a <style> tag), and card
images / mana symbols from Scryfall's CDNs. Adding a new external origin to the frontend means
adding it here.
"""

CONTENT_SECURITY_POLICY = "; ".join(
    (
        "default-src 'self'",
        "script-src 'self'",
        "style-src 'self' 'unsafe-inline'",
        "img-src 'self' data: blob: https://cards.scryfall.io https://svgs.scryfall.io",
        "font-src 'self' data:",
        "connect-src 'self'",
        "frame-ancestors 'none'",
        "base-uri 'self'",
        "form-action 'self'",
        "object-src 'none'",
    )
)

# FastAPI's interactive docs (local only, see api.config.docs_kwargs) load scripts from a CDN.
CSP_EXEMPT_PATHS = frozenset({"/docs", "/redoc"})

CSP_HEADER = "Content-Security-Policy"
CSP_REPORT_ONLY_HEADER = "Content-Security-Policy-Report-Only"


def security_headers(*, deployed: bool, report_only: bool = False) -> dict[str, str]:
    """Headers for every response. HSTS only when deployed (plain-http localhost must keep working).

    ``report_only`` sends the policy as Content-Security-Policy-Report-Only: the browser logs
    violations to its console but blocks nothing.
    """
    headers = {
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        # Also keeps upload / event-edit link tokens out of Referer headers sent to other sites.
        "Referrer-Policy": "no-referrer",
        CSP_REPORT_ONLY_HEADER if report_only else CSP_HEADER: CONTENT_SECURITY_POLICY,
    }
    if deployed:
        headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return headers
