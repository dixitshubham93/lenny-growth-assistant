import asyncio
from app.db.engine import get_engine
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app.db.models import Message

async def run():
    engine = get_engine()
    async with AsyncSession(engine) as db:
        res = await db.execute(select(Message).limit(10))
        for msg in res.scalars().all():
            print(f"Role: {msg.role}, Sources: {msg.sources}")

asyncio.run(run())
