"""Local launcher for the Aqorath browser surface."""

LOCAL_HOST = "127.0.0.1"
DEFAULT_PORT = 8765


def run_local_surface(port=DEFAULT_PORT):
    """Run Aqorath only on IPv4 loopback; remote binding is not configurable."""
    if type(port) is not int or isinstance(port, bool):
        raise TypeError("port must be int")
    if not 1 <= port <= 65535:
        raise ValueError("port must be between 1 and 65535")

    # Decorate the common shell before web_surface is materialized.
    from . import onboarding_shell as _onboarding_shell  # noqa: F401
    # Importing recovery_web registers AQR-014 routes on the canonical web_surface app.
    # aqorath.recovery_web:app is therefore an alias, not a second local surface.
    from . import recovery_web as _recovery_web  # noqa: F401
    # AQR-015 onboarding routes extend that same canonical FastAPI app.
    from . import onboarding_web as _onboarding_web  # noqa: F401
    import uvicorn

    uvicorn.run(
        "aqorath.web_surface:app",
        host=LOCAL_HOST,
        port=port,
        log_level="info",
    )


if __name__ == "__main__":
    run_local_surface()


__all__ = ["LOCAL_HOST", "DEFAULT_PORT", "run_local_surface"]
