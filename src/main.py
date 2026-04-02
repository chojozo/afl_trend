from src.collector import run


if __name__ == "__main__":
    try:
        raise SystemExit(run())
    except Exception as exc:
        print(f"[ERROR] {exc}")
        raise
