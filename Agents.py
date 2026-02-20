from langchain_gigachat.chat_models import GigaChat
from langchain_core.prompts import ChatPromptTemplate


class InterviewerAgent:
  def __init__(self,api_key):
        self.llm = GigaChat(
            credentials=api_key,
            verify_ssl_certs=False
        )
        self.prompt_question = ChatPromptTemplate.from_messages([
            ("system", "Ты интервьюер на техническом собеседовании. В начале интервью поздоровойся и попроси рассказать о себе. Сформулируй только вопрос для кандидата, учитывая советы Observer и историю интервью. Не отвечай Observer. Сформулируй только вопрос для кандидата, учитывая советы Observer и историю интервью. Не отвечай Observer."),
            ("human", """Позиция: {position} Грейд: {grade} Опыт: {experience} Совет Observer: {thoughts} История последних ходов: {history}""")
        ])

        self.prompt_reflect = ChatPromptTemplate.from_messages([
            ("system", "Ты интервьюер на техническом собеседовании. Кратко как в диалоге ответь Observer на его совет, не задавай вопрос кандидату."),
            ("human", """Совет Observer: {observer_thoughts} История последних ходов: {history}""")
        ])

  def reflect(self, context, observer_thoughts):
        response = self.llm.invoke(
            self.prompt_reflect.format_messages(
                observer_thoughts=observer_thoughts,
                history=context.get("history", [])[-3:]
            )
        )
        return response.content.strip()

  def ask_question(self, context, thoughts):
        response = self.llm.invoke(
            self.prompt_question.format_messages(
                position=context["position"],
                grade=context["grade"],
                experience=context["experience"],
                thoughts=thoughts,
                history=context.get("history", [])[-3:]
            )
        )
        context["last_agent_message"] = response.content
        return response.content

class ObserverAgent:
  def __init__(self,api_key):
        self.llm = GigaChat(
            credentials=api_key,
            verify_ssl_certs=False
        )
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", """Ты — скрытый наблюдатель технического интервью. Кратко оцени ответы кандидата: качество (excellent/ok/poor/hallucination), off-topic, ошибки фактов. 
              Давай рекомендации Interviewer и уровень сложности следующего вопроса. Если кандидат отходит от темы посоветуй интервьеру плавно вернуть его к вопросу. Не задавай вопрос, только размышляй."""),
            ("human", """Вопрос: {last_agent_message} Ответ кандидата: {last_user_message} История последних ходов: {history} Грейд: {grade}""")
        ])
  def analyze(self, context):
        response = self.llm.invoke(
            self.prompt.format_messages(
                last_agent_message=context.get("last_agent_message", ""),
                last_user_message=context.get("last_user_message", ""),
                history=context.get("history", [])[-3:],
                grade=context.get("grade", "Junior")
            )
        )
        return response.content.strip()
class SummaryAgent:
    def __init__(self,api_key):
        self.llm = GigaChat(credentials=api_key, verify_ssl_certs=False)
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", """Ты аналитик интервью. Сделай структурированный отчёт по истории интервью. 
            Oцени: 
            1) Decision (Grade, Hiring Recommendation, Confidence)
            2) Hard Skills: Confirmed Skills и Knowledge Gaps
            3) Soft Skills: Clarity, Honesty, Engagement
            4) Roadmap для кандидата
            Сделай кратко и полезно для обучения."""),
            ("human", """История интервью: {history} Грейд: {grade} """)
        ])

    def summarize(self, context):
        response = self.llm.invoke(
            self.prompt.format_messages(
                history=context.get("history", []),
                grade=context.get("grade", "Junior")
            )
        )
        return response.content.strip()