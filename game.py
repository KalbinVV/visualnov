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

from database import Database, Story, Scene, Chapter, User
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


    def load_game_state(self, user_id: int, game_key: str,
                        save_slot: int = 1) -> Optional[Dict[str, Any]]:

        game_state = self.db.load_game(user_id, g)

        if not game_state:
            game_state = {
                'chapter': 1,
                'scene': 1,
                'choices': [],
                'stats': {
                    'affection': 0,
                    'trust': 0,
                    'passion': 0
                },
                'unlocked': True,
                'created_at': datetime.now().isoformat()
            }

            self.db.save_game(user_id, game_key, save_slot, game_state)

        return game_state

    def save_game_state(self, user_id: int, game_key: str,
                        game_state: Dict[str, Any], save_slot: int = 1) -> bool:
        """
        Сохранение состояния игры

        Args:
            user_id: ID пользователя
            game_key: Ключ игры/истории
            game_state: Состояние игры
            save_slot: Слот сохранения

        Returns:
            True если успешно
        """
        # Обновление времени сохранения
        game_state['updated_at'] = datetime.now().isoformat()

        return self.db.save_game(user_id, game_key, save_slot, game_state)

    def make_choice(self, user_id: int, game_key: str,
                    choice_id: int, save_slot: int = 1) -> tuple[bool, str, Optional[Dict[str, Any]]]:
        """
        Сделать выбор в игре с обработкой переходов

        Args:
            user_id: ID пользователя
            game_key: Ключ игры/истории
            choice_id: ID выбора
            save_slot: Слот сохранения

        Returns:
            Кортеж (успешно, сообщение, новое состояние)
        """
        game_state = self.load_game_state(user_id, game_key, save_slot)

        if not game_state:
            return False, 'Игра не найдена', None

        # Добавление выбора в историю
        if 'choices' not in game_state:
            game_state['choices'] = []

        game_state['choices'].append({
            'choice_id': choice_id,
            'timestamp': datetime.now().isoformat(),
            'scene': game_state.get('scene', 1),
            'chapter': game_state.get('chapter', 1)
        })

        # Получаем данные варианта выбора из базы
        choice_data = self.db.get_choice_by_id(choice_id)

        if choice_data:
            # Обновляем статистику
            if 'stats' not in game_state:
                game_state['stats'] = {'affection': 0, 'trust': 0, 'passion': 0}

            game_state['stats']['affection'] = game_state['stats'].get('affection', 0) + choice_data['affection_change']
            game_state['stats']['trust'] = game_state['stats'].get('trust', 0) + choice_data['trust_change']
            game_state['stats']['passion'] = game_state['stats'].get('passion', 0) + choice_data['passion_change']

            # Обработка премиум выбора (снимаем алмазы)
            if choice_data['premium']:
                diamonds_cost = choice_data['diamonds_cost']
                if diamonds_cost > 0:
                    self.db.decrement_diamonds(user_id, diamonds_cost)

            # ===== ВАЖНО: Обработка переходов на следующую сцену или главу =====
            next_scene_id = choice_data.get('next_scene_id')
            next_chapter_id = choice_data.get('next_chapter_id')

            if next_scene_id:
                # Переход на конкретную сцену
                next_scene = self.db.get_scene_by_id(next_scene_id)
                if next_scene:
                    # Получаем главу, к которой принадлежит сцена
                    chapter = self.db.get_chapter_by_id(next_scene['chapter_id'])
                    if chapter:
                        game_state['chapter'] = chapter['chapter_number']
                        game_state['scene'] = next_scene['scene_number']
                    else:
                        return False, 'Глава для следующей сцены не найдена', None
                else:
                    return False, 'Следующая сцена не найдена', None

            elif next_chapter_id:
                # Переход на конкретную главу (начинаем с первой сцены)
                next_chapter = self.db.get_chapter_by_id(next_chapter_id)
                if next_chapter:
                    game_state['chapter'] = next_chapter['chapter_number']
                    game_state['scene'] = 1  # Начинаем с первой сцены главы
                else:
                    return False, 'Следующая глава не найдена', None

            else:
                # Продолжаем следующую сцену в текущей главе
                game_state['scene'] = game_state.get('scene', 1) + 1

        # Сохранение состояния
        success = self.save_game_state(user_id, game_key, game_state, save_slot)

        if success:
            return True, 'Выбор сделан', game_state
        else:
            return False, 'Ошибка сохранения', None

    @staticmethod
    def get_current_user_scene(db: Database, user_id: int, story_id: int) -> Optional[Dict[str, Any]]:
        save_game = db.load_game(user_id, story_id)

        with Session(db.engine) as s:
            scene = s.get(Scene, save_game.scene_id)

            return {
                'character': scene.character_name,
                'dialogue': scene.dialogue_text,
                'background': scene.background_image if scene.background_image else "",
                'character_image': scene.character_image,
                'music': scene.music_track,
                'position': {
                    'x': scene.position_x,
                    'y': scene.position_y
                },
                'scale': scene.scale,
                'choices': [
                    {
                        'id': choice.id,
                        'text': choice.choice_text,
                        'premium': choice.premium,
                        'diamonds_cost': choice.diamonds_cost,
                        'next_scene_id': choice.next_scene_id,
                        'next_chapter_id': choice.next_chapter_id,
                        'effects': {
                            'affection': choice.affection_change,
                            'trust': choice.trust_change,
                            'passion': choice.passion_change
                        }
                    }
                    for choice in scene.choices
                ]
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