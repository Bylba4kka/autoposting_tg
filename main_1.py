import html
import logging
import re
import asyncio
import uuid
from asyncio import sleep, Semaphore
from datetime import datetime, timedelta
from random import randint
import unicodedata
from aiogram import Bot, Dispatcher, types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils import executor
from aiogram.contrib.middlewares.logging import LoggingMiddleware
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.utils.exceptions import NetworkError, TelegramAPIError
from aiohttp import ClientConnectorError
from telethon import TelegramClient, events
from telethon.tl.types import PeerChannel, MessageMediaWebPage, MessageEntityTextUrl, MessageEntityBold, \
    MessageEntityItalic

from config import API_HASH, API_ID, BOT_TOKEN



bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)
dp.middleware.setup(LoggingMiddleware())
client = TelegramClient('bot', API_ID, API_HASH)

tasks = {}
channels = {}
timings = {}
bot_running = True

class Form(StatesGroup):
    get_channel_id = State()
    get_channel_name = State()
    choose_channel = State()
    get_posts = State()
    confirm_delete = State()
    get_timings = State()


main_menu = ReplyKeyboardMarkup(resize_keyboard=True)
main_menu.add(KeyboardButton('Мои задачи'))
main_menu.add(KeyboardButton('Добавить канал'))
main_menu.add(KeyboardButton('Новая задача'))
main_menu.add(KeyboardButton('Удалить задачу'))
main_menu.add(KeyboardButton('Тайм-коды'))
main_menu.add(KeyboardButton('Остановка'))

start_menu = ReplyKeyboardMarkup(resize_keyboard=True)
start_menu.add(KeyboardButton('Запуск'))

MAX_CONCURRENT_REQUESTS = 5
semaphore = Semaphore(MAX_CONCURRENT_REQUESTS)




@dp.message_handler(commands=['start'])
async def start(message: types.Message):
    global bot_running
    bot_running = True
    while True:
        try:
            await message.answer("Привет! Я бот для автоматического постинга. Выберите действие:",
                                 reply_markup=main_menu)
            break
        except (NetworkError, TelegramAPIError) as e:
            print(f"Network error occurred: {e}")
            await sleep(5)  # Повторить попытку через 5 секунд

@dp.message_handler(lambda message: message.text == 'Остановка')
async def stop_bot(message: types.Message, state: FSMContext):
    global bot_running
    bot_running = False
    tasks.clear()

    await state.finish()
    while True:
        try:
            await message.answer("Бот остановлен. Выберите 'Запуск' для возобновления работы.",
                                 reply_markup=start_menu)
            break
        except (NetworkError, TelegramAPIError) as e:
            print(f"Network error occurred: {e}")
            await sleep(5)  # Повторить попытку через 5 секунд

@dp.message_handler(lambda message: message.text == 'Запуск')
async def start_bot(message: types.Message):
    global bot_running
    bot_running = True
    while True:
        try:
            await message.answer("Бот запущен. Выберите действие:", reply_markup=main_menu)
            break
        except (NetworkError, TelegramAPIError) as e:
            print(f"Network error occurred: {e}")
            await sleep(5)  # Повторить попытку через 5 секунд

@dp.message_handler(lambda message: message.text == 'Мои задачи' and bot_running)
async def show_tasks(message: types.Message):
    if tasks:
        response = "Ваши задачи:\n"
        for task_id, task in tasks.items():
            response += f"ID: {task_id}, Канал: {task['channel']}, Количество постов: {len(task['posts'])}, Временной интервал: {task['timings']}\n"
        await message.answer(response)
    else:
        await message.answer("У вас нет активных задач.")


@dp.message_handler(lambda message: message.text == 'Добавить канал' and bot_running)
async def add_channel(message: types.Message):
    await Form.get_channel_id.set()
    back_menu = ReplyKeyboardMarkup(resize_keyboard=True)
    back_menu.add(KeyboardButton('Назад'))
    await message.answer("Введите ID канала или нажмите 'Назад' для возврата:", reply_markup=back_menu)


@dp.message_handler(state=Form.get_channel_id)
async def get_channel_id(message: types.Message, state: FSMContext):
    if message.text == 'Назад':
        await state.finish()
        await message.answer("Возврат в главное меню.", reply_markup=main_menu)
        return
    if not bot_running or message.text == 'Остановка':
        await state.finish()
        await message.answer("Бот остановлен. Выберите 'Запуск' для возобновления работы.", reply_markup=start_menu)
        return

    async with state.proxy() as data:
        data['channel_id'] = message.text.strip()

    await Form.get_channel_name.set()
    await message.answer("Теперь введите название канала или нажмите 'Назад' для возврата:")


@dp.message_handler(state=Form.get_channel_name)
async def get_channel_name(message: types.Message, state: FSMContext):
    if message.text == 'Назад':
        await Form.get_channel_id.set()
        await message.answer("Введите ID канала или нажмите 'Назад' для возврата:")
        return
    if not bot_running or message.text == 'Остановка':
        await state.finish()
        await message.answer("Бот остановлен. Выберите 'Запуск' для возобновления работы.", reply_markup=start_menu)
        return

    async with state.proxy() as data:
        channel_id = data['channel_id']
        channel_name = message.text.strip()

    if message.chat.id not in channels:
        channels[message.chat.id] = {}

    channels[message.chat.id][channel_name] = int(channel_id)

    await state.finish()
    await message.answer(f"Канал добавлен: {channel_name} (ID: {channel_id}). Выберите действие:", reply_markup=main_menu)

@dp.message_handler(lambda message: message.text == 'Новая задача' and bot_running)
async def new_task(message: types.Message):
    if message.chat.id not in channels or not channels[message.chat.id]:
        await message.answer("У вас нет добавленных каналов. Пожалуйста, добавьте канал, прежде чем создавать задачу.")
        return
    if message.chat.id not in timings or not timings[message.chat.id]:
        await message.answer("Тайм-коды не установлены. Пожалуйста, установите тайм-коды, прежде чем создавать задачу.")
        return
    keyboard = InlineKeyboardMarkup()
    for name, channel_id in channels[message.chat.id].items():
        keyboard.add(InlineKeyboardButton(name, callback_data=str(channel_id)))
    keyboard.add(InlineKeyboardButton('Назад', callback_data='back'))
    await Form.choose_channel.set()
    await message.answer("Выберите канал для постинга или нажмите 'Назад' для возврата:", reply_markup=keyboard)
    task_id = str(uuid.uuid4()).split('-')[0].upper()
    async with dp.current_state(user=message.from_user.id).proxy() as data:
        data['task_id'] = task_id
        data['timings'] = timings[message.chat.id]

@dp.callback_query_handler(state=Form.choose_channel)
async def choose_channel(callback_query: types.CallbackQuery, state: FSMContext):
    if callback_query.data == 'back':
        await state.finish()
        await bot.send_message(callback_query.from_user.id, "Возврат в главное меню.", reply_markup=main_menu)
        return

    if not bot_running:
        await state.finish()
        await bot.send_message(callback_query.from_user.id, "Бот остановлен. Выберите 'Запуск' для возобновления работы.", reply_markup=start_menu)
        return

    channel_id = int(callback_query.data)
    async with state.proxy() as data:
        data['channel'] = channel_id
    await Form.get_posts.set()
    await bot.send_message(callback_query.from_user.id, "Теперь введите ссылки на посты через точку с запятой (например, t.me/big_idea/769; t.me/big_idea/765):")
    await callback_query.answer()

@dp.message_handler(state=Form.get_posts)
async def get_posts(message: types.Message, state: FSMContext):
    if message.text == 'Назад':
        await Form.choose_channel.set()
        keyboard = InlineKeyboardMarkup()
        for name, channel_id in channels[message.chat.id].items():
            keyboard.add(InlineKeyboardButton(name, callback_data=str(channel_id)))
        keyboard.add(InlineKeyboardButton('Назад', callback_data='back'))
        await message.answer("Выберите канал для постинга или нажмите 'Назад' для возврата:", reply_markup=keyboard)
        return
    if not bot_running or message.text == 'Остановка':
        if message.chat.id in channels:
            channels.pop(message.chat.id)
        await state.finish()
        await message.answer("Бот остановлен. Выберите 'Запуск' для возобновления работы.", reply_markup=start_menu)
        return

    posts = message.text.split(';')
    async with state.proxy() as data:
        data['posts'] = [post.strip() for post in posts]
        task_id = data['task_id']
        tasks[task_id] = data.as_dict()

    await state.finish()
    await message.answer(f"Задача создана. Посты будут отправляться по установленным тайм-кодам.", reply_markup=main_menu)
    asyncio.create_task(schedule_posts(task_id))


@dp.message_handler(lambda message: message.text == 'Тайм-коды' and bot_running)
async def manage_timings(message: types.Message):
    if message.chat.id in timings and timings[message.chat.id]:
        current_timings = ', '.join(timings[message.chat.id])
        back_menu = ReplyKeyboardMarkup(resize_keyboard=True)
        back_menu.add(KeyboardButton('Назад'))
        await message.answer(f"Текущие тайм-коды: {current_timings}\nВведите новые тайм-коды через запятую или напишите 'Удалить' для удаления всех тайм-кодов.", reply_markup=back_menu)
    else:
        back_menu = ReplyKeyboardMarkup(resize_keyboard=True)
        back_menu.add(KeyboardButton('Назад'))
        await message.answer("Тайм-коды не установлены. Введите три тайм-кода через запятую (например, 12:00, 16:00, 20:00) или нажмите 'Назад' для возврата:", reply_markup=back_menu)
    await Form.get_timings.set()


@dp.message_handler(state=Form.get_timings)
async def set_timings(message: types.Message, state: FSMContext):
    if message.text == 'Назад':
        await state.finish()
        await message.answer("Возврат в главное меню.", reply_markup=main_menu)
        return

    if not bot_running or message.text.lower() == 'остановка':
        if message.chat.id in timings:
            timings.pop(message.chat.id)
        await state.finish()
        await message.answer("Бот остановлен. Выберите 'Запуск' для возобновления работы.", reply_markup=start_menu)
        return

    if message.text.lower() == 'удалить':
        if message.chat.id in timings:
            timings.pop(message.chat.id)
        await state.finish()
        await message.answer("Все тайм-коды удалены.", reply_markup=main_menu)
        return

    new_timings = message.text.split(',')
    if len(new_timings) != 3:
        await message.answer("Пожалуйста, введите ровно три тайм-кода через запятую (например, 12:00, 16:00, 20:00).")
        return

    new_timings = [timing.strip() for timing in new_timings]
    for timing in new_timings:
        try:
            datetime.strptime(timing, '%H:%M').time()
        except ValueError:
            await message.answer(f"Неверный формат времени: {timing}. Пожалуйста, используйте формат HH:MM.")
            return

    timings[message.chat.id] = new_timings
    await state.finish()
    await message.answer(f"Новые тайм-коды установлены: {', '.join(new_timings)}.", reply_markup=main_menu)


@dp.message_handler(lambda message: message.text == 'Удалить задачу' and bot_running)
async def delete_task(message: types.Message):
    if tasks:
        response = "Выберите ID задачи для удаления:\n"
        for task_id, task in tasks.items():
            response += f"ID: {task_id}, Канал: {task['channel']}\n"
        await message.answer(response)
        await Form.confirm_delete.set()
    else:
        await message.answer("У вас нет активных задач.")


@dp.message_handler(state=Form.confirm_delete)
async def confirm_delete_task(message: types.Message, state: FSMContext):
    if not bot_running or message.text == 'Остановка':
        await state.finish()
        await message.answer("Бот остановлен. Выберите 'Запуск' для возобновления работы.", reply_markup=start_menu)
        return

    task_id = message.text.strip()
    if task_id in tasks:
        del tasks[task_id]
        await state.finish()
        await message.answer(f"Задача {task_id} удалена.", reply_markup=main_menu)
    else:
        await message.answer("Неверный ID задачи. Попробуйте снова.", reply_markup=main_menu)
        await state.finish()


def insert_entities(message, entities):

    if not entities:
        return html.escape(message)

    entities = sorted(entities, key=lambda e: e.offset, reverse=True)

    for entity in entities:
        if isinstance(entity, MessageEntityTextUrl):
            url_text = message[entity.offset:entity.offset + entity.length]
            link = f'<a href="{entity.url}">{html.escape(url_text)}</a>'
            message = message[:entity.offset] + link + message[entity.offset + entity.length:]

    return message


async def schedule_posts(task_id):
    global bot_running
    task = tasks[task_id]
    channel_id = task['channel']
    post_links = task['posts']
    timings = [datetime.strptime(t, '%H:%M').time() for t in task['timings']]
    max_retries = 5
    IGNORE_ERRNO = {10038, 121}

    post_index = 0

    while bot_running and post_links:
        now = datetime.now().time()
        next_timing = None

        for timing in timings:
            if now < timing:
                next_timing = timing
                break

        if not next_timing:
            next_timing = timings[0]
            time_to_wait = (datetime.combine(datetime.today() + timedelta(days=1), next_timing) - datetime.now()).total_seconds()
        else:
            time_to_wait = (datetime.combine(datetime.today(), next_timing) - datetime.now()).total_seconds()

        await asyncio.sleep(time_to_wait)

        if not bot_running:
            break

        post = post_links[post_index % len(post_links)]
        post_index += 1

        match = re.match(r'https://t\.me/([^/]+)/(\d+)', post)
        if match:
            channel_username = match.group(1)
            message_id = int(match.group(2))
            retry_count = 0
            while retry_count < max_retries:
                try:
                    async with semaphore:
                        channel = await asyncio.wait_for(client.get_entity(channel_username), timeout=20)
                        message_to_forward = await asyncio.wait_for(client.get_messages(channel, ids=message_id), timeout=20)
                        

                        logging.info(f"Forwarding message with id {message_id} from {channel_username}")

                        message_text = message_to_forward.message
                        entities = message_to_forward.entities

                        if entities:
                            message_text = insert_entities(message_text, entities)

                        if message_to_forward.media:
                            if isinstance(message_to_forward.media, MessageMediaWebPage):
                                # Отправляем текстовое сообщение с предпросмотром ссылки
                                await asyncio.wait_for(client.send_message(
                                    PeerChannel(channel_id),
                                    message_text,
                                    parse_mode='html',
                                    link_preview=True
                                ), timeout=20)
                            else:
                                # Отправляем медиа-контент
                                await asyncio.wait_for(client.send_file(
                                    PeerChannel(channel_id),
                                    message_to_forward.media,
                                    caption=message_text,
                                    parse_mode='html'
                                ), timeout=20)
                        else:
                            # Отправляем текстовое сообщение с форматированием
                            await asyncio.wait_for(client.send_message(
                                PeerChannel(channel_id),
                                message_text,
                                parse_mode='html'
                            ), timeout=20)

                        break
                except asyncio.TimeoutError:
                    logging.error("Operation timed out")
                    retry_count += 1
                except OSError as e:
                    if e.errno in IGNORE_ERRNO:
                        logging.warning(f"Ignoring OS error: {e}")
                        break
                    else:
                        logging.error(f"OS error occurred: {e}")
                        retry_count += 1
                except (NetworkError, ClientConnectorError, TelegramAPIError, ConnectionError) as e:
                    logging.error(f"Network error occurred: {e}")
                    retry_count += 1
                finally:
                    if retry_count >= max_retries:
                        logging.error("Max retries reached. Restarting client...")

                sleep_time = min(2 ** retry_count + randint(0, 1000) / 1000, 60)
                logging.info(f"Retrying in {sleep_time} seconds...")
                await asyncio.sleep(sleep_time)
            await asyncio.sleep(10)


async def restart_client():
    global client
    await client.disconnect()
    await client.connect()
async def main():
    while True:
        try:
            await client.start(bot_token=BOT_TOKEN)
            break
        except (NetworkError, ClientConnectorError, TelegramAPIError, ConnectionError, asyncio.TimeoutError) as e:
            logging.error(f"Network error occurred during client start: {e}")
            await sleep(5)  # Повторить попытку через 5 секунд


if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.create_task(main())
    executor.start_polling(dp, skip_updates=True)