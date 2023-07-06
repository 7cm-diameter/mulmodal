import sounddevice as sd
from amas.agent import Agent, NotWorkingError
from comprex.agent import ABEND, NEND, OBSERVER, RECORDER, START
from comprex.audio import make_white_noise
from comprex.config import Experimental
from comprex.scheduler import TrialIterator, blockwise_shuffle
from comprex.util import timestamp
from pino.ino import HIGH, LOW, Arduino

FS = 48000
NOISE_IDX = 14
sd.default.samplerate = FS


async def present_stimulus(agent: Agent, ino: Arduino, pin: int,
                           duration: float) -> None:
    ino.digital_write(pin, HIGH)
    agent.send_to(RECORDER, timestamp(pin))
    await agent.sleep(duration)
    ino.digital_write(pin, LOW)
    agent.send_to(RECORDER, timestamp(-pin))
    return None


async def control(agent: Agent, ino: Arduino, expvars: Experimental) -> None:
    sound_duration = expvars.get("sound-duration", 1.)
    light_duration = expvars.get("light-duration", 1.)
    reward_duration = expvars.get("reward-duration", 0.05)

    light_pin = expvars.get("light-pin", [8, 9, 10, 11, 12])
    reward_pin = expvars.get("reward-pin", [6, 7])
    noise = make_white_noise(sound_duration, FS)  # Click音でも良い？

    isi = expvars.get("inter-stimulus-interval", 18.)

    number_of_trial = expvars.get("number-of-trial", 200)
    number_of_blocks = int(number_of_trial / (len(light_pin) * 2))
    light_order = blockwise_shuffle(light_pin * 2 * number_of_blocks,
                                    len(light_pin))
    stimulus_order = blockwise_shuffle(
        sum([[0, 1] for _ in range(5)], []) * number_of_blocks,
        len(light_pin) * 2)  # 0: light -> sound / 1: sound -> light
    trial_iterator = TrialIterator(list(range(number_of_trial)),
                                   list(zip(stimulus_order, light_order)))

    try:
        while agent.working():
            agent.send_to(RECORDER, timestamp(START))
            for i, (first_light, light) in trial_iterator:
                await agent.sleep(isi)
                if first_light:
                    agent.send_to(RECORDER, timestamp(light))
                    ino.digital_write(light, HIGH)
                    await agent.sleep(light_duration)
                    agent.send_to(RECORDER, timestamp(NOISE_IDX))
                    sd.play(noise)
                    await agent.sleep(sound_duration)
                    ino.digital_write(light, LOW)
                    agent.send_to(RECORDER, timestamp(-NOISE_IDX))
                    agent.send_to(RECORDER, timestamp(-light))
                    await present_stimulus(agent, ino, reward_pin[0],
                                           reward_duration)
                else:
                    agent.send_to(RECORDER, timestamp(NOISE_IDX))
                    sd.play(noise, loop=True)
                    await agent.sleep(sound_duration)
                    await present_stimulus(agent, ino, light, light_duration)
                    sd.stop()
                    agent.send_to(RECORDER, timestamp(-NOISE_IDX))
                    await present_stimulus(agent, ino, reward_pin[1],
                                           reward_duration)
            agent.send_to(OBSERVER, NEND)
            agent.send_to(RECORDER, timestamp(NEND))
            agent.finish()
    except NotWorkingError:
        agent.send_to(OBSERVER, ABEND)
        agent.send_to(RECORDER, timestamp(ABEND))
        agent.finish()
    return None


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
