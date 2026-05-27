from aiogram.fsm.state import State, StatesGroup

class AdminStates(StatesGroup):
    waiting_for_subs = State()
    waiting_for_broadcast = State()
    broadcast_adding_button = State()
    broadcast_confirm = State()