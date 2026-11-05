"""Run one registry-selected API with a workspace-local graceful shutdown marker."""

import argparse
import json
from pathlib import Path

import uvicorn


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--code", required=True)
    args = parser.parse_args()
    win_root = Path(__file__).resolve().parent
    registry = json.loads((win_root / "conf/services.json").read_text(encoding="utf-8-sig"))
    service = next(item for item in registry["services"] if item["code"] == args.code)
    stop_path = win_root / "runtime" / (service["code"] + ".stop")

    class ManagedServer(uvicorn.Server):
        async def on_tick(self, counter: int) -> bool:
            if stop_path.exists():
                self.should_exit = True
            return await super().on_tick(counter)

    ManagedServer(uvicorn.Config(
        service["module"], factory=service.get("factory", True),
        host="127.0.0.1", port=service["port"], timeout_graceful_shutdown=10,
    )).run()


if __name__ == "__main__":
    main()
