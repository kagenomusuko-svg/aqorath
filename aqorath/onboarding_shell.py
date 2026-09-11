"""AQR-015 discoverability decoration for the canonical local browser shell."""

from . import web_assets


_ONBOARDING_LINK = (
    '<a id="aqorath-onboarding-link" href="/onboarding" '
    'style="position:fixed;right:18px;bottom:66px;z-index:9999;padding:10px 14px;'
    'border-radius:10px;background:#fff;color:#173f3a;text-decoration:none;'
    'border:1px solid #b7c9c5;box-shadow:0 4px 16px rgba(0,0,0,.12);'
    'font:600 14px system-ui">Configuración</a>'
)

if "aqorath-onboarding-link" not in web_assets.APP_HTML:
    web_assets.APP_HTML = web_assets.APP_HTML.replace(
        "</body>", f"{_ONBOARDING_LINK}</body>"
    )


__all__ = []
