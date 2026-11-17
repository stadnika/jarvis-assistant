while True:

    try:

        try:
            action, value = (
                state.command_queue
                .get_nowait()
            )

        except queue.Empty:
            pass

        else:

            state.LAST_ACTIVITY = time.time()

            if action == "wake":

                state.LISTENING = True

                speak(
                    "Так, слухаю."
                )

            elif action == "command":

                execute_cmd(value)

            elif action == "timer":

                ...
            else:

                execute_dynamic_cmd(
                    action,
                    value
                )

        if (
            state.LISTENING and
            time.time() -
            state.LAST_ACTIVITY > 30
        ):

            state.LISTENING = False

        time.sleep(0.1)

    except Exception as error:

        print(error)