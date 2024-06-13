import html

from telethon.tl.types import (
    MessageEntityBold, MessageEntityItalic, MessageEntityCode, MessageEntityPre,
    MessageEntityTextUrl, MessageEntityMention, MessageEntityMentionName
)

def insert_entities(message_text, entities):
    """
    Обрабатывает сущности в сообщении и возвращает текст с HTML-разметкой.
    """
    html_text = message_text

    if not entities:
        return html.escape(message)

    entities = sorted(entities, key=lambda e: e.offset, reverse=True)

    for entity in entities:
        if isinstance(entity, MessageEntityTextUrl):
            url_text = message[entity.offset:entity.offset + entity.length]
            link = f'<a href="{entity.url}">{html.escape(url_text)}</a>'
            message = message[:entity.offset] + link + message[entity.offset + entity.length:]

    # Обрабатываем сущности в обратном порядке, чтобы не нарушать индексы при вставке тегов
    for entity in sorted(entities, key=lambda e: e.offset, reverse=True):
        if isinstance(entity, MessageEntityBold):
            html_text = (html_text[:entity.offset] + '<b>' + 
                         html_text[entity.offset:entity.offset + entity.length] + '</b>' + 
                         html_text[entity.offset + entity.length:])
        elif isinstance(entity, MessageEntityItalic):
            html_text = (html_text[:entity.offset] + '<i>' + 
                         html_text[entity.offset:entity.offset + entity.length] + '</i>' + 
                         html_text[entity.offset + entity.length:])
        elif isinstance(entity, MessageEntityCode):
            html_text = (html_text[:entity.offset] + '<code>' + 
                         html_text[entity.offset:entity.offset + entity.length] + '</code>' + 
                         html_text[entity.offset + entity.length:])
        elif isinstance(entity, MessageEntityPre):
            html_text = (html_text[:entity.offset] + '<pre>' + 
                         html_text[entity.offset:entity.offset + entity.length] + '</pre>' + 
                         html_text[entity.offset + entity.length:])
        elif isinstance(entity, MessageEntityTextUrl):
            html_text = (html_text[:entity.offset] + f'<a href="{entity.url}">' + 
                         html_text[entity.offset:entity.offset + entity.length] + '</a>' + 
                         html_text[entity.offset + entity.length:])
        elif isinstance(entity, MessageEntityMention):
            html_text = (html_text[:entity.offset] + '<a href="https://t.me/' + 
                         html_text[entity.offset + 1:entity.offset + entity.length] + '">' + 
                         html_text[entity.offset:entity.offset + entity.length] + '</a>' + 
                         html_text[entity.offset + entity.length:])
        elif isinstance(entity, MessageEntityMentionName):
            html_text = (html_text[:entity.offset] + f'<a href="tg://user?id={entity.user_id}">' + 
                         html_text[entity.offset:entity.offset + entity.length] + '</a>' + 
                         html_text[entity.offset + entity.length:])
        # Добавьте дополнительные проверки для других типов сущностей, если необходимо

    return html_text
