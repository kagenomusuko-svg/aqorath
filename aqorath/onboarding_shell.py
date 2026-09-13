"""AQR-015 discoverability decoration for the canonical local browser shell."""

from . import web_assets


_LINKS = (
    ("aqorath-onboarding-link", "/onboarding", "Configuración", 66),
    ("aqorath-fixed-assets-link", "/fixed-assets", "Activos fijos", 114),
    ("aqorath-periods-link", "/periods", "Períodos", 162),
    ("aqorath-programs-link", "/programs", "Programas", 210),
)

for element_id, href, label, bottom in _LINKS:
    if element_id in web_assets.APP_HTML:
        continue
    link = (
        f'<a id="{element_id}" href="{href}" '
        f'style="position:fixed;right:18px;bottom:{bottom}px;z-index:9999;padding:10px 14px;'
        'border-radius:10px;background:#fff;color:#173f3a;text-decoration:none;'
        'border:1px solid #b7c9c5;box-shadow:0 4px 16px rgba(0,0,0,.12);'
        f'font:600 14px system-ui">{label}</a>'
    )
    web_assets.APP_HTML = web_assets.APP_HTML.replace("</body>", f"{link}</body>")


__all__ = []
