from aiogram.fsm.state import State, StatesGroup

class UserStates(StatesGroup):
    waiting_for_custom_amount = State() # Для доната
    waiting_for_custom_limit = State()  # Для лимита подписки
    browsing_catalog = State()