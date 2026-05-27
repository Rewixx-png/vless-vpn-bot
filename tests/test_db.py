import asyncio
from database.repo.system import SystemRepo

async def main():
    val = await SystemRepo.get_config("collector_last_run")
    print("collector_last_run:", val)

if __name__ == "__main__":
    asyncio.run(main())
