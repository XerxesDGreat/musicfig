import random

OFF   = [0,0,0]
RED   = [100,0,0]
GREEN = [0,100,0]
BLUE  = [0,0,100]
PINK = [100,75,79]
ORANGE = [100,64,0]
PURPLE = [100,0,100]
LBLUE = [100,100,100]
OLIVE = [50,50,0]

COLORS = ['self.RED', 'self.GREEN', 'self.BLUE', 'self.PINK', 
                        'self.ORANGE', 'self.PURPLE', 'self.LBLUE', 'self.OLIVE']

def get_random_color():
    return random.choice(COLORS)