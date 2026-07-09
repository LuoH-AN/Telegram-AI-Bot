"""Skill infrastructure.cache mixin."""

from __future__ import annotations


class SkillsMixin:
    def get_skills(self, user_id: int) -> list[dict]:
        with self._lock:
            return self._skills_cache.get(user_id, [])

    def get_skill(self, user_id: int, name: str) -> dict | None:
        with self._lock:
            for skill in self._skills_cache.get(user_id, []):
                if skill.get("name") == name:
                    return skill
            return None

    def set_skills(self, user_id: int, skills: list[dict]) -> None:
        with self._lock:
            self._skills_cache[user_id] = [dict(skill) for skill in skills]

    def add_skill(self, user_id: int, **skill_data) -> dict | None:
        with self._lock:
            if self.get_skill(user_id, skill_data["name"]):
                return None
            skill = {"id": None, "user_id": user_id, **skill_data}
            self._skills_cache.setdefault(user_id, []).append(skill)
            self._new_skills.append(skill)
            return skill

    def update_skill(self, user_id: int, name: str, **kwargs) -> bool:
        with self._lock:
            skill = self.get_skill(user_id, name)
            if not skill:
                return False
            skill.update(kwargs)
            self._updated_skills.append(skill)
            return True

    def delete_skill(self, user_id: int, name: str) -> bool:
        with self._lock:
            skills = self._skills_cache.get(user_id, [])
            for index, skill in enumerate(skills):
                if skill.get("name") == name:
                    skills.pop(index)
                    self._deleted_skills.append((user_id, name))
                    return True
            return False

    def get_skill_state(self, user_id: int, name: str) -> dict | None:
        with self._lock:
            return self._skill_states_cache.get(user_id, {}).get(name)

    def set_skill_state(self, user_id: int, name: str, state: dict) -> None:
        with self._lock:
            entry = {"user_id": user_id, "skill_name": name, **state}
            self._skill_states_cache.setdefault(user_id, {})[name] = entry
            self._updated_skill_states.append(entry)

    def delete_skill_state(self, user_id: int, name: str) -> None:
        with self._lock:
            if user_id in self._skill_states_cache:
                self._skill_states_cache[user_id].pop(name, None)
