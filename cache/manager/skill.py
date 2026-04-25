"""Skill cache mixin."""

from __future__ import annotations


class SkillsMixin:
    def get_skills(self, user_id: int) -> list[dict]:
        return self._skills_cache.get(user_id, [])

    def get_skill(self, user_id: int, name: str) -> dict | None:
        for skill in self._skills_cache.get(user_id, []):
            if skill.get("name") == name:
                return skill
        return None

    def set_skills(self, user_id: int, skills: list[dict]) -> None:
        self._skills_cache[user_id] = [dict(skill) for skill in skills]

    def add_skill(self, user_id: int, **skill_data) -> dict | None:
        if self.get_skill(user_id, skill_data["name"]):
            return None
        skill = {"id": None, "user_id": user_id, **skill_data}
        self._skills_cache.setdefault(user_id, []).append(skill)
        with self._lock:
            self._new_skills.append(skill)
        return skill

    def update_skill(self, user_id: int, name: str, **kwargs) -> bool:
        skill = self.get_skill(user_id, name)
        if not skill:
            return False
        skill.update(kwargs)
        with self._lock:
            self._updated_skills.append(skill)
        return True

    def delete_skill(self, user_id: int, name: str) -> bool:
        skills = self._skills_cache.get(user_id, [])
        for index, skill in enumerate(skills):
            if skill.get("name") == name:
                skills.pop(index)
                with self._lock:
                    self._deleted_skills.append((user_id, name))
                return True
        return False

    def get_skill_state(self, user_id: int, name: str) -> dict | None:
        return self._skill_states_cache.get(user_id, {}).get(name)

    def set_skill_state(self, user_id: int, name: str, state: dict) -> None:
        self._skill_states_cache.setdefault(user_id, {})[name] = {"user_id": user_id, "skill_name": name, **state}
        with self._lock:
            self._updated_skill_states.append(self._skill_states_cache[user_id][name])

    def delete_skill_state(self, user_id: int, name: str) -> None:
        if user_id in self._skill_states_cache:
            self._skill_states_cache[user_id].pop(name, None)
