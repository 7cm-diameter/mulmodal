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
    while interval >= 0. and agent.working():
        s = perf_counter()
        mail = await agent.try_recv(limit)
        if mail is None:
            break
        interval -= perf_counter() - s
        _, response = mail
        if response != correct and interval < postpone:
            interval = postpone
