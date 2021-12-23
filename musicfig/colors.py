import random

OFF     = [0,   0,   0]
RED     = [100, 0,   0]
GREEN   = [0,   100, 0]
BLUE    = [0,   0,   100]
PINK    = [100, 75,  79]
ORANGE  = [100, 64,  0]
YELLOW  = [100, 100, 0]
PURPLE  = [100, 0,   100]
LBLUE   = [100, 100, 100]
OLIVE   = [50,  50,  0]
DIM     = [20,  20,  20]

COLORS = [RED, GREEN, BLUE, PINK, ORANGE, PURPLE, LBLUE, OLIVE, YELLOW]

def get_random_color():
    return random.choice(COLORS)