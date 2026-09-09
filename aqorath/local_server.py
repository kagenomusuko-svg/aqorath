"""Local launcher for the AQR-005 browser surface."""

LOCAL_HOST = "127.0.0.1"
DEFAULT_PORT = 8765


def run_local_surface(port=DEFAULT_PORT):
    """Run Aqorath only on IPv4 loopback; remote binding is not configurable."""
    if type(port) is not int or isinstance(port, bool):
        raise TypeError("port must be int")
    if not 1 <= port <= 65535:
        raise ValueError("port must be between 1 and 65535")
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
