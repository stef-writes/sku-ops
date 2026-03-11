"""Background scheduled tasks.

Currently contains the nightly Xero sync loop. Add new recurring jobs here.
"""

import asyncio
import logging
from datetime import UTC, datetime

from finance.application.xero_sync_job import run_sync
from identity.infrastructure.org_repo import list_all
from shared.infrastructure.config import XERO_SYNC_HOUR
from shared.infrastructure.logging_config import org_id_var

logger = logging.getLogger(__name__)


async def _get_active_org_ids() -> list[str]:
    """Return org IDs that should run scheduled jobs."""
    orgs = await list_all()
    return [o.id for o in orgs] if orgs else ["default"]


async def xero_sync_loop() -> None:
    """Run the Xero sync job once per day at XERO_SYNC_HOUR UTC.

    Wakes up every minute, checks whether the target hour has arrived, and
    fires run_sync for each active org exactly once per calendar day.
    """
    last_run_date = None
    logger.info("Xero nightly sync scheduler started (fires at %02d:00 UTC)", XERO_SYNC_HOUR)
    while True:
        try:
            await asyncio.sleep(60)
            now = datetime.now(UTC)
            if now.hour == XERO_SYNC_HOUR and now.date() != last_run_date:
                last_run_date = now.date()
                org_ids = await _get_active_org_ids()
                for oid in org_ids:
                    token = org_id_var.set(oid)
                    try:
                        logger.info("Xero nightly sync starting for org '%s'", oid)
                        summary = await run_sync()
                        logger.info(
                            "Xero nightly sync complete for org '%s': %s",
                            oid,
                            {k: v for k, v in summary.items() if k != "errors"},
                        )
                        if summary.get("errors"):
                            logger.warning(
                                "Xero nightly sync for org '%s' had %d error(s): %s",
                                oid,
                                len(summary["errors"]),
                                summary["errors"],
                            )
                    except Exception:
                        logger.exception("Xero nightly sync failed for org '%s'", oid)
                    finally:
                        org_id_var.reset(token)
        except asyncio.CancelledError:
            logger.info("Xero nightly sync scheduler stopped")
            return
        except Exception:
            logger.exception("Unexpected error in Xero sync loop")
