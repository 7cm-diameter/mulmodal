from amas.agent import Agent, NotWorkingError
from comprex.agent import ABEND, NEND, OBSERVER, RECORDER, START
from comprex.config import Experimental
from comprex.scheduler import TrialIterator2, unif_rng
from comprex.util import timestamp
from pino.ino import HIGH, LOW, Arduino
from mulmodal.share import show_progress


async def control(agent: Agent, ino: Arduino, expvars: Experimental):
    # Pin settings
    light_pin: int = expvars.get("light-pin", [4, 5, 6, 7, 8])[2]
    reward_pin: int = expvars.get("reward-pin", [2, 3])[0]

    # Experimental parameters
    cue_duration: float = expvars.get("cue-duration", 1.5)
    reward_duration: float = expvars.get("reward-duration", 0.02)
    mean_isi: float = expvars.get("inter-stimulus-interval", 13.5)
    range_isi: float = expvars.get("isi-range", 5.)
    number_of_rewards: int = expvars.get("number-of-rewards", 200)
    isis = unif_rng(mean_isi, range_isi, number_of_rewards)

    trials = TrialIterator2(isis)

    try:
        while agent.working():
            for i, isi in trials:
                show_progress(i, isi)
                await agent.sleep(isi)
                agent.send_to(RECORDER, timestamp(light_pin))
                ino.digital_write(light_pin, HIGH)
                await agent.sleep(cue_duration)
                agent.send_to(RECORDER, timestamp(-light_pin))
                ino.digital_write(light_pin, LOW)
                agent.send_to(RECORDER, timestamp(reward_pin))
                ino.digital_write(reward_pin, HIGH)
                await agent.sleep(reward_duration)
                agent.send_to(RECORDER, timestamp(-reward_pin))
                ino.digital_write(reward_pin, LOW)
            agent.send_to(RECORDER, timestamp(NEND))
            agent.send_to(OBSERVER, NEND)
            agent.finish()
    except NotWorkingError:
        agent.send_to(RECORDER, timestamp(ABEND))
        agent.send_to(OBSERVER, ABEND)
        agent.finish()


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
    config.metadata.update(condition = "pavlovian-with-single-led")

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

    controller = Agent("Controller") \
        .assign_task(control, ino=ino, expvars=config.experimental) \
        .assign_task(_self_terminate)

    # Use built-in agents
    reader = Reader(ino=ino)
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
