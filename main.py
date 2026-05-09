from __future__ import annotations

import logging
import sys
import traceback
from datetime import date

from agent.collect_agent import CollectAgent
from service.gmail_sender import GmailSender
from service.obsidian_writer import ObsidianWriter


def main() -> None:
    logging.basicConfig(
        stream=sys.stdout,
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    logger = logging.getLogger(__name__)

    run_date = date.today()
    logger.info("=== AI Tips Collector 開始 (date=%s) ===", run_date)

    try:
        agent = CollectAgent()
        result = agent.graph.invoke({"run_date": run_date})
        final_report: str = result["final_report"]

        writer = ObsidianWriter()
        path = writer.write(final_report, run_date)
        logger.info("Obsidianファイル保存完了: %s", path)

        sender = GmailSender()
        sender.send(final_report, run_date)

    except Exception:
        traceback.print_exc()
        sys.exit(1)

    logger.info("=== AI Tips Collector 完了 ===")


if __name__ == "__main__":
    main()
