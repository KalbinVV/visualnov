# -*- coding: utf-8 -*-
"""
Сервис управления сюжетами
Любовный симулятор
"""

import json
from datetime import datetime
from typing import Optional, Dict, List, Any
from database import Database


class StoryService:
    """Сервис управления сюжетами"""

    def __init__(self, db: Database):
        """
        Инициализация сервиса

        Args:
            db: Объект базы данных
        """
        self.db = db

    # ========== CRUD для историй ==========

    def create_story(self, story_key: str, title: str, description: str = None,
                     cover_image: str = None, background_image: str = None,
                     premium: bool = False, diamonds_cost: int = 0,
                     author_id: int = None) -> Optional[int]:
        """
        Создать новую историю

        Args:
            story_key: Уникальный ключ истории
            title: Название
            description: Описание
            cover_image: Обложка
            background_image: Фоновое изображение
            premium: Премиум история
            diamonds_cost: Стоимость в алмазах
            author_id: ID автора

        Returns:
            ID созданной истории или None
        """
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute('''
                    INSERT INTO stories 
                    (story_key, title, description, cover_image, background_image,
                     premium, diamonds_cost, author_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (story_key, title, description, cover_image,
                      background_image, premium, diamonds_cost, author_id))
                return cursor.lastrowid
            except Exception as e:
                print(f"Ошибка создания истории: {e}")
                return None

    def get_story_by_id(self, story_id: int) -> Optional[Dict[str, Any]]:
        """
        Получить историю по ID

        Args:
            story_id: ID истории

        Returns:
            Данные истории или None
        """
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM stories WHERE id = ?', (story_id,))
            story = cursor.fetchone()
            return dict(story) if story else None

    def get_story_by_key(self, story_key: str) -> Optional[Dict[str, Any]]:
        """
        Получить историю по ключу

        Args:
            story_key: Ключ истории

        Returns:
            Данные истории или None
        """
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM stories WHERE story_key = ?', (story_key,))
            story = cursor.fetchone()
            return dict(story) if story else None

    def get_all_stories(self, published_only: bool = False) -> List[Dict[str, Any]]:
        """
        Получить все истории

        Args:
            published_only: Только опубликованные

        Returns:
            Список историй
        """
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            if published_only:
                cursor.execute('SELECT * FROM stories WHERE is_published = 1 ORDER BY created_at DESC')
            else:
                cursor.execute('SELECT * FROM stories ORDER BY created_at DESC')
            return [dict(row) for row in cursor.fetchall()]

    def update_story(self, story_id: int, **kwargs) -> bool:
        """
        Обновить историю

        Args:
            story_id: ID истории
            **kwargs: Поля для обновления

        Returns:
            True если успешно
        """
        allowed_fields = {
            'title', 'description', 'cover_image', 'background_image',
            'premium', 'diamonds_cost', 'chapters_count', 'scenes_count',
            'is_published'
        }

        fields_to_update = {k: v for k, v in kwargs.items() if k in allowed_fields}

        if not fields_to_update:
            return False

        set_clause = ', '.join([f'{field} = ?' for field in fields_to_update.keys()])
        values = list(fields_to_update.values()) + [story_id]

        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f'''
                UPDATE stories 
                SET {set_clause}, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', values)
            return cursor.rowcount > 0

    def delete_story(self, story_id: int) -> bool:
        """
        Удалить историю

        Args:
            story_id: ID истории

        Returns:
            True если успешно
        """
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM stories WHERE id = ?', (story_id,))
            return cursor.rowcount > 0

    # ========== CRUD для глав ==========

    def create_chapter(self, story_id: int, chapter_number: int,
                       title: str = None, description: str = None,
                       background_image: str = None) -> Optional[int]:
        """
        Создать главу

        Args:
            story_id: ID истории
            chapter_number: Номер главы
            title: Название
            description: Описание
            background_image: Фоновое изображение

        Returns:
            ID созданной главы или None
        """
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute('''
                    INSERT INTO chapters 
                    (story_id, chapter_number, title, description, background_image)
                    VALUES (?, ?, ?, ?, ?)
                ''', (story_id, chapter_number, title, description, background_image))

                # Обновить количество глав в истории
                cursor.execute('''
                    UPDATE stories 
                    SET chapters_count = (
                        SELECT COUNT(*) FROM chapters WHERE story_id = ?
                    )
                    WHERE id = ?
                ''', (story_id, story_id))

                return cursor.lastrowid
            except Exception as e:
                print(f"Ошибка создания главы: {e}")
                return None

    def get_chapter_by_id(self, chapter_id: int) -> Optional[Dict[str, Any]]:
        """
        Получить главу по ID

        Args:
            chapter_id: ID главы

        Returns:
            Данные главы или None
        """
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM chapters WHERE id = ?', (chapter_id,))
            chapter = cursor.fetchone()
            return dict(chapter) if chapter else None

    def get_chapters_by_story(self, story_id: int) -> List[Dict[str, Any]]:
        """
        Получить все главы истории

        Args:
            story_id: ID истории

        Returns:
            Список глав
        """
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM chapters 
                WHERE story_id = ? 
                ORDER BY chapter_number
            ''', (story_id,))
            return [dict(row) for row in cursor.fetchall()]

    def update_chapter(self, chapter_id: int, **kwargs) -> bool:
        """
        Обновить главу

        Args:
            chapter_id: ID главы
            **kwargs: Поля для обновления

        Returns:
            True если успешно
        """
        allowed_fields = {'title', 'description', 'background_image'}

        fields_to_update = {k: v for k, v in kwargs.items() if k in allowed_fields}

        if not fields_to_update:
            return False

        set_clause = ', '.join([f'{field} = ?' for field in fields_to_update.keys()])
        values = list(fields_to_update.values()) + [chapter_id]

        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f'UPDATE chapters SET {set_clause} WHERE id = ?', values)
            return cursor.rowcount > 0

    def delete_chapter(self, chapter_id: int) -> bool:
        """
        Удалить главу

        Args:
            chapter_id: ID главы

        Returns:
            True если успешно
        """
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM chapters WHERE id = ?', (chapter_id,))

            # Обновить количество глав
            cursor.execute('''
                UPDATE stories 
                SET chapters_count = (
                    SELECT COUNT(*) FROM chapters WHERE story_id = (
                        SELECT story_id FROM chapters WHERE id = ?
                    )
                )
                WHERE id = (
                    SELECT story_id FROM chapters WHERE id = ?
                )
            ''', (chapter_id, chapter_id))

            return cursor.rowcount > 0

    # ========== CRUD для сцен ==========

    def create_scene(self, chapter_id: int, scene_number: int,
                     character_name: str, dialogue_text: str,
                     character_image: str = None, background_image: str = None,
                     music_track: str = None, position_x: int = 0,
                     position_y: int = 0, scale: float = 1.0) -> Optional[int]:
        """
        Создать сцену

        Args:
            chapter_id: ID главы
            scene_number: Номер сцены
            character_name: Имя персонажа
            dialogue_text: Текст диалога
            character_image: Изображение персонажа
            background_image: Фоновое изображение
            music_track: Музыкальный трек
            position_x: Позиция X
            position_y: Позиция Y
            scale: Масштаб

        Returns:
            ID созданной сцены или None
        """
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute('''
                    INSERT INTO scenes 
                    (chapter_id, scene_number, character_name, dialogue_text,
                     character_image, background_image, music_track,
                     position_x, position_y, scale)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (chapter_id, scene_number, character_name, dialogue_text,
                      character_image, background_image, music_track,
                      position_x, position_y, scale))

                # Обновить количество сцен в истории
                cursor.execute('''
                    UPDATE stories 
                    SET scenes_count = (
                        SELECT COUNT(*) FROM scenes 
                        WHERE chapter_id IN (
                            SELECT id FROM chapters WHERE story_id = (
                                SELECT story_id FROM chapters WHERE id = ?
                            )
                        )
                    )
                    WHERE id = (
                        SELECT story_id FROM chapters WHERE id = ?
                    )
                ''', (chapter_id, chapter_id))

                return cursor.lastrowid
            except Exception as e:
                print(f"Ошибка создания сцены: {e}")
                return None

    def get_scene_by_id(self, scene_id: int) -> Optional[Dict[str, Any]]:
        """
        Получить сцену по ID

        Args:
            scene_id: ID сцены

        Returns:
            Данные сцены или None
        """
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM scenes WHERE id = ?', (scene_id,))
            scene = cursor.fetchone()
            return dict(scene) if scene else None

    def get_scenes_by_chapter(self, chapter_id: int) -> List[Dict[str, Any]]:
        """
        Получить все сцены главы

        Args:
            chapter_id: ID главы

        Returns:
            Список сцен
        """
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM scenes 
                WHERE chapter_id = ? 
                ORDER BY scene_number
            ''', (chapter_id,))
            return [dict(row) for row in cursor.fetchall()]

    def update_scene(self, scene_id: int, **kwargs) -> bool:
        """
        Обновить сцену

        Args:
            scene_id: ID сцены
            **kwargs: Поля для обновления

        Returns:
            True если успешно
        """
        allowed_fields = {
            'character_name', 'dialogue_text', 'character_image',
            'background_image', 'music_track', 'position_x', 'position_y',
            'scale'
        }

        fields_to_update = {k: v for k, v in kwargs.items() if k in allowed_fields}

        if not fields_to_update:
            return False

        set_clause = ', '.join([f'{field} = ?' for field in fields_to_update.keys()])
        values = list(fields_to_update.values()) + [scene_id]

        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f'UPDATE scenes SET {set_clause} WHERE id = ?', values)
            return cursor.rowcount > 0

    def delete_scene(self, scene_id: int) -> bool:
        """
        Удалить сцену

        Args:
            scene_id: ID сцены

        Returns:
            True если успешно
        """
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM scenes WHERE id = ?', (scene_id,))

            # Обновить количество сцен
            cursor.execute('''
                UPDATE stories 
                SET scenes_count = (
                    SELECT COUNT(*) FROM scenes 
                    WHERE chapter_id IN (
                        SELECT id FROM chapters WHERE story_id = (
                            SELECT story_id FROM chapters WHERE id = (
                                SELECT chapter_id FROM scenes WHERE id = ?
                            )
                        )
                    )
                )
                WHERE id = (
                    SELECT story_id FROM chapters WHERE id = (
                        SELECT chapter_id FROM scenes WHERE id = ?
                    )
                )
            ''', (scene_id, scene_id))

            return cursor.rowcount > 0

    # ========== CRUD для вариантов выбора ==========

    def create_choice(self, scene_id: int, choice_number: int,
                      choice_text: str, next_scene_id: int = None,
                      next_chapter_id: int = None, effect_type: str = None,
                      effect_data: str = None, premium: bool = False,
                      diamonds_cost: int = 0, affection_change: int = 0,
                      trust_change: int = 0, passion_change: int = 0,
                      unlock_condition: str = None) -> Optional[int]:
        """
        Создать вариант выбора

        Args:
            scene_id: ID сцены
            choice_number: Номер варианта
            choice_text: Текст варианта
            next_scene_id: ID следующей сцены
            next_chapter_id: ID следующей главы
            effect_type: Тип эффекта
            effect_data: Данные эффекта
            premium: Премиум вариант
            diamonds_cost: Стоимость в алмазах
            affection_change: Изменение привязанности
            trust_change: Изменение доверия
            passion_change: Изменение страсти
            unlock_condition: Условие разблокировки

        Returns:
            ID созданного варианта или None
        """
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute('''
                    INSERT INTO choices 
                    (scene_id, choice_number, choice_text, next_scene_id,
                     next_chapter_id, effect_type, effect_data, premium,
                     diamonds_cost, affection_change, trust_change,
                     passion_change, unlock_condition)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (scene_id, choice_number, choice_text, next_scene_id,
                      next_chapter_id, effect_type, effect_data, premium,
                      diamonds_cost, affection_change, trust_change,
                      passion_change, unlock_condition))
                return cursor.lastrowid
            except Exception as e:
                print(f"Ошибка создания варианта: {e}")
                return None

    def get_choices_by_scene(self, scene_id: int) -> List[Dict[str, Any]]:
        """
        Получить все варианты выбора для сцены

        Args:
            scene_id: ID сцены

        Returns:
            Список вариантов
        """
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM choices 
                WHERE scene_id = ? 
                ORDER BY choice_number
            ''', (scene_id,))
            return [dict(row) for row in cursor.fetchall()]

    def update_choice(self, choice_id: int, **kwargs) -> bool:
        """
        Обновить вариант выбора

        Args:
            choice_id: ID варианта
            **kwargs: Поля для обновления

        Returns:
            True если успешно
        """
        allowed_fields = {
            'choice_text', 'next_scene_id', 'next_chapter_id',
            'effect_type', 'effect_data', 'premium', 'diamonds_cost',
            'affection_change', 'trust_change', 'passion_change',
            'unlock_condition'
        }

        fields_to_update = {k: v for k, v in kwargs.items() if k in allowed_fields}

        if not fields_to_update:
            return False

        set_clause = ', '.join([f'{field} = ?' for field in fields_to_update.keys()])
        values = list(fields_to_update.values()) + [choice_id]

        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f'UPDATE choices SET {set_clause} WHERE id = ?', values)
            return cursor.rowcount > 0

    def delete_choice(self, choice_id: int) -> bool:
        """
        Удалить вариант выбора

        Args:
            choice_id: ID варианта

        Returns:
            True если успешно
        """
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM choices WHERE id = ?', (choice_id,))
            return cursor.rowcount > 0

    # ========== Экспорт/Импорт сюжета ==========

    def export_story(self, story_id: int) -> Optional[Dict[str, Any]]:
        """
        Экспортировать историю в JSON

        Args:
            story_id: ID истории

        Returns:
            Словарь с данными истории или None
        """
        story = self.get_story_by_id(story_id)
        if not story:
            return None

        chapters = self.get_chapters_by_story(story_id)

        story_data = {
            'story_key': story['story_key'],
            'title': story['title'],
            'description': story['description'],
            'cover_image': story['cover_image'],
            'background_image': story['background_image'],
            'premium': bool(story['premium']),
            'diamonds_cost': story['diamonds_cost'],
            'chapters': []
        }

        for chapter in chapters:
            scenes = self.get_scenes_by_chapter(chapter['id'])
            chapter_data = {
                'chapter_number': chapter['chapter_number'],
                'title': chapter['title'],
                'description': chapter['description'],
                'background_image': chapter['background_image'],
                'scenes': []
            }

            for scene in scenes:
                choices = self.get_choices_by_scene(scene['id'])
                scene_data = {
                    'scene_number': scene['scene_number'],
                    'character_name': scene['character_name'],
                    'character_image': scene['character_image'],
                    'dialogue_text': scene['dialogue_text'],
                    'background_image': scene['background_image'],
                    'music_track': scene['music_track'],
                    'position': {
                        'x': scene['position_x'],
                        'y': scene['position_y']
                    },
                    'scale': scene['scale'],
                    'choices': []
                }

                for choice in choices:
                    choice_data = {
                        'choice_number': choice['choice_number'],
                        'choice_text': choice['choice_text'],
                        'next_scene_id': choice['next_scene_id'],
                        'next_chapter_id': choice['next_chapter_id'],
                        'effect_type': choice['effect_type'],
                        'premium': bool(choice['premium']),
                        'diamonds_cost': choice['diamonds_cost'],
                        'stats_changes': {
                            'affection': choice['affection_change'],
                            'trust': choice['trust_change'],
                            'passion': choice['passion_change']
                        },
                        'unlock_condition': choice['unlock_condition']
                    }
                    scene_data['choices'].append(choice_data)

                chapter_data['scenes'].append(scene_data)

            story_data['chapters'].append(chapter_data)

        return story_data

    def import_story(self, story_data: Dict[str, Any], author_id: int = None) -> Optional[int]:
        """
        Импортировать историю из JSON

        Args:
            story_data: Данные истории
            author_id: ID автора

        Returns:
            ID созданной истории или None
        """
        # Создать историю
        story_id = self.create_story(
            story_key=story_data['story_key'],
            title=story_data['title'],
            description=story_data.get('description'),
            cover_image=story_data.get('cover_image'),
            background_image=story_data.get('background_image'),
            premium=story_data.get('premium', False),
            diamonds_cost=story_data.get('diamonds_cost', 0),
            author_id=author_id
        )

        if not story_id:
            return None

        # Создать главы
        for chapter_data in story_data.get('chapters', []):
            chapter_id = self.create_chapter(
                story_id=story_id,
                chapter_number=chapter_data['chapter_number'],
                title=chapter_data.get('title'),
                description=chapter_data.get('description'),
                background_image=chapter_data.get('background_image')
            )

            if not chapter_id:
                continue

            # Создать сцены
            for scene_data in chapter_data.get('scenes', []):
                scene_id = self.create_scene(
                    chapter_id=chapter_id,
                    scene_number=scene_data['scene_number'],
                    character_name=scene_data['character_name'],
                    dialogue_text=scene_data['dialogue_text'],
                    character_image=scene_data.get('character_image'),
                    background_image=scene_data.get('background_image'),
                    music_track=scene_data.get('music_track'),
                    position_x=scene_data.get('position', {}).get('x', 0),
                    position_y=scene_data.get('position', {}).get('y', 0),
                    scale=scene_data.get('scale', 1.0)
                )

                if not scene_id:
                    continue

                # Создать варианты выбора
                for choice_data in scene_data.get('choices', []):
                    self.create_choice(
                        scene_id=scene_id,
                        choice_number=choice_data['choice_number'],
                        choice_text=choice_data['choice_text'],
                        next_scene_id=choice_data.get('next_scene_id'),
                        next_chapter_id=choice_data.get('next_chapter_id'),
                        effect_type=choice_data.get('effect_type'),
                        premium=choice_data.get('premium', False),
                        diamonds_cost=choice_data.get('diamonds_cost', 0),
                        affection_change=choice_data.get('stats_changes', {}).get('affection', 0),
                        trust_change=choice_data.get('stats_changes', {}).get('trust', 0),
                        passion_change=choice_data.get('stats_changes', {}).get('passion', 0),
                        unlock_condition=choice_data.get('unlock_condition')
                    )

        return story_id

    # ========== Получение сюжетных данных для игры ==========

    def get_story_content(self, story_key: str, chapter_number: int = 1,
                          scene_number: int = 1) -> Optional[Dict[str, Any]]:
        """
        Получить контент сцены для игры

        Args:
            story_key: Ключ истории
            chapter_number: Номер главы
            scene_number: Номер сцены

        Returns:
            Данные сцены или None
        """
        story = self.get_story_by_key(story_key)
        if not story:
            return None

        # Получить главу
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM chapters 
                WHERE story_id = ? AND chapter_number = ?
            ''', (story['id'], chapter_number))
            chapter = cursor.fetchone()

            if not chapter:
                return None

            # Получить сцену
            cursor.execute('''
                SELECT * FROM scenes 
                WHERE chapter_id = ? AND scene_number = ?
            ''', (chapter['id'], scene_number))
            scene = cursor.fetchone()

            if not scene:
                return None

            # Получить варианты выбора
            cursor.execute('''
                SELECT * FROM choices 
                WHERE scene_id = ? 
                ORDER BY choice_number
            ''', (scene['id'],))
            choices = [dict(row) for row in cursor.fetchall()]

            return {
                'story': dict(story),
                'chapter': dict(chapter),
                'scene': dict(scene),
                'choices': choices
            }