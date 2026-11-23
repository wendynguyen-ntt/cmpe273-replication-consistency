import asyncio
from contextlib import suppress
from dataclasses import dataclass


@dataclass
class Replica:
    name: str
    stock: int = 0


class InventorySystem:
    def __init__(self):
        self.primary = Replica("Primary")
        self.secondary = Replica("Secondary")
        self.pending = asyncio.Queue()
        self.replication_enabled = asyncio.Event()
        self.replication_enabled.set()

    def write_primary(self, stock):
        self.primary.stock = stock
        self.pending.put_nowait(stock)
        print(f"WRITE Primary: stock={stock}; update queued for Secondary")

    def read(self, replica):
        """Client reads the selected replica's own inventory value."""
        print(f"READ {replica.name}: stock={replica.stock}")
        return replica.stock

    def pause_replication(self):
        self.replication_enabled.clear()
        print("REPLICATION PAUSED: reads and Primary writes remain available")

    def resume_replication(self):
        self.replication_enabled.set()
        print("REPLICATION RESUMED")

    async def replicate(self):
        """Deliver queued writes in order, with a simulated network delay."""
        while True:
            stock = await self.pending.get()
            await self.replication_enabled.wait()
            await asyncio.sleep(0.5)
            # Respect a pause that occurred during the simulated delay, too.
            await self.replication_enabled.wait()
            self.secondary.stock = stock
            print(f"REPLICATED Primary -> Secondary: stock={stock}")
            self.pending.task_done()

    async def wait_for_replication(self):
        # Wait for actual delivery; fail instead of waiting forever on a bug.
        await asyncio.wait_for(self.pending.join(), timeout=5)


def check_reads(system, expected_primary, expected_secondary, label):
    actual = (system.read(system.primary), system.read(system.secondary))
    expected = (expected_primary, expected_secondary)
    if actual != expected:
        raise AssertionError(f"{label}: expected {expected}, got {actual}")
    print(f"PASS: {label}")


async def main():
    system = InventorySystem()
    worker = asyncio.create_task(system.replicate())
    try:
        print("1. Successful replication: initialize stock to 10")
        print("Both replicas initially contain stock=0")
        system.write_primary(10)
        check_reads(system, 10, 0, "Primary accepts the write before replication")
        await system.wait_for_replication()
        check_reads(system, 10, 10, "Both replicas return 10 after replication")

        print("\n2. Stale read: pause replication and change 10 -> 9")
        system.pause_replication()
        system.write_primary(9)
        # Longer than the normal 0.5-second delivery delay, to verify the pause.
        await asyncio.sleep(0.75)
        check_reads(system, 9, 10, "Secondary returns stale stock=10 while Primary returns 9")

        print("\n3. Recovery: resume replication")
        system.resume_replication()
        await system.wait_for_replication()
        check_reads(system, 9, 9, "Replicas converge to stock=9")
        print("\nALL CHECKS PASSED")
    finally:
        worker.cancel()
        with suppress(asyncio.CancelledError):
            await worker


if __name__ == "__main__":
    asyncio.run(main())
