from time import perf_counter
from amas.agent import Agent


def show_progress(trial: int, isi: float):
    print(f"Trial {trial}: Cue will be presented {isi} secs after.")


async def flush_message_for(agent: Agent, duration: float):
    while duration >= 0. and agent.working():
        s = perf_counter()
        await agent.try_recv(duration)
        duration -= perf_counter() - s


async def fixed_interval_with_limit(agent: Agent, interval: float,
                                    correct: str, postpone: float, limit: float):
    _limit = limit
    while interval >= 0. and agent.working():
        s = perf_counter()
        mail = await agent.try_recv(interval)
        required_time = perf_counter() - s
        interval -= required_time
        if limit < 0 and interval < 0:
            break
        if mail is None:
            interval = 1e-3
            limit -= required_time
            continue
        _, response = mail
        if response != correct and interval < postpone:
            interval = postpone
            limit = _limit


async def fixed_interval_with_limit2(agent: Agent, interval: float,
                                    correct: str, postpone: float, limit: float):
    while interval >= 0. and agent.working():
        s = perf_counter()
        mail = await agent.try_recv(limit)
        if mail is None:
            break
        interval -= perf_counter() - s
        _, response = mail
        if response != correct and interval < postpone:
            interval = postpone
