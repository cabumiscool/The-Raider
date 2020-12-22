import queue

from ..config import Settings

from .background_objects import *
from .background_process import BackgroundProcess


process = BackgroundProcess(queue.Queue(), queue.Queue(), Settings())
print(process)
