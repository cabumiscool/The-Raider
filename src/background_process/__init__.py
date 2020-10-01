from .background_objects import *
from config import Settings
from .background_process import BackgroundProcess

import queue

process = background_process.BackgroundProcess(queue.Queue(), queue.Queue(), Settings())
print(process)