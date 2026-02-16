# -*- coding: utf-8 -*-
"""
Логика игры (визуальная новелла)
Любовный симулятор
"""

import json
from datetime import datetime
from typing import Optional, Dict, Any, List
from database import Database
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

    def get_game_info(self, game_key: str) -> Optional[Dict[str, Any]]:
        """
        Получить информацию об игре/истории по ключу

        Args:
            game_key: Ключ игры/истории

        Returns:
            Информация об игре или None
        """
        # Сначала проверяем в новых историях
        story = self.story_service.get_story_by_key(game_key)

        if story:
            return {
                'key': story['story_key'],
                'title': story['title'],
                'description': story['description'] or 'Интерактивная история',
                'premium': bool(story['premium']),
                'diamonds_cost': story['diamonds_cost'],
                'chapters_count': story['chapters_count'],
                'is_published': bool(story['is_published']),
                'cover_image': story['cover_image'],
                'background_image': story['background_image']
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
            })

        return games_list

    def can_access_game(self, user_id: int, game_key: str) -> tuple[bool, str]:
        """
        Проверка доступа к игре

        Args:
            user_id: ID пользователя
            game_key: Ключ игры/истории

        Returns:
            Кортеж (доступен, сообщение)
        """
        # Сначала проверяем в новых историях
        story = self.story_service.get_story_by_key(game_key)

        if story:
            # Проверка, опубликована ли история
            if not story.get('is_published'):
                return False, 'История еще не опубликована'

            # Бесплатные истории всегда доступны
            if not story.get('premium'):
                return True, 'История доступна'

            # Проверка, куплена ли уже история (есть сохранение)
            saves = self.db.get_user_saves(user_id, game_key)
            if saves:
                return True, 'История уже куплена'

            # Проверка достаточности алмазов
            user = self.db.get_user_by_id(user_id)
            if not user:
                return False, 'Пользователь не найден'

            diamonds_cost = story.get('diamonds_cost', 0)
            if user['diamonds'] < diamonds_cost:
                return False, f'Недостаточно алмазов. Нужно {diamonds_cost}'

            return True, 'История доступна за алмазы'

        # Проверка, куплена ли уже игра (есть сохранение)
        saves = self.db.get_user_saves(user_id, game_key)
        if saves:
            return True, 'Игра уже куплена'

        # Проверка достаточности алмазов
        user = self.db.get_user_by_id(user_id)
        if not user:
            return False, 'Пользователь не найден'

        diamonds_cost = game_info.get('diamonds_cost', 0)
        if user['diamonds'] < diamonds_cost:
            return False, f'Недостаточно алмазов. Нужно {diamonds_cost}'

        return True, 'Игра доступна за алмазы'

    def purchase_game(self, user_id: int, game_key: str) -> tuple[bool, str]:
        """
        Покупка игры за алмазы

        Args:
            user_id: ID пользователя
            game_key: Ключ игры/истории

        Returns:
            Кортеж (успешно, сообщение)
        """
        accessible, message = self.can_access_game(user_id, game_key)

        if not accessible and 'Недостаточно алмазов' in message:
            return False, message

        # Определяем стоимость
        diamonds_cost = 0
        story = self.story_service.get_story_by_key(game_key)

        if story:
            diamonds_cost = story.get('diamonds_cost', 0)

        # Снимаем алмазы если нужно
        if diamonds_cost > 0:
            success = self.db.decrement_diamonds(user_id, diamonds_cost)
            if not success:
                return False, 'Недостаточно алмазов'

        # Создание начального сохранения
        initial_save = {
            'chapter': 1,
            'scene': 1,
            'choices': [],
            'stats': {
                'affection': 0,
                'trust': 0,
                'passion': 0
            },
            'unlocked': True
        }

        success = self.db.save_game(user_id, game_key, 1, initial_save)

        if success:
            return True, f'Игра куплена за {diamonds_cost} алмазов'
        else:
            # Возврат алмазов при ошибке
            if diamonds_cost > 0:
                self.db.increment_diamonds(user_id, diamonds_cost)
            return False, 'Ошибка покупки игры'

    def load_game_state(self, user_id: int, game_key: str,
                        save_slot: int = 1) -> Optional[Dict[str, Any]]:
        """
        Загрузка состояния игры

        Args:
            user_id: ID пользователя
            game_key: Ключ игры/истории
            save_slot: Слот сохранения

        Returns:
            Состояние игры или None
        """
        game_state = self.db.load_game(user_id, game_key, save_slot)

        if not game_state:
            # Создание нового сохранения
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

    def get_game_story(self, game_key: str, chapter: int,
                       scene: int) -> Optional[Dict[str, Any]]:
        """
        Получить сценарий сцены из базы данных

        Args:
            game_key: Ключ игры/истории
            chapter: Глава
            scene: Сцена

        Returns:
            Данные сцены или None
        """
        # Получаем историю по ключу
        story = self.story_service.get_story_by_key(game_key)


        # Получаем главу
        chapters = self.story_service.get_chapters_by_story(story['id'])
        chapter_data = None

        for ch in chapters:
            if ch['chapter_number'] == chapter:
                chapter_data = ch
                break

        if not chapter_data:
            return None

        # Получаем сцену
        scenes = self.story_service.get_scenes_by_chapter(chapter_data['id'])
        scene_data = None

        for sc in scenes:
            if sc['scene_number'] == scene:
                scene_data = sc
                break

        if not scene_data:
            return None

        # Получаем варианты выбора
        choices = self.story_service.get_choices_by_scene(scene_data['id'])

        # Формируем данные для возврата
        background = scene_data['background_image'] or chapter_data.get('background_image') or story.get(
            'background_image') or 'background1.jpg'

        return {
            'character': scene_data['character_name'],
            'dialogue': scene_data['dialogue_text'],
            'background': background,
            'character_image': scene_data['character_image'] or 'guy.png',
            'music': scene_data['music_track'],
            'position': {
                'x': scene_data['position_x'],
                'y': scene_data['position_y']
            },
            'scale': scene_data['scale'],
            'choices': [
                {
                    'id': choice['id'],
                    'text': choice['choice_text'],
                    'premium': bool(choice['premium']),
                    'diamonds_cost': choice['diamonds_cost'],
                    'next_scene_id': choice['next_scene_id'],
                    'next_chapter_id': choice['next_chapter_id'],
                    'effects': {
                        'affection': choice['affection_change'],
                        'trust': choice['trust_change'],
                        'passion': choice['passion_change']
                    }
                }
                for choice in choices
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