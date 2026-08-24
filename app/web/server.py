def get_downloads_dir() -> Path:
    if os.getenv("VERCEL") or os.getenv("AWS_LAMBDA_FUNCTION_NAME"):
        d = Path(tempfile.gettempdir()) / "telegram_downloads"
        d.mkdir(exist_ok=True)
        return d

    try:
        d = Path("downloads")
        d.mkdir(exist_ok=True)
        test_file = d / ".write_test"
        test_file.touch()
        test_file.unlink(missing_ok=True)
        return d
    except (OSError, PermissionError):
        d = Path(tempfile.gettempdir()) / "telegram_downloads"
        d.mkdir(exist_ok=True)
        return d
