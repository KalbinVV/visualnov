# -*- coding: utf-8 -*-
"""
Сервис управления сюжетами
Любовный симулятор — версия на SQLAlchemy ORM
"""

from datetime import datetime
from typing import Optional, List, Dict, Any

from sqlalchemy import func, select, update, delete
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from database import Database, Story, Chapter, Scene, Choice  # Импортируем модели явно


class StoryService:
    """Сервис управления сюжетами на ORM"""

    def __init__(self, db: Database):
        """
        Инициализация сервиса

        Args:
            db: Объект базы данных (ORM)
        """
        self.db = db

    # ========== CRUD для историй ==========

    def create_story(
        self,
        story_key: str,
        title: str,
        description: Optional[str] = None,
        cover_image: Optional[str] = None,
        background_image: Optional[str] = None,
        premium: bool = False,
        diamonds_cost: int = 0,
        author_id: Optional[int] = None
    ) -> Optional[int]:
        """
        Создать новую историю

        Returns:
            ID созданной истории или None
        """
        with self.db.get_session() as s:
            try:
                story = Story(
                    story_key=story_key,
                    title=title,
                    description=description,
                    cover_image=cover_image,
                    background_image=background_image,
                    premium=premium,
                    diamonds_cost=diamonds_cost,
                    author_id=author_id,
                    chapters_count=0,
                    scenes_count=0,
                    is_published=False
                )
                s.add(story)
                s.flush()  # Получаем ID без коммита
                return story.id
            except IntegrityError:
                s.rollback()
                return None
            except Exception as e:
                s.rollback()
                print(f"Ошибка создания истории: {e}")
                return None

    def get_story_by_id(self, story_id: int) -> Optional[Story]:
        """
        Получить историю по ID
        """
        with self.db.get_session() as s:
            return s.get(Story, story_id)

    def get_story_by_key(self, story_key: str) -> Optional[Story]:
        """
        Получить историю по ключу
        """
        with self.db.get_session() as s:
            return s.scalar(select(Story).where(Story.story_key == story_key))

    def get_all_stories(self, published_only: bool = False) -> List[Story]:
        """
        Получить все истории
        """
        with self.db.get_session() as s:
            stmt = select(Story).order_by(Story.created_at.desc())
            if published_only:
                stmt = stmt.where(Story.is_published == True)
            return s.scalars(stmt).all()

    def update_story(self, story_id: int, **kwargs) -> bool:
        """
        Обновить историю
        """
        allowed_fields = {
            'title', 'description', 'cover_image', 'background_image',
            'premium', 'diamonds_cost', 'chapters_count', 'scenes_count',
            'is_published'
        }
        data = {k: v for k, v in kwargs.items() if k in allowed_fields}

        if not data:
            return False

        with self.db.get_session() as s:
            stmt = (
                update(Story)
                .where(Story.id == story_id)
                .values(**data, updated_at=func.now())
            )
            result = s.execute(stmt)
            return result.rowcount > 0

    def delete_story(self, story_id: int) -> bool:
        """
        Удалить историю (каскадно удалит главы, сцены и т.д.)
        """
        with self.db.get_session() as s:
            story = s.get(Story, story_id)
            if not story:
                return False
            s.delete(story)
            return True

    # ========== CRUD для глав ==========

    def create_chapter(
        self,
        story_id: int,
        chapter_number: int,
        title: Optional[str] = None,
        description: Optional[str] = None,
        background_image: Optional[str] = None
    ) -> Optional[int]:
        """
        Создать главу
        """
        with self.db.get_session() as s:
            try:
                chapter = Chapter(
                    story_id=story_id,
                    chapter_number=chapter_number,
                    title=title,
                    description=description,
                    background_image=background_image
                )
                s.add(chapter)
                s.flush()

                # Обновить chapters_count в истории
                s.execute(
                    update(Story)
                    .where(Story.id == story_id)
                    .values(chapters_count=select(func.count(Chapter.id)).where(Chapter.story_id == story_id))
                )

                return chapter.id
            except IntegrityError:
                s.rollback()
                return None
            except Exception as e:
                s.rollback()
                print(f"Ошибка создания главы: {e}")
                return None

    def get_chapter_by_id(self, chapter_id: int) -> Optional[Chapter]:
        """
        Получить главу по ID
        """
        with self.db.get_session() as s:
            return s.get(Chapter, chapter_id)

    def get_chapters_by_story(self, story_id: int) -> List[Chapter]:
        """
        Получить все главы истории
        """
        with self.db.get_session() as s:
            return s.scalars(
                select(Chapter)
                .where(Chapter.story_id == story_id)
                .order_by(Chapter.chapter_number)
            ).all()

    def update_chapter(self, chapter_id: int, **kwargs) -> bool:
        """
        Обновить главу
        """
        allowed_fields = {'title', 'description', 'background_image'}
        data = {k: v for k, v in kwargs.items() if k in allowed_fields}

        if not data:
            return False

        with self.db.get_session() as s:
            stmt = (
                update(Chapter)
                .where(Chapter.id == chapter_id)
                .values(**data)
            )
            result = s.execute(stmt)
            return result.rowcount > 0

    def delete_chapter(self, chapter_id: int) -> bool:
        """
        Удалить главу (каскадно удалит сцены)
        """
        with self.db.get_session() as s:
            chapter = s.get(Chapter, chapter_id)
            if not chapter:
                return False

            story_id = chapter.story_id
            s.delete(chapter)
            s.flush()  # Обеспечиваем удаление перед обновлением счётчика

            # Обновить chapters_count
            s.execute(
                update(Story)
                .where(Story.id == story_id)
                .values(chapters_count=select(func.count(Chapter.id)).where(Chapter.story_id == story_id))
            )

            return True

    # ========== CRUD для сцен ==========

    def create_scene(
        self,
        chapter_id: int,
        scene_number: int,
        character_name: str,
        dialogue_text: str,
        character_image: Optional[str] = None,
        background_image: Optional[str] = None,
        music_track: Optional[str] = None,
        position_x: int = 0,
        position_y: int = 0,
        scale: float = 1.0,
        effects: Optional[str] = None  # Добавлено поле effects из модели
    ) -> Optional[int]:
        """
        Создать сцену
        """
        with self.db.get_session() as s:
            try:
                scene = Scene(
                    chapter_id=chapter_id,
                    scene_number=scene_number,
                    character_name=character_name,
                    dialogue_text=dialogue_text,
                    character_image=character_image,
                    background_image=background_image,
                    music_track=music_track,
                    position_x=position_x,
                    position_y=position_y,
                    scale=scale,
                    effects=effects
                )
                s.add(scene)
                s.flush()

                # Обновить scenes_count в истории (упрощённый subquery)
                story_id_sub = select(Chapter.story_id).where(Chapter.id == chapter_id).scalar_subquery()
                scenes_count_sub = (
                    select(func.count(Scene.id))
                    .where(Scene.chapter_id.in_(select(Chapter.id).where(Chapter.story_id == Story.id)))
                    .scalar_subquery()
                )
                s.execute(
                    update(Story)
                    .where(Story.id == story_id_sub)
                    .values(scenes_count=scenes_count_sub)
                )

                return scene.id
            except IntegrityError:
                s.rollback()
                return None
            except Exception as e:
                s.rollback()
                print(f"Ошибка создания сцены: {e}")
                return None

    def get_scene_by_id(self, scene_id: int) -> Optional[Scene]:
        """
        Получить сцену по ID
        """
        with self.db.get_session() as s:
            return s.get(Scene, scene_id)

    def get_scenes_by_chapter(self, chapter_id: int) -> List[Scene]:
        """
        Получить все сцены главы
        """
        with self.db.get_session() as s:
            return s.scalars(
                select(Scene)
                .where(Scene.chapter_id == chapter_id)
                .order_by(Scene.scene_number)
            ).all()

    def update_scene(self, scene_id: int, **kwargs) -> bool:
        """
        Обновить сцену
        """
        allowed_fields = {
            'character_name', 'dialogue_text', 'character_image',
            'background_image', 'music_track', 'position_x', 'position_y',
            'scale', 'effects'  # Добавлено поле effects
        }
        data = {k: v for k, v in kwargs.items() if k in allowed_fields}

        if not data:
            return False

        with self.db.get_session() as s:
            stmt = (
                update(Scene)
                .where(Scene.id == scene_id)
                .values(**data)
            )
            result = s.execute(stmt)
            return result.rowcount > 0

    def delete_scene(self, scene_id: int) -> bool:
        """
        Удалить сцену (каскадно удалит choices)
        """
        with self.db.get_session() as s:
            scene = s.get(Scene, scene_id)
            if not scene:
                return False

            chapter_id = scene.chapter_id
            story_id = s.scalar(select(Chapter.story_id).where(Chapter.id == chapter_id))
            s.delete(scene)
            s.flush()  # Обеспечиваем удаление перед обновлением счётчика

            # Обновить scenes_count
            scenes_count_sub = (
                select(func.count(Scene.id))
                .where(Scene.chapter_id.in_(select(Chapter.id).where(Chapter.story_id == Story.id)))
                .scalar_subquery()
            )
            s.execute(
                update(Story)
                .where(Story.id == story_id)
                .values(scenes_count=scenes_count_sub)
            )

            return True

    # ========== CRUD для вариантов выбора ==========

    def create_choice(
        self,
        scene_id: int,
        choice_number: int,
        choice_text: str,
        next_scene_id: Optional[int] = None,
        next_chapter_id: Optional[int] = None,
        effect_type: Optional[str] = None,
        effect_data: Optional[str] = None,
        premium: bool = False,
        diamonds_cost: int = 0,
        affection_change: int = 0,
        trust_change: int = 0,
        passion_change: int = 0,
        unlock_condition: Optional[str] = None,
        only_leader: Optional[bool] = None,
        is_locked: bool = False
    ) -> Optional[int]:
        """
        Создать вариант выбора
        """
        with self.db.get_session() as s:
            try:
                choice = Choice(
                    scene_id=scene_id,
                    choice_number=choice_number,
                    choice_text=choice_text,
                    next_scene_id=next_scene_id,
                    next_chapter_id=next_chapter_id,
                    effect_type=effect_type,
                    effect_data=effect_data,
                    premium=premium,
                    diamonds_cost=diamonds_cost,
                    affection_change=affection_change,
                    trust_change=trust_change,
                    passion_change=passion_change,
                    unlock_condition=unlock_condition,
                    only_leader=only_leader,
                    is_locked=is_locked
                )
                s.add(choice)
                s.flush()
                return choice.id
            except IntegrityError:
                s.rollback()
                return None
            except Exception as e:
                s.rollback()
                print(f"Ошибка создания варианта: {e}")
                return None

    def get_choice_by_id(self, choice_id: int) -> Optional[Choice]:
        """
        Получить вариант выбора по ID
        """
        with self.db.get_session() as s:
            return s.get(Choice, choice_id)

    def get_choices_by_scene(self, scene_id: int) -> List[Choice]:
        """
        Получить все варианты выбора для сцены
        """
        with self.db.get_session() as s:
            return s.scalars(
                select(Choice)
                .where(Choice.scene_id == scene_id)
                .order_by(Choice.choice_number)
            ).all()

    def update_choice(self, choice_id: int, **kwargs) -> bool:
        """
        Обновить вариант выбора
        """
        allowed_fields = {
            'choice_text', 'next_scene_id', 'next_chapter_id',
            'effect_type', 'effect_data', 'premium', 'diamonds_cost',
            'affection_change', 'trust_change', 'passion_change',
            'unlock_condition', 'only_leader', 'is_locked'
        }
        data = {k: v for k, v in kwargs.items() if k in allowed_fields}

        if not data:
            return False

        with self.db.get_session() as s:
            stmt = (
                update(Choice)
                .where(Choice.id == choice_id)
                .values(**data)
            )
            result = s.execute(stmt)
            return result.rowcount > 0

    def delete_choice(self, choice_id: int) -> bool:
        """
        Удалить вариант выбора
        """
        with self.db.get_session() as s:
            choice = s.get(Choice, choice_id)
            if not choice:
                return False
            s.delete(choice)
            return True

    # ========== Экспорт/Импорт сюжета ==========

    def export_story(self, story_id: int) -> Optional[Dict[str, Any]]:
        """
        Экспортировать историю в JSON-структуру
        """
        story = self.get_story_by_id(story_id)
        if not story:
            return None

        chapters = self.get_chapters_by_story(story_id)

        story_data: Dict[str, Any] = {
            'story_key': story.story_key,
            'title': story.title,
            'description': story.description,
            'cover_image': story.cover_image,
            'background_image': story.background_image,
            'premium': story.premium,
            'diamonds_cost': story.diamonds_cost,
            'chapters': []
        }

        for chapter in chapters:
            scenes = self.get_scenes_by_chapter(chapter.id)
            chapter_data: Dict[str, Any] = {
                'chapter_number': chapter.chapter_number,
                'title': chapter.title,
                'description': chapter.description,
                'background_image': chapter.background_image,
                'scenes': []
            }

            for scene in scenes:
                choices = self.get_choices_by_scene(scene.id)
                scene_data: Dict[str, Any] = {
                    'scene_number': scene.scene_number,
                    'character_name': scene.character_name,
                    'character_image': scene.character_image,
                    'dialogue_text': scene.dialogue_text,
                    'background_image': scene.background_image,
                    'music_track': scene.music_track,
                    'effects': scene.effects,  # Добавлено поле effects
                    'position': {
                        'x': scene.position_x,
                        'y': scene.position_y
                    },
                    'scale': scene.scale,
                    'choices': []
                }

                for choice in choices:
                    scene_data['choices'].append({
                        'choice_number': choice.choice_number,
                        'choice_text': choice.choice_text,
                        'next_scene_id': choice.next_scene_id,
                        'next_chapter_id': choice.next_chapter_id,
                        'effect_type': choice.effect_type,
                        'effect_data': choice.effect_data,
                        'premium': choice.premium,
                        'diamonds_cost': choice.diamonds_cost,
                        'stats_changes': {
                            'affection': choice.affection_change,
                            'trust': choice.trust_change,
                            'passion': choice.passion_change
                        },
                        'unlock_condition': choice.unlock_condition,
                        'only_leader': choice.only_leader,
                        'is_locked': choice.is_locked
                    })

                chapter_data['scenes'].append(scene_data)

            story_data['chapters'].append(chapter_data)

        return story_data

    def import_story(self, story_data: Dict[str, Any], author_id: Optional[int] = None) -> Optional[int]:
        """
        Импортировать историю из JSON
        """
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

        # Создать главы (с обработкой ошибок, но продолжаем импорт)
        for chapter_data in story_data.get('chapters', []):
            chapter_id = self.create_chapter(
                story_id=story_id,
                chapter_number=chapter_data['chapter_number'],
                title=chapter_data.get('title'),
                description=chapter_data.get('description'),
                background_image=chapter_data.get('background_image')
            )

            if not chapter_id:
                print(f"Пропуск главы {chapter_data.get('chapter_number')}: ошибка создания")
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
                    scale=scene_data.get('scale', 1.0),
                    effects=scene_data.get('effects')  # Добавлено поле effects
                )

                if not scene_id:
                    print(f"Пропуск сцены {scene_data['scene_number']}: ошибка создания")
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
                        effect_data=choice_data.get('effect_data'),
                        premium=choice_data.get('premium', False),
                        diamonds_cost=choice_data.get('diamonds_cost', 0),
                        affection_change=choice_data.get('stats_changes', {}).get('affection', 0),
                        trust_change=choice_data.get('stats_changes', {}).get('trust', 0),
                        passion_change=choice_data.get('stats_changes', {}).get('passion', 0),
                        unlock_condition=choice_data.get('unlock_condition'),
                        only_leader=choice_data.get('only_leader'),
                        is_locked=choice_data.get('is_locked', False)
                    )

        return story_id

    # ========== Получение сюжетных данных для игры ==========

    def get_story_content(
        self,
        story_key: str,
        chapter_number: int = 1,
        scene_number: int = 1
    ) -> Optional[Dict[str, Any]]:
        """
        Получить контент сцены для игры (возвращает dict для совместимости)
        """
        with self.db.get_session() as s:
            story = s.scalar(select(Story).where(Story.story_key == story_key))
            if not story:
                return None

            chapter = s.scalar(
                select(Chapter)
                .where(Chapter.story_id == story.id, Chapter.chapter_number == chapter_number)
            )
            if not chapter:
                return None

            scene = s.scalar(
                select(Scene)
                .where(Scene.chapter_id == chapter.id, Scene.scene_number == scene_number)
            )
            if not scene:
                return None

            choices = s.scalars(
                select(Choice)
                .where(Choice.scene_id == scene.id)
                .order_by(Choice.choice_number)
            ).all()

            return {
                'story': {
                    'id': story.id,
                    'story_key': story.story_key,
                    'title': story.title,
                    'description': story.description,
                    'cover_image': story.cover_image,
                    'background_image': story.background_image,
                    'premium': story.premium,
                    'diamonds_cost': story.diamonds_cost
                },
                'chapter': {
                    'id': chapter.id,
                    'chapter_number': chapter.chapter_number,
                    'title': chapter.title,
                    'description': chapter.description,
                    'background_image': chapter.background_image
                },
                'scene': {
                    'id': scene.id,
                    'scene_number': scene.scene_number,
                    'character_name': scene.character_name,
                    'character_image': scene.character_image,
                    'dialogue_text': scene.dialogue_text,
                    'background_image': scene.background_image,
                    'music_track': scene.music_track,
                    'effects': scene.effects,  # Добавлено поле effects
                    'position_x': scene.position_x,
                    'position_y': scene.position_y,
                    'scale': scene.scale
                },
                'choices': [
                    {
                        'id': c.id,
                        'choice_number': c.choice_number,
                        'choice_text': c.choice_text,
                        'next_scene_id': c.next_scene_id,
                        'next_chapter_id': c.next_chapter_id,
                        'effect_type': c.effect_type,
                        'effect_data': c.effect_data,  # Добавлено поле effect_data
                        'premium': c.premium,
                        'diamonds_cost': c.diamonds_cost,
                        'affection_change': c.affection_change,
                        'trust_change': c.trust_change,
                        'passion_change': c.passion_change,
                        'unlock_condition': c.unlock_condition,
                        'only_leader': c.only_leader,
                        'is_locked': c.is_locked
                    }
                    for c in choices
                ]
            }