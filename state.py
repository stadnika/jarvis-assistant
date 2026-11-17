"""Mutable runtime state shared by Jarvis modules."""

import queue

LISTENING = True
TIMER_DEADLINE = None
command_queue = queue.Queue()
