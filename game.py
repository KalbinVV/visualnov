# -*- coding: utf-8 -*-
"""
Логика игры (визуальная новелла)
Любовный симулятор
"""

import json
from datetime import datetime
from typing import Optional, Dict, Any, List

from flask import session
from sqlalchemy.orm import Session

from database import Database, Story, Scene, Chapter, User, Choice, ChoiceHistory
from story import StoryService


class GameService:
    """Сервис игры"""

    def __init__(self, db: Database):
        """
        Инициализация сервиса игры

        Args:
            db: Объект базы данных
        """
        self.db = db
        self.story_service = StoryService(db)

    def get_game_info(self, story_id: int) -> Optional[Dict[str, Any]]:
        story = self.story_service.get_story_by_id(story_id)

        if story:
            return {
                'key': story.story_key,
                'title': story.title,
                'description': story.description,
                'premium': story.premium,
                'diamonds_cost': story.diamonds_cost,
                'chapters_count': story.chapters_count,
                'is_published': story.is_published,
                'cover_image': story.cover_image,
                'background_image': story.background_image
            }

        return None

    def get_available_games(self, user_id: int) -> List[Dict[str, Any]]:
        games_list = []

        stories = self.story_service.get_all_stories(published_only=True)

        for story in stories:
            games_list.append({
                'key': story.story_key,
                'title': story.title,
                'description': story.description,
                'chapters': story.chapters_count,
                'premium': story.premium,
                'diamonds_cost': story.diamonds_cost,
                'id': story.id
            })

        return games_list

    def can_access_game(self, user_id: int, story_id: int) -> tuple[bool, str]:
        story = self.story_service.get_story_by_id(story_id)

        if story:
            if not story.is_published:
                return False, 'История еще не опубликована'

            if not story.premium:
                return True, 'История доступна'


            user = self.db.get_user_by_id(user_id)
            if not user:
                return False, 'Пользователь не найден'

            diamonds_cost = story.diamonds_cost
            if user.diamonds < diamonds_cost:
                return False, f'Недостаточно алмазов. Нужно {diamonds_cost}'

            return True, 'История доступна за алмазы'

        user = self.db.get_user_by_id(user_id)
        if not user:
            return False, 'Пользователь не найден'

        return True, 'Игра доступна за алмазы'



    def make_input_choice(self, user_id: int, story_id: int, scene_id: int, value: str) -> tuple[bool, str, int, int]:
        with Session(self.db.engine) as s:
            choice = s.query(Choice).filter(Choice.scene_id == scene_id,
                                             Choice.choice_text == value).first()

            if not choice:
                return False, 'Неправильный ответ!', -1, -1

            return self.make_choice(user_id, story_id, choice.id)

    def make_choice(self, user_id: int, story_id: int,
                    choice_id: int) -> tuple[bool, str, int, int]:

        with Session(self.db.engine) as s:
            user = s.get(User, user_id)
            choice = s.get(Choice, choice_id)

            success, msg = self.is_choice_available(user_id, choice_id)

            if success:
                if choice.premium:
                    user.diamonds -= choice.diamonds_cost
                    s.commit()

                self.db.save_game(user_id, story_id,
                                  choice.next_scene_id,
                                  choice.next_chapter_id,
                                  teasing_change=choice.teasing_change,
                                  friendship_change=choice.friendship_change,
                                  passion_change=choice.passion_change)

                choice_history = ChoiceHistory(choice_id=choice.id,
                                               user_id=user.id)
                s.add(choice_history)
                s.commit()
            else:
                return False, msg, -1, -1

            return True, '', choice.next_scene_id, choice.next_chapter_id

    def is_choice_available(self, user_id: int, choice_id: int) -> tuple[bool,str]:
        with Session(self.db.engine) as s:
            choice = s.get(Choice, choice_id)
            scene = s.query(Scene).filter_by(id=choice.scene_id).first()
            chapter = s.query(Chapter).filter_by(id=scene.chapter_id).first()

            user = s.get(User, user_id)
            user_save = self.db.load_game_raw(user_id, chapter.story_id)

            if choice.premium:
                if user.diamonds < choice.diamonds_cost:
                    return False, 'Недостаточно алмазов!'

            if choice.only_leader:
                if not user.is_leader:
                    return False, 'Вы должны быть лидером команды!'

            if user_save.friendship_level < choice.required_friendship_level:
                return False, 'Данный вариант недоступен, в связи с вашими предыдущими выборами'

            if user_save.passion_level < choice.passion_change:
                return False, 'Данный вариант недоступен, в связи с вашими предыдущими выборами!'

            if user_save.teasing_level < choice.teasing_change:
                return False, 'Данный вариант недоступен, в связи с вашими предыдущими выборами'

            if choice.is_locked:
                if not choice.unlocked_for_teams:
                    return False, 'Ваша команда не разблокировала ещё данный вариант!'

                teams_ids = list(map(int, choice.unlocked_for_teams.split(';')))

                if user.team_id not in teams_ids:
                    return False, 'Ваша команда не разблокировала ещё данный вариант!'

            return True, ''


    def get_current_user_scene_data(self, db: Database, user_id: int, story_id: int) -> Optional[Dict[str, Any]]:
        save_game = db.load_game(user_id, story_id)

        with Session(db.engine) as s:
            scene = s.query(Scene).filter_by(id=save_game[1]).first()
            user = s.get(User, user_id)

            return {
                'current_user_diamonds': user.diamonds,
                'character_name': scene.character_name.replace('{name}', user.display_name),
                'dialogue': scene.dialogue_text.replace('{name}', user.display_name),
                'background': scene.background_image if scene.background_image else "",
                'character_image': scene.character_image,
                'scene_type': scene.scene_type,
                'scene_id': scene.id,
                'music': scene.music_track,
                'position': {
                    'x': scene.position_x,
                    'y': scene.position_y
                },
                'scale': scene.scale,
                'choices': [
                    {
                        'data': Choice.as_dict(choice),
                        'is_available': self.is_choice_available(user.id, choice.id)[0]
                    }
                    for choice in scene.choices
                ] if scene.scene_type != 'input' else []
            }


    def update_game_stats(self, user_id: int, game_key: str,
                          play_time: int = 0, choices_made: int = 0):
        """
        Обновление статистики игры

        Args:
            user_id: ID пользователя
            game_key: Ключ игры/истории
            play_time: Время игры в секундах
            choices_made: Количество сделанных выборов
        """
        # Получение существующей статистики
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id FROM game_stats
                WHERE user_id = ? AND game_name = ?
                ORDER BY id DESC LIMIT 1
            ''', (user_id, game_key))

            result = cursor.fetchone()

            if result:
                # Обновление существующей записи
                cursor.execute('''
                    UPDATE game_stats
                    SET play_time = play_time + ?,
                        choices_made = choices_made + ?
                    WHERE id = ?
                ''', (play_time, choices_made, result['id']))
            else:
                # Создание новой записи
                self.db.create_game_stat(user_id, game_key)

    def complete_game(self, user_id: int, game_key: str, rating: int = None):
        """
        Завершение игры

        Args:
            user_id: ID пользователя
            game_key: Ключ игры/истории
            rating: Рейтинг игры (1-5)
        """
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE game_stats
                SET completed = 1,
                    rating = ?
                WHERE user_id = ? AND game_name = ?
                ORDER BY id DESC LIMIT 1
            ''', (rating, user_id, game_key))

        # Разблокировка достижения
        self.db.unlock_achievement(
            user_id,
            f'completed_{game_key}',
            f'Завершена игра "{game_key}"'
        )

    def get_user_progress(self, user_id: int) -> Dict[str, Any]:
        saves = {}

        stories = self.story_service.get_all_stories(published_only=True)

        for story in stories:
            game_saves = self.db.get_user_saves(user_id, story['story_key'])
            saves[story['story_key']] = game_saves

        stats = self.db.get_user_stats(user_id)

        return {
            'saves': saves,
            'stats': stats,
            'achievements': self.db.get_user_achievements(user_id)
        }