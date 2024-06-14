import asyncio
import logging
import uuid

from random import randint

from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor
from aiogram.contrib.middlewares.logging import LoggingMiddleware
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.utils.exceptions import TelegramAPIError
from telethon import TelegramClient, events
from telethon.tl.types import MessageMediaWebPage, PeerChannel, MessageMediaPhoto, MessageMediaDocument, InputMessagesFilterPhotos



from config import API_HASH, API_ID, BOT_TOKEN
from json_proccesing import load_data_json, save_data_json, delete_json_data
from keyboards import back_menu, start_menu, main_menu
from entity_processing import insert_entities

bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)
dp.middleware.setup(LoggingMiddleware())

# Множество для отслеживания обработанных grouped_id
processed_grouped_ids = set()
tasks = load_data_json()
channels = {}
bot_running = True
max_retries = 5
IGNORE_ERRNO = {10038, 121}
semaphore = asyncio.Semaphore(10)  # Ограничение одновременных запросов


# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
main_logger = logging.FileHandler('main.log')
main_logger.setLevel(logging.INFO)

logger = logging.getLogger()
logger.addHandler(main_logger)


try:
    client = TelegramClient("session", API_ID, API_HASH)
    client.start()
except Exception as ap:
    logger.info(f"ERROR - {ap}")
    exit(1)


class Form(StatesGroup):
    get_source_channel = State()
    get_target_channel = State()
    get_source_channel_name = State()
    get_target_channel_name = State()
    confirm_delete = State()


@dp.message_handler(commands=['start'])
async def start(message: types.Message):
    global bot_running
    bot_running = True
    for task_id in tasks:
        asyncio.create_task(monitor_channel(task_id))
    await message.answer("Привет! Я бот для кругового автопостинга. Выберите действие:", reply_markup=main_menu)
    


@dp.message_handler(lambda message: message.text == 'Мои задачи' and bot_running)
async def show_tasks(message: types.Message):
    if tasks:
        response = "Ваши задачи:\n"
        for task_id, task in tasks.items():
            response += (
                f"ID: {task_id}, "
                f"Из канала: {task['source_channel_name']} (ID {task['source_channel']}) "
                f"в {task['target_channel_name']} (ID {task['target_channel']}).\n"
            )
        await message.answer(response)
    else:
        await message.answer("У вас нет активных задач.")


@dp.message_handler(lambda message: message.text == 'Удалить задачу' and bot_running)
async def delete_task(message: types.Message):
    if tasks:
        response = "Выберите ID задачи для удаления:\n"
        for task_id, task in tasks.items():
            response +=(
                f"ID: {task_id}\n"
                f"Из канала: {task['source_channel_name']}\n"
                f"в {task['target_channel_name']}.\n\n"
            )
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
        delete_json_data(task_id)
        await message.answer(f"Задача {task_id} удалена.", reply_markup=main_menu)
    else:
        await message.answer("Неверный ID задачи. Попробуйте снова.", reply_markup=main_menu)
        await state.finish()


@dp.message_handler(lambda message: message.text == 'Остановка')
async def stop_bot(message: types.Message, state: FSMContext):
    global bot_running
    bot_running = False
    tasks.clear()

    await state.finish()
    await message.answer("Бот остановлен. Выберите 'Запуск' для возобновления работы.", reply_markup=start_menu)

@dp.message_handler(lambda message: message.text == 'Запуск')
async def start_bot(message: types.Message):
    global bot_running
    bot_running = True
    await message.answer("Бот запущен. Выберите действие:", reply_markup=main_menu)

@dp.message_handler(lambda message: message.text == 'Создать задачу' and bot_running)
async def new_task(message: types.Message):
    await Form.get_source_channel.set()
    await message.answer("Введите ID исходного канала:")


@dp.message_handler(lambda message: message.text == 'отмена', state='*')
async def cancel_handler(message: types.Message, state: FSMContext):
    
    current_state = await state.get_state()
    if current_state is None:
        return

    await state.finish()
    await message.reply('Действие отменено.', reply_markup=main_menu)


@dp.message_handler(state=Form.get_source_channel)
async def get_source_channel(message: types.Message, state: FSMContext):
    async with state.proxy() as data:
        data['source_channel'] = message.text.strip()
    
    await Form.get_source_channel_name.set()
    await message.answer("Теперь введите название исходного канала или нажмите 'Назад' для возврата:", reply_markup=back_menu)


@dp.message_handler(state=Form.get_source_channel_name)
async def get_target_channel_name(message: types.Message, state: FSMContext):
    if message.text == 'Назад':
        await Form.get_source_channel.set()
        await message.answer("Введите ID исходного канала:")
        return
    if not bot_running or message.text == 'Остановка':
        await state.finish()
        await message.answer("Бот остановлен. Выберите 'Запуск' для возобновления работы.", reply_markup=start_menu)
        return

    async with state.proxy() as data:
        data['source_channel_name'] = message.text.strip()

    await Form.get_target_channel.set()
    await message.answer("Введите ID канала для постинга:")


@dp.message_handler(state=Form.get_target_channel)
async def get_target_channel(message: types.Message, state: FSMContext):
    async with state.proxy() as data:
        data['target_channel'] = message.text.strip()

    await Form.get_target_channel_name.set()
    await message.answer("Теперь введите название канала для постинга или нажмите 'Назад' для возврата:", reply_markup=back_menu)

    


@dp.message_handler(state=Form.get_target_channel_name)
async def get_target_channel_name(message: types.Message, state: FSMContext):
    if message.text == 'Назад':
        await Form.get_target_channel.set()
        await message.answer("Введите ID канала для постинга:")
        return
    if not bot_running or message.text == 'Остановка':
        await state.finish()
        await message.answer("Бот остановлен. Выберите 'Запуск' для возобновления работы.", reply_markup=start_menu)
        return

    async with state.proxy() as data:
        data['target_channel_name'] = message.text.strip()

    task_id = str(uuid.uuid4()).split('-')[0].upper()
    tasks[task_id] = data.as_dict()

    # Сохранение текущих рассылок
    save_data_json(tasks)

    await state.finish()
    await message.answer(
        f"Задача создана. Все новые посты из {data['source_channel_name']}(ID {data['source_channel']}) будут автоматически отправляться в {data['target_channel_name']}(ID {data['target_channel']}).",
        reply_markup=main_menu
        )
    asyncio.create_task(monitor_channel(task_id))




async def fetch_media_group(client: TelegramClient, source_channel, grouped_id):
    messages = []
    async for message in client.iter_messages(source_channel, limit=11):
        if message.grouped_id == grouped_id:
            messages.append(message)
    messages.sort(key=lambda x: x.id) 
    return messages



async def monitor_channel(task_id):
    task = tasks[task_id]
    source_channel = int(task['source_channel'])
    target_channel = int(task['target_channel'])
    target_channel = await client.get_entity(PeerChannel(target_channel))


    async def forward_message(event):
        if task_id not in tasks:
            return
        
        post = event.message
        message_id = post.id
        channel_username = source_channel
        
        grouped_id = post.grouped_id

        if grouped_id and grouped_id in processed_grouped_ids:
            return
        else:
            processed_grouped_ids.add(grouped_id)


        retry_count = 0
        while retry_count < max_retries:
            try:
                async with semaphore:
                    channel = await asyncio.wait_for(client.get_entity(channel_username), timeout=20)
                    message_to_forward = await asyncio.wait_for(client.get_messages(channel, ids=message_id), timeout=20)

                    logger.info(f"Forwarding message with id {message_id} from {channel_username}")

                    message_text = message_to_forward.message
                    entities = message_to_forward.entities

                    if entities:
                        message_text = insert_entities(message_text, entities)
                

                media = message_to_forward.media
                media_messages = []

                if media:
                    if isinstance(media, MessageMediaWebPage):
                        # Если медиагруппа - отправляем сообщение с включенным превью ссылки
                        await asyncio.wait_for(client.send_file(
                            target_channel,
                            message_text,
                            parse_mode='html',
                            link_preview=True
                        ), timeout=20)
                    elif isinstance(media, MessageMediaPhoto):
                        # Если одно изображение - добавляем его в список медиамесседжей
                        
                        
                        if grouped_id:
                            # Получить все сообщения с тем же grouped_id
                            media_messages = await fetch_media_group(client, source_channel, grouped_id)
                    
                        else:
                            media_messages.append(media)
                    elif isinstance(media, MessageMediaDocument):
                        # Если это документ с изображением - добавляем его в список медиамесседжей
                        media_messages.append(media)
                    if media_messages:
                        # Если есть медиамесседжи - отправляем медиагруппу
                        await asyncio.wait_for(client.send_file(
                            target_channel,
                            file=media_messages,
                            caption=message_text,
                            parse_mode="markdown"
                        ), timeout=20)

                else:

                    # Если нет медиа - отправляем текстовое сообщение
                    await asyncio.wait_for(client.send_message(
                        target_channel,
                        message_text,
                        parse_mode='html'
                    ), timeout=20)

                break
            except asyncio.TimeoutError:
                logger.info("Operation timed out")
                retry_count += 1
            except OSError as e:
                if e.errno in IGNORE_ERRNO:
                    logger.info(f"Ignoring OS error: {e}")
                    break
                else:
                    logger.info(f"OS error occurred: {e}")
                    retry_count += 1
            except (TelegramAPIError, ConnectionError) as e:
                logger.info(f"Network error occurred: {e}")
                retry_count += 1
            finally:
                if retry_count >= max_retries:
                    logger.info("Max retries reached. Restarting client...")

            sleep_time = min(2 ** retry_count + randint(0, 1000) / 1000, 60)
            logger.info(f"Retrying in {sleep_time} seconds...")
            await asyncio.sleep(sleep_time)

    client.add_event_handler(forward_message, events.NewMessage(chats=source_channel, incoming=True))
    await client.run_until_disconnected()


if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    executor.start_polling(dp, skip_updates=True)

    