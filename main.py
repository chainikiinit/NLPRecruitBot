import telebot
from telebot import types
from Agents import ObserverAgent, InterviewerAgent,SummaryAgent
from Logger import Logger
import langchain
langchain.debug = False
langchain.llm_cache = None
import argparse
import json
from telebot.types import KeyboardButton, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
import asyncio



bot = telebot.TeleBot(' ')
api_key = ' '

user_contexts = {}

observer = ObserverAgent(api_key)
interviewer = InterviewerAgent(api_key)
summary_agent = SummaryAgent(api_key)


@bot.message_handler(commands=["start"])
def handle_start(message):
    global user_contexts
    user_id = str(message.from_user.id)
    if user_id in user_contexts:
        del user_contexts[user_id]
    user_contexts[user_id] = {
        "candidate_name": message.from_user.first_name + " " + message.from_user.last_name,
        "position": "",
        "grade": "",
        "experience": "",
        "history": [],
        "last_user_message": "",
        "last_agent_message": "",
        "finished": False
    }
    bot.reply_to(message, "Добро пожаловать! \nЭто бот для проведения собеседования с помощью LLM на основе твоих навыков! Чтобы начать интервью ответьте на 3 вопроса.\n1. Введите название вашей позиции. Например: Solution Architect")
    bot.register_next_step_handler(message, handle_position)

@bot.message_handler(commands=["restart"])
def restart_state(message):
    user_id = str(message.from_user.id)
    if user_id in user_contexts:
        del user_contexts[user_id]
    bot.reply_to(message, "История удалена. Начнём интервью заново!")
    handle_start(message)


def handle_position(message):
    user_id = str(message.from_user.id)
    user_contexts[user_id]["position"] = message.text.strip()

    markup = types.InlineKeyboardMarkup(row_width=3)
    for level in ["Junior", "Middle", "Senior"]:
        button = types.InlineKeyboardButton(level, callback_data=f'level_{level}')
        markup.add(button)

    bot.send_message(user_id, "2. Выберите ваш уровень подготовки:", reply_markup=markup)


@bot.callback_query_handler(func=lambda call: call.data.startswith('level_'))
def handle_grade(call):
    user_id = str(call.from_user.id)
    selected_level = call.data.split('_')[1].strip()
    user_contexts[user_id]['grade'] = selected_level

    bot.edit_message_text(
        chat_id=user_id,
        message_id=call.message.message_id,
        text=f"2. Ваш уровень подготовки: {selected_level}\n\n",
        reply_markup=None
    )
    bot.send_message(user_id, "3. Перечислите ваши ключевые навыки через запятую или опишите ваш опыт работы.")

    bot.register_next_step_handler(call.message, handle_experience)




def handle_experience(message):
    user_id = str(message.from_user.id)
    experience_text = message.text.strip()

    # Ограничиваем длину опыта
    max_length = 30
    if len(experience_text) >= max_length:
        bot.reply_to(message, "Слишком длинное сообщение, сократите его.")
        bot.register_next_step_handler(message, handle_experience)
        return

    user_contexts[user_id]["experience"] = experience_text
    user_contexts[user_id]["last_message"] = message  # сохраняем сообщение потому что костыль

    confirm_text = (
        f"Позиция: {user_contexts[user_id]['position']}\n"
        f"Уровень: {user_contexts[user_id]['grade']}\n"
        f"Навыки: {user_contexts[user_id]['experience']}"
    )

    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("Начать интервью", callback_data='start_interview'),
        types.InlineKeyboardButton("Изменить данные", callback_data='edit_data')
    )

    bot.send_message(
        chat_id=user_id,
        text=f"{confirm_text}\n\nДанные верны?",
        reply_markup= markup
    )


@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    user_id = str(call.from_user.id)

    if call.data == 'start_interview':
        bot.answer_callback_query(callback_query_id=call.id, show_alert=False, text="Интервью начато!")
        context = user_contexts[user_id]
        start_interview(user_id, context)

    elif call.data == 'edit_data':
        #Возвращаемся к началу
        bot.answer_callback_query(callback_query_id=call.id, show_alert=False, text="Вы можете изменить данные.")
        #edit_data(user_id)


'''
# Обработка нажатия кнопки для начала интервью
@bot.callback_query_handler(func=lambda call: call.data == 'start_interview')
def start_interview_callback(call):
    user_id = str(call.from_user.id)
    context = user_contexts.get(user_id)
    if context is None or context['finished']:
        bot.answer_callback_query(callback_query_id=call.id, show_alert=True, text='Интервью завершилось.')
        return

    bot.answer_callback_query(callback_query_id=call.id)
    start_interview(call.message, context)
'''


def start_interview(user_id, context):
    last_message = context.get("last_message")

    #context = user_contexts[user_id]
    if not context:
        bot.send_message(user_id, "Контекст потерян. Попробуйте снова /start.")
        return

    logger = Logger(context["candidate_name"])
    observer_thoughts = "Начало интервью. Поздоровайтесь и спросите о кандидате."
    internal_combined = observer_thoughts
    agent_message = interviewer.ask_question(context, internal_combined)
    bot.send_message(user_id, agent_message)
    bot.register_next_step_handler(last_message, process_answer)

def process_answer(message):
    user_id = str(message.from_user.id)
    context = user_contexts[user_id]
    user_message = message.text.strip()
    context["last_user_message"] = user_message
    context["history"].append({"agent": context["last_agent_message"], "user": user_message})

    if user_message.lower() == "стоп":
        context["finished"] = True
        final_summary = summary_agent.summarize(context)
        bot.send_message(user_id, final_summary)
        del user_contexts[user_id]
        return

    observer_thoughts = observer.analyze(context)
    interviewer_thoughts = interviewer.reflect(context, observer_thoughts)
    internal_combined = f"[Observer]: {observer_thoughts}+\n [Interviewer]: {interviewer_thoughts}+\n"
    next_agent_message = interviewer.ask_question(context, internal_combined)
    bot.send_message(user_id, next_agent_message)
    context["last_agent_message"] = next_agent_message
    bot.register_next_step_handler(message, process_answer)



from time import sleep
import requests

if __name__ == "__main__":
    bot.polling(non_stop=True)
    '''
    while True:
        response = requests.get("https://t.me/NLPRecruit_bot")
        for message in response:
            bot.answer(message)
            sleep(1)
'''