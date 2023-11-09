from amas.agent import Agent, NotWorkingError
from comprex.agent import ABEND, NEND, OBSERVER, RECORDER, READER
from comprex.audio import make_white_noise, Speaker
from comprex.config import Experimental
from comprex.scheduler import TrialIterator2, unif_rng, repeat, blockwise_shuffle
from comprex.util import timestamp
from pino.ino import HIGH, LOW, Arduino
from mulmodal.share import show_progress, flush_message_for, fixed_interval_with_limit2


NOISE_IDX = 14
CONTROLLER = "Controller"


async def control(agent: Agent, ino: Arduino, expvars: Experimental):
    # Pin settings
    light_pins: list[int] = expvars.get("light-pin", [4, 5, 6, 7, 8])
    speaker = Speaker(expvars.get("speaker", 6))
    reward_pins: list[int] = expvars.get("reward-pin", [2, 3])
    response_pins: list[str] = list(map(str, expvars.get("response-pin", [-9, -10])))

    # Experimental parameters
    cue_duration: float = expvars.get("cue-duration", 1.5)
    white_noise = make_white_noise(cue_duration)
    reward_duration: float = expvars.get("reward-duration", 0.02)
    mean_isi: float = expvars.get("inter-stimulus-interval", 13.5)
    range_isi: float = expvars.get("isi-range", 5.)
    number_of_rewards: int = expvars.get("number-of-rewards", 200)
    postpone: float = expvars.get("postpone", 0.5)
    waittime_limit: float = expvars.get("limit-of-waittaime", 5.)
    isis = unif_rng(mean_isi, range_isi, number_of_rewards)
    _stimuli: list[int] = light_pins + [NOISE_IDX for _ in range(len(light_pins))]
    stimuli: list[int] = blockwise_shuffle(sum(repeat([_stimuli],
                                                      [number_of_rewards // len(_stimuli)]),
                                               []),
                                           len(_stimuli))
    trials = TrialIterator2(isis, stimuli)

    try:
        while agent.working():
            for i, isi, stimulus in trials:
                show_progress(i, isi)
                await flush_message_for(agent, isi)
                agent.send_to(RECORDER, timestamp(stimulus))
                if stimulus == NOISE_IDX:
                    speaker.play(white_noise, blocking=False, loop=True)
                    await fixed_interval_with_limit2(agent, cue_duration, response_pins[1], postpone, waittime_limit)
                    agent.send_to(RECORDER, timestamp(-stimulus))
                    speaker.stop()
                    reward = reward_pins[1]
                else:
                    ino.digital_write(stimulus, HIGH)
                    await fixed_interval_with_limit2(agent, cue_duration, response_pins[0], postpone, waittime_limit)
                    agent.send_to(RECORDER, timestamp(-stimulus))
                    ino.digital_write(stimulus, LOW)
                    reward = reward_pins[0]
                agent.send_to(RECORDER, timestamp(reward))
                ino.digital_write(reward, HIGH)
                await flush_message_for(agent, reward_duration)
                agent.send_to(RECORDER, timestamp(-reward))
                ino.digital_write(reward, LOW)
            agent.send_to(RECORDER, timestamp(NEND))
            agent.send_to(OBSERVER, NEND)
            agent.finish()
    except NotWorkingError:
        agent.send_to(RECORDER, timestamp(ABEND))
        agent.send_to(OBSERVER, ABEND)
        agent.finish()


async def read(agent: Agent, ino: Arduino, expvars: Experimental):
    response_pins: list[str] = list(map(str, expvars.get("response-pin", [-9, -10])))
    try:
        while agent.working():
            read_bytes: bytes = await agent.call_async(ino.read_until_eol)
            if read_bytes is None:
                continue
            decoded = read_bytes.rstrip().decode("utf-8")
            if decoded in response_pins:
                agent.send_to(CONTROLLER, decoded)
            agent.send_to(RECORDER, timestamp(decoded))
    except NotWorkingError:
        pass


if __name__ == '__main__':
    from os import mkdir
    from os.path import exists, join

    from amas.connection import Register
    from amas.env import Environment
    from comprex.agent import Observer, Reader, Recorder, _self_terminate
    from comprex.config import PinoClap
    from comprex.util import get_current_file_abspath, namefile
    from pino.ino import Arduino, Comport

    config = PinoClap().config
    config.metadata.update(condition = "va-discrimination")

    com = Comport() \
        .apply_settings(config.comport) \
        .set_timeout(1.0) \
        .deploy() \
        .connect()

    ino = Arduino(com)
    ino.apply_pinmode_settings(config.pinmode)

    data_dir = join(get_current_file_abspath(__file__), "data")
    if not exists(data_dir):
        mkdir(data_dir)
    filename = join(data_dir, namefile(config.metadata))

    controller = Agent(CONTROLLER) \
        .assign_task(control, ino=ino, expvars=config.experimental) \
        .assign_task(_self_terminate)

    # Use built-in agents
    reader = Agent(READER) \
        .assign_task(read, ino=ino, expvars=config.experimental) \
        .assign_task(_self_terminate)
    recorder = Recorder(filename=filename)
    observer = Observer()

    agents = [controller, reader, recorder, observer]
    register = Register(agents)
    env = Environment(agents)

    try:
        env.run()
    except KeyboardInterrupt:
        observer.send_all(ABEND)
        observer.finish()
