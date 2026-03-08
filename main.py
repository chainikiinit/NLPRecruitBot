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
from time import sleep
import requests
from Tools import build_tools
import os
from dotenv import load_dotenv

load_dotenv()
bot = telebot.TeleBot(os.getenv('TOKEN_BOT'))
api_key = os.getenv("GIGACHAT_API")

user_contexts = {}

@bot.message_handler(commands=["start"])
def handle_start(message):
    global user_contexts
    user_id = str(message.from_user.id)
    if user_id in user_contexts:
        del user_contexts[user_id]
    user_contexts[user_id] = {
        "id": 1,
        "candidate_name": message.from_user.first_name,
        "position": "",
        "grade": "",
        "experience": "",
        "history": [],
        "last_user_message": "",
        "last_agent_message": "",
        "finished": False,
        "interviewer_signal": "",
        "difficulty": "easy",
        "hallucinations": 0,
    }
    context = user_contexts[user_id]
    tools = build_tools(context)

    observer_tools = [
        t for t in tools
        if t.name in ["mark_hallucination", "send_signal_to_interviewer", "change_difficulty"]
    ]

    interviewer_tools = [
        t for t in tools
        if t.name in ["end_interview"]
    ]

    global logger
    logger = Logger(context['candidate_name'])

    global observer
    observer = ObserverAgent(api_key, observer_tools)

    global interviewer
    interviewer = InterviewerAgent(api_key, interviewer_tools)

    global summary_agent
    summary_agent = SummaryAgent(api_key)

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
    context = user_contexts[user_id]
    context["turn_id"] = 1

    if call.data == 'start_interview':
        bot.answer_callback_query(callback_query_id=call.id, show_alert=False, text="Интервью начато!")

        start_interview(user_id, context)

    elif call.data == 'edit_data':
        #Возвращаемся к началу
        bot.answer_callback_query(callback_query_id=call.id, show_alert=False, text="Вы можете изменить данные.")
        last_message = context.get("last_message")

        handle_start(last_message)


def start_interview(user_id, context):
    last_message = context.get("last_message")

    if not context:
        bot.send_message(user_id, "Контекст потерян. Попробуйте снова /start.")
        return


    observer_thoughts = "Начало интервью. Поздоровайся и попроси рассказать о себе"
    internal_combined = observer_thoughts
    agent_message = interviewer.ask_question(context, internal_combined)
    bot.send_message(user_id, agent_message)
    bot.register_next_step_handler(last_message, process_answer)

def process_answer(message):
    user_id = str(message.from_user.id)
    if user_id not in user_contexts:
        bot.send_message(user_id, "Контекст потерян. Попробуйте снова /start")
        return

    context = user_contexts[user_id]
    user_message = message.text.strip()
    context["last_user_message"] = message
    context["history"].append({
        "interviewer": context["last_agent_message"],
        "user": user_message
    })

    observer_thoughts = observer.analyze(context)
    internal_combined = f"[Observer]: {observer_thoughts}+\n"
    context["history"][-1] = {
        "interviewer": context["last_agent_message"],
        "user": user_message,
        "observer": observer_thoughts
    }

    logger.record_turn(
        turn_id=context["turn_id"],
        agent_visible_message=context["last_agent_message"],
        user_message=user_message,
        internal_thoughts=internal_combined
    )

    context["id"] += 1

    if user_message.lower() == "стоп":
        context["finished"] = True
        final_summary = summary_agent.summarize(context)
        bot.send_message(user_id, final_summary)
        del user_contexts[user_id]
        return



    if context.get("finished"):
        final_summary = summary_agent.summarize(context)
        logger.set_final_feedback(final_summary)
        logger.save_to_file()
        bot.send_message(user_id, final_summary)
        del user_contexts[user_id]
        return

    next_agent_message = interviewer.ask_question(context, internal_combined)


    bot.send_message(user_id, next_agent_message)
    context["last_agent_message"] = next_agent_message
    bot.register_next_step_handler(message, process_answer)


if __name__ == "__main__":
    #bot.polling(non_stop=True)

    print("Запуск")
    try:
        bot.infinity_polling(timeout=60, long_polling_timeout=60)
    except Exception as e:
        print(f"Произошла ошибка: {e}")

