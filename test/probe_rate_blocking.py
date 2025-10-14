import asyncio
import math
import statistics
import time

from limxsdk.robot.Rate import Rate

CTRL_HZ = 50.0
DT = 1.0 / CTRL_HZ


async def heartbeat(period=0.005, samples=400):
    gaps = []
    t_prev = time.perf_counter()
    for _ in range(samples):
        await asyncio.sleep(period)
        t_now = time.perf_counter()
        gaps.append(t_now - t_prev)
        t_prev = t_now
    return gaps


def blocking_rate_loop(n_iters=100):
    r = Rate(CTRL_HZ)
    for _ in range(n_iters):
        r.sleep()


async def main():
    hb = asyncio.create_task(heartbeat())
    t0 = time.perf_counter()
    blocking_rate_loop(n_iters=int(2.0 / DT))
    t1 = time.perf_counter()

    gaps = await hb
    print(f"blocking_rate_loop wall time: {t1 - t0:.3f}s")
    print(f"heartbeat ticks: {len(gaps)}")
    print(
        f"gap stats (s): min={min(gaps):.4f}  mean={statistics.mean(gaps):.4f}  "
        f"max={max(gaps):.4f}"
    )

    if max(gaps) > 0.5:
        print("ugh")
    else:
        print("hohoho")


if __name__ == "__main__":
    asyncio.run(main())
