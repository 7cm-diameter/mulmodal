import sounddevice as sd
from amas.agent import Agent, NotWorkingError
from comprex.agent import ABEND, NEND, OBSERVER, RECORDER, START
from comprex.audio import make_white_noise, Speaker
from comprex.config import Experimental
from comprex.scheduler import TrialIterator, blockwise_shuffle, unif_rng
from comprex.util import timestamp
from pino.ino import HIGH, LOW, Arduino
from mulmodal.util import flush_message_for, fixed_interval_with_limit, present_stimulus

NOISE_IDX = 14
CONTROLLER = "Controller"


async def control(agent: Agent, ino: Arduino, expvars: Experimental) -> None:
    first_duration = expvars.get("first-duration", 1.)
    initial_second_duration = expvars.get("initial-second-duration", 1.)
    last_second_duration = expvars.get("last-second-duration", 1.)
    second_duration_sound = initial_second_duration
    second_duration_light = initial_second_duration
    diff_first_second_light = first_duration - initial_second_duration
    diff_first_second_sound = first_duration - initial_second_duration
    reward_duration = expvars.get("reward-duration", 0.05)
    postpone = expvars.get("postpone", .5)

    light_pin = expvars.get("light-pin", [8, 9, 10, 11, 12])
    reward_pin = expvars.get("reward-pin", [6, 7])
    response_pins = list(map(str, expvars.get("response-pin", [-9, -10])))
    speaker = Speaker(expvars.get("speaker", 6))
    noise = make_white_noise(first_duration * 2.)  # Click音でも良い？

    mean_isi = expvars.get("inter-stimulus-interval", 19.)
    range_isi = expvars.get("interval-range", 10.)

    number_of_trial = expvars.get("number-of-trial", 200)
    isis = unif_rng(mean_isi, range_isi, number_of_trial)
    step = (last_second_duration - initial_second_duration) / (number_of_trial / 2)
    number_of_blocks = int(number_of_trial / (len(light_pin) * 2))
    light_positions = blockwise_shuffle(light_pin * 2 * number_of_blocks,
                                    len(light_pin))
    stimulus_order = blockwise_shuffle(
        sum([[0, 1] for _ in range(5)], []) * number_of_blocks,
        len(light_pin) * 2)  # 0: light -> sound / 1: sound -> light
    trial_iterator = TrialIterator(list(range(number_of_trial)),
                                   list(zip(stimulus_order, light_positions, isis)))

    try:
        while agent.working():
            agent.send_to(RECORDER, timestamp(START))
            for i, (is_light_first, light_position, isi) in trial_iterator:
                print(f"Trial {i}: Cue will be presented {isi} secs after.")
                await flush_message_for(agent, isi)
                if is_light_first:
                    agent.send_to(RECORDER, timestamp(light_position))
                    ino.digital_write(light_position, HIGH)
                    await flush_message_for(agent, diff_first_second_sound)
                    agent.send_to(RECORDER, timestamp(NOISE_IDX))
                    speaker.play(noise, False, True)
                    await fixed_interval_with_limit(agent, second_duration_sound,
                                                    response_pins[0], postpone,
                                                    first_duration * 2)
                    agent.send_to(RECORDER, timestamp(-light_position))
                    agent.send_to(RECORDER, timestamp(-NOISE_IDX))
                    ino.digital_write(light_position, LOW)
                    speaker.stop()
                    await present_stimulus(agent, ino, reward_pin[0],
                                           reward_duration)
                    diff_first_second_sound -= step
                    second_duration += step
                else:
                    agent.send_to(RECORDER, timestamp(NOISE_IDX))
                    speaker.play(noise, False, True)
                    await flush_message_for(agent, diff_first_second_light)
                    agent.send_to(RECORDER, timestamp(light_position))
                    ino.digital_write(light_position, HIGH)
                    await fixed_interval_with_limit(agent, second_duration_light,
                                                    response_pins[1], postpone,
                                                    first_duration * 2)
                    agent.send_to(RECORDER, timestamp(-light_position))
                    agent.send_to(RECORDER, timestamp(-NOISE_IDX))
                    ino.digital_write(light_position, LOW)
                    speaker.stop()
                    await present_stimulus(agent, ino, reward_pin[1],
                                           reward_duration)
                    diff_first_second_light -= step
            agent.send_to(OBSERVER, NEND)
            agent.send_to(RECORDER, timestamp(NEND))
            agent.finish()
    except NotWorkingError:
        agent.send_to(OBSERVER, ABEND)
        agent.send_to(RECORDER, timestamp(ABEND))
        agent.finish()
    return None


async def read(agent: Agent, ino: Arduino, expvars: Experimental):
    response_pin = expvars.get("response-pin", [-9, -10])

    response_pins_str = list(map(str, response_pin))

    try:
        while agent.working():
            input_: bytes = await agent.call_async(ino.read_until_eol)
            if input_ is None:
                continue
            parsed_input = input_.rstrip().decode("utf-8")
            agent.send_to(RECORDER, timestamp(parsed_input))
            if parsed_input in response_pins_str:
                agent.send_to(CONTROLLER, parsed_input)

    except NotWorkingError:
        ino.cancel_read()


if __name__ == '__main__':
    from os import mkdir
    from os.path import exists, join

    from amas.connection import Register
    from amas.env import Environment
    from comprex.agent import Observer, Reader, Recorder, _self_terminate, READER
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
