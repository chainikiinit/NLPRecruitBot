import json
class Logger:
    def __init__(self, participant_name):
        self.participant_name = participant_name
        self.log = {
            "participant_name": participant_name,
            "turns": [],
            "final_feedback": None
        }

    def record_turn(self, turn_id, agent_visible_message, user_message,internal_thoughts):
        self.log["turns"].append({
            "turn_id": turn_id,
            "agent_visible_message": agent_visible_message,
            "user_message": user_message,
            "internal_thoughts": internal_thoughts
        })

    def set_final_feedback(self, feedback):
        self.log["final_feedback"] = feedback

    def save_to_file(self, filename="interview_log.json"):
        with open(filename, "w") as f:
            json.dump(self.log, f, ensure_ascii=False, indent=4)