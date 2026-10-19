"""Authoritative keyboard game state, independent of the application stack."""
import random
from threading import RLock
import time
from uuid import uuid4

from .bank import load_bank
from .scores import ScoreStore


class QuizError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


class QuizEngine:
    def __init__(self, settings, clock=None):
        self.settings = settings
        self.clock = clock or (lambda: time.time() * 1000)
        self.lock = RLock()
        self.sessions = {}
        self.store = ScoreStore(settings.sqlite_path)

    def config(self):
        bank = self._bank()
        return {"enabled": self.settings.enabled,
                "ready": self.settings.enabled and len(bank) >= max(self.settings.min_questions, self.settings.questions_per_game),
                "questions_available": len(bank), "questions_per_game": self.settings.questions_per_game,
                "answer_s": self.settings.answer_s, "coop_answer_s": self.settings.coop_answer_s,
                "hold_ms": self.settings.hold_ms, "streak_bonus": self.settings.streak_bonus}

    def _bank(self):
        try:
            return load_bank(self.settings.bank_path, self.settings.clean_dir)
        except (OSError, ValueError):
            # Missing/unreadable or corrupt snapshots cannot make a playable bank.
            return []

    @staticmethod
    def _mode(mode):
        if mode not in ("versus", "coop"):
            raise QuizError(422, "Mode must be versus or coop")

    def start(self, mode, players):
        with self.lock:
            self._mode(mode)
            if not self.settings.enabled:
                raise QuizError(503, "Quiz is disabled")
            if (not isinstance(players, list) or len(players) != 2
                    or any(not isinstance(n, str) or not n.strip() or len(n.strip()) > 40 for n in players)):
                raise QuizError(422, "Provide two player names of 1 to 40 characters")
            bank = self._bank()
            if len(bank) < max(self.settings.min_questions, self.settings.questions_per_game):
                raise QuizError(503, "Quiz needs more campus data")
            now = self.clock()
            for key in list(self.sessions):
                if now - self.sessions[key]["touched"] > self.settings.session_ttl_s * 1000:
                    del self.sessions[key]
            if len(self.sessions) >= self.settings.max_sessions:
                raise QuizError(503, "Too many quiz sessions; try again later")
            sid = uuid4().hex
            state = dict(id=sid, mode=mode, players=[n.strip() for n in players], scores=[0, 0],
                         team_score=0, streak=0, active_player=None, selections=[None, None],
                         revision=0, index=0, items=random.sample(bank, self.settings.questions_per_game),
                         touched=now, tried=[], hold=None, deadline=None, message="")
            self.sessions[sid] = state
            self._begin(state, now)
            return self._render(state, now)

    def _begin(self, state, now):
        state.update(phase="buzz" if state["mode"] == "versus" else "coop", active_player=None,
                     selections=[None, None], tried=[], hold=None, message="")
        state["deadline"] = now + self.settings.coop_answer_s * 1000 if state["mode"] == "coop" else None
        state["revision"] += 1

    def _get(self, sid, now):
        state = self.sessions.get(sid)
        if state is None or now - state["touched"] > self.settings.session_ttl_s * 1000:
            self.sessions.pop(sid, None)
            raise QuizError(404, "Quiz session expired or not found")
        state["touched"] = now
        self._tick(state, now)
        return state

    def _reveal(self, state, message):
        state.update(phase="reveal", active_player=None, deadline=None, hold=None, message=message)
        state["revision"] += 1

    def _fail_versus(self, state, now):
        player = state["active_player"]
        state["tried"].append(player)
        if len(state["tried"]) == 1:
            state.update(active_player=1-player, deadline=now + self.settings.answer_s * 1000,
                         message="Passed to the other player")
            state["revision"] += 1
        else:
            self._reveal(state, "Answer revealed")

    def _tick(self, state, now):
        if state["phase"] == "coop":
            # A hold completed before the deadline wins even when polled later.
            due = state["hold"] + self.settings.hold_ms if state["hold"] is not None else None
            if due is not None and due <= now and due <= state["deadline"]:
                correct = state["selections"][0] == state["items"][state["index"]].answer_index
                state["streak"] = state["streak"] + 1 if correct else 0
                if correct:
                    state["team_score"] += 1 + (state["streak"] - 1) * self.settings.streak_bonus
                self._reveal(state, "Team correct!" if correct else "Try the next question")
            elif now >= state["deadline"]:
                state["streak"] = 0
                self._reveal(state, "Time is up")
        elif state["phase"] == "answer" and now >= state["deadline"]:
            # The pass receives its full answer window from the original expiry.
            deadline = state["deadline"]
            self._fail_versus(state, deadline)
            if state["phase"] == "answer" and now >= state["deadline"]:
                self._fail_versus(state, state["deadline"])

    def view(self, sid):
        with self.lock:
            now = self.clock()
            return self._render(self._get(sid, now), now)

    def action(self, sid, action, player=None, option=None):
        with self.lock:
            now = self.clock()
            state = self._get(sid, now)
            if action == "tick":
                return self._render(state, now)
            if action == "next":
                if state["phase"] == "finished":
                    return self._render(state, now)
                if state["phase"] != "reveal":
                    raise QuizError(409, "Wait for the answer reveal")
                if state["index"] + 1 == len(state["items"]):
                    names = state["players"] if state["mode"] == "versus" else [" + ".join(state["players"])]
                    scores = state["scores"] if state["mode"] == "versus" else [state["team_score"]]
                    self.store.save(state["id"], state["mode"], names, scores, now)
                    state.update(phase="finished", message="Game complete")
                    state["revision"] += 1
                else:
                    state["index"] += 1
                    self._begin(state, now)
                return self._render(state, now)
            if action not in ("buzz", "answer"):
                raise QuizError(422, "Unknown quiz action")
            if type(player) is not int or player not in (0, 1):
                raise QuizError(422, "Player must be 0 or 1")
            if action == "buzz":
                if state["mode"] != "versus" or state["phase"] != "buzz":
                    raise QuizError(409, "Buzz is not available")
                state.update(phase="answer", active_player=player, deadline=now + self.settings.answer_s * 1000)
            else:
                if type(option) is not int or option not in range(4):
                    raise QuizError(422, "Option must be 0 to 3")
                if state["phase"] == "coop":
                    if state["selections"][player] != option:
                        state["selections"][player] = option
                        state["hold"] = now if state["selections"][0] == state["selections"][1] else None
                    state["message"] = "You two need to talk!" if None not in state["selections"] and state["hold"] is None else ""
                elif state["phase"] == "answer" and state["active_player"] == player:
                    state["selections"][player] = option
                    if option == state["items"][state["index"]].answer_index:
                        state["scores"][player] += 1
                        self._reveal(state, "Correct!")
                    else:
                        self._fail_versus(state, now)
                else:
                    raise QuizError(409, "This player cannot answer now")
            state["revision"] += 1
            self._tick(state, now)
            return self._render(state, now)

    def _render(self, state, now):
        question = None
        if state["phase"] != "finished":
            item = state["items"][state["index"]]
            question = {"id": item.id, "question": item.question, "options": list(item.options)}
            if state["phase"] == "reveal":
                question.update(answer_index=item.answer_index, evidence=item.evidence, source_url=item.source_url)
        result = {key: state[key] for key in ("id", "mode", "team_score", "streak", "phase", "active_player", "revision", "message")}
        result.update(players=list(state["players"]), scores=list(state["scores"]), selections=list(state["selections"]),
                      question_number=state["index"]+1, total_questions=len(state["items"]), question=question,
                      remaining_ms=max(0, state["deadline"]-now) if state["deadline"] is not None else None,
                      hold_remaining_ms=max(0, self.settings.hold_ms-(now-state["hold"])) if state["hold"] is not None else None,
                      server_now_ms=now)
        return result

    def leaderboard(self, mode):
        self._mode(mode)
        return self.store.leaderboard(mode, self.clock())
