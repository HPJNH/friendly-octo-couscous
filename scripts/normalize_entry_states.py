from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app import create_app
from app.rebuild_engine import normalize_existing_entries


def main() -> None:
    app = create_app()
    with app.app_context():
        summary = normalize_existing_entries(write_reports=True)
        print("状态归一化已完成")
        for key, value in summary.items():
            print(f"{key}: {value}")


if __name__ == "__main__":
    main()
