"""Small runtime hook for provider overrides that must load before main.py."""
try:
    import market_service
    from realtime_korea import install_patch

    install_patch(market_service)
    print("[SiteCustomize] realtime Korea patch installed")
except Exception as exc:
    # Never block app startup; existing Yahoo providers remain the fallback.
    print(f"[SiteCustomize] realtime Korea patch skipped: {type(exc).__name__}: {exc}")
