from time import perf_counter
from typing import Any, Optional
from amas.agent import Agent
from numpy.random import uniform
from comprex.util import timestamp
from comprex.agent import RECORDER
from pino.ino import Arduino, HIGH, LOW


async def flush_message_for(agent: Agent, duration: float):
    while duration >= 0. and agent.working():
        s = perf_counter()
        await agent.try_recv(duration)
        e = perf_counter()
        duration -= e - s


async def fixed_interval_with_postpone(agent: Agent, duration: float,
                                        target_response: Any, postpone: float = 0.):
    while duration >= 0. and agent.working():
        s = perf_counter()
        mail = await agent.try_recv(duration)
        duration -= perf_counter() - s
        if mail is None:
            duration = 1e-3
            continue
        _, response = mail
        if response != target_response and duration < postpone:
            duration = postpone


async def fixed_time_with_postpone(agent: Agent, duration: float,
                                    target_response: Any, postpone: float = 0.):
    while duration >= 0. and agent.working():
        s = perf_counter()
        mail = await agent.try_recv(duration)
        duration -= perf_counter() - s
        if mail is None:
            break
        _, response = mail
        if response != target_response and duration < postpone:
            duration = postpone


async def fixed_interval_with_limit(agent: Agent, duration: float, target_response: Any,
                                    postpone: float = 0., limit: float = 10.):
    while duration >= 0. and agent.working():
        s = perf_counter()
        mail = await agent.try_recv(duration)
        required_time = perf_counter() - s
        duration -= required_time
        limit -= required_time
        if limit < 0 and duration < 0:
            break
        if mail is None:
            duration = 1e-3
            continue
        _, response = mail
        if response != target_response and duration < postpone:
            duration = postpone


async def present_stimulus(agent: Agent, ino: Arduino, pin: int,
                           duration: float) -> None:
    ino.digital_write(pin, HIGH)
    agent.send_to(RECORDER, timestamp(pin))
    await agent.sleep(duration)
    ino.digital_write(pin, LOW)
    agent.send_to(RECORDER, timestamp(-pin))
    return None
