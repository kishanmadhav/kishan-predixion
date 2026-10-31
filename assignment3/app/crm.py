"""CRM client and outbox delivery."""
import asyncio
import logging

import httpx

from .storage import Store

log = logging.getLogger("crm")


class CrmClient:
    def __init__(self, url: str, token: str, transport: httpx.AsyncBaseTransport | None = None):
        self._url = url
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(5.0),          # never wait forever on a sick CRM
            headers={"Authorization": f"Bearer {token}"},
            transport=transport,
        )

    async def schedule(self, account_id: str, next_call_at: str) -> None:
        r = await self._client.post(self._url, json={"account_id": account_id, "next_call": next_call_at})
        r.raise_for_status()

    async def aclose(self) -> None:
        await self._client.aclose()


async def flush_outbox(store: Store, crm: CrmClient) -> int:
    """Deliver pending notifications once. Failures stay PENDING for the next sweep.

    Returns the number delivered. Sqlite calls run in a thread so the event loop is never blocked.
    """
    sent = 0
    for outbox_id, account_id, next_call_at in await asyncio.to_thread(store.pending):
        try:
            await crm.schedule(account_id, next_call_at)
        except httpx.HTTPError as e:
            log.warning("crm delivery failed", extra={"outbox_id": outbox_id, "error": repr(e)})
            await asyncio.to_thread(store.mark_failed, outbox_id, repr(e))
            break                                # CRM is likely down; stop hammering it this sweep
        await asyncio.to_thread(store.mark_sent, outbox_id)
        sent += 1
    return sent
