from amas.agent import Agent, NotWorkingError
from comprex.agent import ABEND, NEND, OBSERVER, RECORDER, START
from comprex.audio import Speaker, make_white_noise
from comprex.config import Experimental
from comprex.scheduler import TrialIterator, geom_rng, unif_rng
from comprex.util import timestamp
from pino.ino import HIGH, LOW, Arduino
from numpy import int64, cumsum
from mulmodal.util import fixed_time_with_postopone


NOISE_IDX = 14
CONTROLLER = "Controller"


async def control(agent: Agent, ino: Arduino, expvars: Experimental):
    mean_component_length = expvars.get("mean-component-length", 25)
    range_component = expvars.get("range-component-length", 10)
    interval_between_component = expvars.get("interval-between-component", 60.)
    mean_iri = expvars.get("inter-reward-interval", 10.)
    range_iri = expvars.get("range-IRI", 5.)
    number_of_rewards = expvars.get("number-of-rewards", 200)
    number_of_component = number_of_rewards // mean_component_length

    light_pins = expvars.get("light-pin", [4, 5, 6, 7, 8])
    reward_pins = expvars.get("reward-pin", [2, 3])
    speaker = Speaker(expvars.get("speaker", 6))
    noise = make_white_noise(30.)
    response_pins = list(map(str, expvars.get("response-pin", [-9, -10])))
    reward_duration = expvars.get("reward-duration", 0.01)

    component_lengths = unif_rng(mean_component_length,
                                 range_component,
                                 number_of_component).astype(int64) + 1
    components: list[int] = sum([[0] * n if (i % 2 == 0) else [1] * n \
                                    for i, n in zip(range(number_of_component),
                                                    component_lengths)], [])
    iris = unif_rng(mean_iri, range_iri, number_of_rewards)
    trial_iterator = TrialIterator(list(range(number_of_rewards)),
                                   list(zip(iris, components)))

    try:
        while agent.working():
            agent.send_to(RECORDER, timestamp(START))
            previous_component = components[0]
            for trial, (iri, component) in trial_iterator:
                print(f"Trial {trial}: Reward will occur {iri} secs after.")
                if previous_component != component:
                    if component == 0:
                        agent.send_to(RECORDER, timestamp(-NOISE_IDX))
                        speaker.stop()
                        agent.send_to(RECORDER, timestamp(light_pins[2]))
                        ino.digital_write(light_pins[2], HIGH)
                    else:
                        agent.send_to(RECORDER, timestamp(-light_pins[2]))
                        ino.digital_write(light_pins[2], LOW)
                        agent.send_to(RECORDER, timestamp(NOISE_IDX))
                        speaker.play(noise, False, True)
                        light_pin = light_pins.pop()
                if component == 0:
                    target_response = response_pins[0]
                    reward_pin = reward_pins[0]
                else:
                    target_response = response_pins[1]
                    reward_pin = reward_pins[1]
                await fixed_time_with_postopone(agent, iri, target_response, 2.)
                agent.send_to(RECORDER, timestamp(reward_pin))
                ino.digital_write(reward_pin, HIGH)
                await agent.sleep(reward_duration)
                agent.send_to(RECORDER, timestamp(-reward_pin))
                ino.digital_write(reward_pin, LOW)

                previous_component = component
            agent.send_to(OBSERVER, NEND)
            agent.send_to(RECORDER, timestamp(NEND))
            agent.finish()
    except NotWorkingError:
        agent.send_to(OBSERVER, ABEND)
        agent.send_to(RECORDER, timestamp(NEND))
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
    from comprex.agent import Observer, Recorder, _self_terminate, READER
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
