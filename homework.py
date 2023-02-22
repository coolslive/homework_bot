import logging
import os
import sys
import time
from http import HTTPStatus

import requests
import telegram
from dotenv import load_dotenv

from exceptions import (
    EmptyResponseFromAPI,
    TelegramError,
    WrongResponseCode,
)

load_dotenv()
PRACTICUM_TOKEN = os.getenv("PRACTICUM_TOKEN")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")


RETRY_PERIOD = 600
ENDPOINT = "https://practicum.yandex.ru/api/user_api/homework_statuses/"
HEADERS = {"Authorization": f"OAuth {PRACTICUM_TOKEN}"}


HOMEWORK_VERDICTS = {
    "approved": "Работа проверена: ревьюеру всё понравилось. Ура!",
    "reviewing": "Работа взята на проверку ревьюером.",
    "rejected": "Работа проверена: у ревьюера есть замечания.",
}


def send_message(bot: telegram.bot.Bot, message: str) -> None:
    """Отправляет сообщение в Telegram."""
    try:
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
        logging.debug(f"Отправленно сообщение: {message}")
    except telegram.error.TelegramError as error:
        error_text = f"Ошибка отправки сообщения в Telegram: {error}"
        logging.error(error_text)
        raise TelegramError(error_text)
    else:
        logging.debug("Статус отправаки сообщения в Telegram")


def get_api_answer(current_timestamp: int) -> dict:
    """Делает запрос к ENDPOINT API.
    В качестве параметра функция получает временную метку.
    В случае успешного запроса вернет ответ API,
    преобразовав формат JSON к типу данных Python.
    """
    timestamp = current_timestamp or int(time.time())
    params_request = {
        "url": ENDPOINT,
        "headers": HEADERS,
        "params": {"from_date": timestamp},
    }
    message = ("Запрос к API: {url}, {headers}, {params}.").format(
        **params_request
    )
    logging.info(message)
    try:
        response = requests.get(**params_request)
        if response.status_code != HTTPStatus.OK:
            raise WrongResponseCode(
                f"API не возвращает код 200. "
                f"Код: {response.status_code}. "
                f"Причина: {response.reason}. "
                f"Текст: {response.text}."
            )
        return response.json()
    except Exception as error:
        message = (
            "API не возвращает код 200. Запрос: {url}, {headers}, {params}."
        ).format(**params_request)
        raise WrongResponseCode(message, error)


def check_response(response: dict) -> list:
    """Проверяет ответ API на корректность.
    В качестве параметра функция получает ответ API
    Должна вернуть список домашних работ (возможно он будет пуст),
    доступный в ответе по ключу 'homeworks'.
    """
    if not isinstance(response, dict):
        raise TypeError("Ответ не является dict")
    if "homeworks" not in response or "current_date" not in response:
        raise EmptyResponseFromAPI("Нет ключа homeworks в ответе")
    homeworks = response.get("homeworks")
    if not isinstance(homeworks, list):
        raise TypeError("homeworks не является list")
    return homeworks


def parse_status(homework: dict) -> str:
    """Получаем информацию о конкретной работе.
    Возвращает подготовленную для отправки строку
    в Telegram.
    """
    if "homework_name" not in homework:
        raise KeyError("Нет ключа homework_name в ответе")
    homework_name = homework.get("homework_name")
    homework_status = homework.get("status")
    if homework_status not in HOMEWORK_VERDICTS:
        raise ValueError(f"Неизвестный статус - {homework_status}")
    return (
        'Изменился статус проверки работы "{homework_name}". {verdict}'
    ).format(
        homework_name=homework_name, verdict=HOMEWORK_VERDICTS[homework_status]
    )


def check_tokens() -> bool:
    """Проверяем наличие всех токенов.
    В случае отсутствия одного, бота останавливаем.
    """
    logging.info("Проверка наличия всех токенов")
    return all([PRACTICUM_TOKEN, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID])


def main():
    """Логика работы бота."""
    if not check_tokens():
        message = "Токен отсутствует. Бот остановлен!"
        logging.critical(message)
        sys.exit(message)
    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    current_timestamp = int(time.time())
    start_message = "Бот запущен"
    send_message(bot, start_message)
    logging.info(start_message)
    last_message = ""

    while True:
        try:
            response = get_api_answer(current_timestamp)
            current_timestamp = response.get("current_date", int(time.time()))
            homeworks = check_response(response)
            if homeworks:
                message = parse_status(homeworks[0])
            else:
                message = "Статус не изменился"
            if message != last_message:
                send_message(bot, message)
                last_message = message
            else:
                logging.info(message)

        except Exception as error:
            message = f"Сбой в работе программы: {error}"
            logging.error(message, exc_info=True)
            if message != last_message:
                send_message(bot, message)
                last_message = message

        finally:
            time.sleep(RETRY_PERIOD)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        handlers=[
            logging.FileHandler(
                os.path.abspath("main.log"), mode="a", encoding="UTF-8"
            ),
            logging.StreamHandler(stream=sys.stdout),
        ],
        format="%(asctime)s, %(levelname)s, %(funcName)s, "
        "%(lineno)s, %(name)s, %(message)s",
    )
    main()
