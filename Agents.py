from langchain_gigachat.chat_models import GigaChat
from langchain_core.prompts import ChatPromptTemplate
from Tools import invoke_with_tools

class InterviewerAgent:
  def __init__(self,api_key,tools):
      self.tools_dict = {tool.name: tool for tool in tools}
      self.llm = GigaChat(credentials=api_key,verify_ssl_certs=False).bind_tools(tools)
      self.prompt_question = ChatPromptTemplate.from_messages([
            ("system", """Ты интервьюер на техническом собеседовании. Веди беседу с кандидатом как настоящий человек:
                    - Задавай вопросы последовательно, строя диалог, ориентируясь на ответы кандидата,историю и установленную сложность.
                    - Не повторяй ранее заданные вопросы. Вопросы должны соответвовать позиции и грейду кандидата. 
                    - Будь вежливым и дружелюбным, поддерживай естественный темп беседы. Если пользователь затрудняется смени тему. 
                    - При формировании вопроса учитывай советы и сигналы Observer.
                    - Не включай Observer-сообщения, размышления или пояснения в текст вопроса.
                    - Формулируй **только один вопрос** для кандидата за раз, понятный и конкретный.
                    - Старайся связывать вопросы логически: предыдущий вопрос+предыдущий ответ → следующий вопрос.
                    - Если нужно изменить состояние интервью — используй инструменты внутренне, не показывай tool_call пользователю.
                    - Если пользователь отказывется отвечать более 5 раз→ вызови инструмент:end_interview(reason="Пользователь не отвечает")
                    - ВАЖНО если в question_count написано первый вопрос, задай вопрос кандидату и НЕ завершай интервью.
                    - Обязательно если в question_count написано закончить интервью-> вызови инструмент:end_interview(reason="Конец интервью") """),
            ("human", """Позиция: {position} Грейд: {grade} Опыт: {experience} Совет Observer: {thoughts} История последних ходов: {history} Сложность вопроса:{difficulty} Сигнал Observer:{signal} question_count:{question_count}""")
        ])

  def ask_question(self, context, thoughts):
        question_count='обычный вопрос'
        if context['id']<3:question_count='первый вопрос'
        elif context['id'] > 15: question_count = 'закончить интервью'
        messages=self.prompt_question.format_messages(
                position=context["position"],
                grade=context["grade"],
                experience=context["experience"],
                thoughts=thoughts,
                history=context.get("history", [])[-5:],
                difficulty=context['difficulty'],
                signal=context['interviewer_signal'],
                question_count=question_count,
            )
        response = invoke_with_tools(self.llm, messages,self.tools_dict)
        context['interviewer_signal']= ""
        context["last_agent_message"] = response.content
        return response.content

class ObserverAgent:
  def __init__(self,api_key,tools):
        self.tools_dict = {tool.name: tool for tool in tools}
        self.llm = GigaChat(
            credentials=api_key,
            verify_ssl_certs=False
        ).bind_tools(tools)
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", """Ты — скрытый наблюдатель технического интервью. 
              Кратко оцени ответы кандидата: качество (excellent/ok/poor/hallucination), off-topic, ошибки фактов(hallucinations). 
              Давай рекомендации Interviewer и уровень сложности следующего вопроса. 
              Если кандидат отходит от темы посоветуй интервьеру плавно вернуть его к вопросу. Не задавай вопрос, только размышляй.
              Если нужно изменить состояние интервью — используй инструменты внутренне, не показывай tool_call пользователю.
              ВАЖНО Если:
               -кандидат даёт ответ с фактологической ошибкой или уходит от темы -> mark_hallucination(reason="ответ не по теме") Не пиши как текст, вызови инструмент.
               -кандидат отказывается отвечать -> send_signal_to_interviewer(message="кандидат отказывается отвечать, смени тему")Не пиши как текст, вызови инструмент.
               -Ответ слабый или неверный -> change_difficulty(level="easy")Не пиши как текст, вызови инструмент.
               -Ответ полный и верный -> change_difficulty(level="hard")Не пиши как текст, вызови инструмент."""),
            ("human", """Вопрос: {last_agent_message} Ответ кандидата: {last_user_message} История последних ходов: {history} Грейд: {grade} Сложность вопроса:{difficulty}""")
        ])
  def analyze(self, context):
        messages=self.prompt.format_messages(
                last_agent_message=context.get("last_agent_message", ""),
                last_user_message=context.get("last_user_message", ""),
                history=context.get("history", [])[-3:],
                grade=context.get("grade", "Junior"),
                difficulty=context['difficulty']
            )
        response = invoke_with_tools(self.llm, messages, self.tools_dict)
        return response.content.strip()
class SummaryAgent:
    def __init__(self,api_key):
        self.llm = GigaChat(credentials=api_key, verify_ssl_certs=False)
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", """Ты аналитик интервью. Сделай структурированный отчёт по истории интервью. 
            При составлении отчёта учти количество галлюцинаций и оценку ответов от Observer.
            Если кандидат много отвечал не по теме или отвечал мало и неверно, то он не может быть нанят.
            Если информации мало, не выдумывай, строго анализируй интервью.
            Oцени кандидата на соответвие позиции и грейду.  Используй план: 
            1) Decision Должны быть эти поля: Грейд, Рекомендация для найма (Выбери из [да/нет]), Уверенность в оценке
            2) Hard Skills: Подтвержденные навыки и Пробелы в знаниях
            3) Soft Skills: Ясность, Честность, Вовлеченность
            4) Советы(roadmap) для кандидата
            Сделай кратко и полезно для обучения."""),
            ("human", """История интервью: {history} Грейд: {grade} Позиция:{position} Галлюцинации:{hallucination} """)
        ])

    def summarize(self, context):
        response = self.llm.invoke(
            self.prompt.format_messages(
                history=context.get("history", []),
                grade=context["grade"],
                hallucination=context['hallucinations'],
                position=context["position"],
            )
        )
        if "Рекомендация для найма: нет" in response.content.strip():
            context['hire'] = "нет"

        return response.content.strip()
