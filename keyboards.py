from aiogram.types import ReplyKeyboardMarkup, KeyboardButton


main_menu = ReplyKeyboardMarkup(resize_keyboard=True)
main_menu.add(KeyboardButton('Мои задачи'))
main_menu.add(KeyboardButton('Создать задачу'))
main_menu.add(KeyboardButton('Удалить задачу'))
# main_menu.add(KeyboardButton('Остановка'))

start_menu = ReplyKeyboardMarkup(resize_keyboard=True)
start_menu.add(KeyboardButton('Запуск'))

back_menu = ReplyKeyboardMarkup(resize_keyboard=True)
back_menu.add(KeyboardButton('Назад'))