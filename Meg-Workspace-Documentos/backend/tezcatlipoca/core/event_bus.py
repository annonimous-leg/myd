from __future__ import annotations
import asyncio, json, os, time
from collections import defaultdict
from typing import Awaitable, Callable
Handler = Callable[[dict], Awaitable[None] | None]
class EventBus:
    """Durable Redis Streams event bus in production; in-process only in explicit development."""
    def __init__(self, redis_url: str|None=None, require_durable: bool|None=None):
        self.redis_url=redis_url or os.getenv("REDIS_URL"); env=os.getenv("ENVIRONMENT","development").lower()
        self.require_durable=(env=="production") if require_durable is None else require_durable
        if self.require_durable and not self.redis_url: raise RuntimeError("REDIS_URL obligatorio para EventBus en producción")
        self._handlers=defaultdict(list); self._redis=None; self._initialized=False
    async def _client(self):
        if not self.redis_url: return None
        if self._redis is None:
            try: from redis import asyncio as redis_async
            except ImportError as exc: raise RuntimeError("redis-py oficial requerido para EventBus") from exc
            self._redis=redis_async.from_url(self.redis_url, decode_responses=True)
        if not self._initialized: await self._redis.ping(); self._initialized=True
        return self._redis
    def subscribe(self, topic: str, handler: Handler)->None: self._handlers[topic].append(handler)
    async def publish(self, topic: str, payload: dict)->str:
        client=await self._client(); event={"topic":topic,"payload":json.dumps(payload,ensure_ascii=False,default=str),"published_at":str(time.time())}
        if client is None:
            if self.require_durable: raise RuntimeError("EventBus durable no disponible")
            event_id=f"local-{time.time_ns()}"
        else: event_id=await client.xadd(f"megalodon:events:{topic}",event,maxlen=100000,approximate=True)
        for handler in list(self._handlers.get(topic, [])):
            r=handler(payload)
            if asyncio.iscoroutine(r): await r
        return str(event_id)
    async def create_group(self,topic:str,group:str,start_id:str="0-0"):
        client=await self._client();
        if client is None:
            if self.require_durable: raise RuntimeError("EventBus durable requerido")
            return
        try: await client.xgroup_create(f"megalodon:events:{topic}",group,id=start_id,mkstream=True)
        except Exception as exc:
            if "BUSYGROUP" not in str(exc): raise
    async def consume_once(self,topic:str,group:str,consumer:str,count:int=10,block_ms:int=1000):
        client=await self._client();
        if client is None:
            if self.require_durable: raise RuntimeError("EventBus durable requerido")
            return []
        return await client.xreadgroup(group,consumer,{f"megalodon:events:{topic}":">"},count=count,block=block_ms)
    async def ack(self,topic:str,group:str,event_id:str)->int:
        client=await self._client();
        if client is None:
            if self.require_durable: raise RuntimeError("EventBus durable requerido")
            return 0
        return int(await client.xack(f"megalodon:events:{topic}",group,event_id))
    async def dead_letter(self,topic:str,event_id:str,reason:str,payload:dict)->str:
        client=await self._client();
        if client is None:
            if self.require_durable: raise RuntimeError("EventBus durable requerido")
            return f"local-dlq-{time.time_ns()}"
        return str(await client.xadd(f"megalodon:events:dlq:{topic}",{"event_id":event_id,"reason":reason,"payload":json.dumps(payload,default=str)},maxlen=100000,approximate=True))
    async def close(self):
        if self._redis is not None: await self._redis.aclose(); self._redis=None; self._initialized=False
