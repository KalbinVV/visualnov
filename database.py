# -*- coding: utf-8 -*-
"""
Модуль работы с базой данных (SQLAlchemy ORM)
Любовный симулятор
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
import json
from uuid import uuid4

from flask import session
from sqlalchemy import (
    create_engine,
    String,
    Text,
    Boolean,
    Integer,
    ForeignKey,
    DateTime,
    Float,
    func,
    select,
    update,
    delete,
    UniqueConstraint, Connection, UUID,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
    Session,
    sessionmaker,
    joinedload,
)
from sqlalchemy.exc import IntegrityError
from contextlib import contextmanager


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    password_salt: Mapped[str] = mapped_column(String(128), nullable=False)
    display_name: Mapped[Optional[str]] = mapped_column(String(100))
    avatar_url: Mapped[Optional[str]] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    last_login: Mapped[Optional[datetime]] = mapped_column(DateTime)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    failed_login_attempts: Mapped[int] = mapped_column(default=0)
    locked_until: Mapped[Optional[datetime]] = mapped_column(DateTime)
    diamonds: Mapped[int] = mapped_column(default=0)
    is_leader: Mapped[bool] = mapped_column(Boolean, default=False)
    theme: Mapped[str] = mapped_column(String(50), default="orange")
    settings: Mapped[str] = mapped_column(Text, default="{}")
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"), nullable=True)

    user_sessions: Mapped[List["UserSession"]] = relationship(
        "UserSession", back_populates="user", cascade="all, delete-orphan"
    )
    game_stats: Mapped[List["GameStat"]] = relationship(
        "GameStat", back_populates="user", cascade="all, delete-orphan"
    )
    achievements: Mapped[List["Achievement"]] = relationship(
        "Achievement", back_populates="user", cascade="all, delete-orphan"
    )
    authored_stories: Mapped[List["Story"]] = relationship(
        "Story", back_populates="author", foreign_keys="[Story.author_id]"
    )

    team: Mapped["Team"] = relationship()


class DiamondCode(Base):
    __tablename__ = 'diamond_codes'

    code: Mapped[UUID] = mapped_column(UUID, primary_key=True, default=uuid4)
    value: Mapped[int] = mapped_column(Integer, nullable=False)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)


class DiamondCodesHistory(Base):
    __tablename__ = 'diamond_codes_history'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    diamond_code_uuid: Mapped[UUID] = mapped_column(ForeignKey('diamond_codes.code', ondelete='CASCADE'), nullable=False)


class TeamCode(Base):
    __tablename__ = 'team_codes'

    code: Mapped[UUID] = mapped_column(UUID, primary_key=True, default=uuid4)
    team_id: Mapped[int] = mapped_column(ForeignKey('teams.id', ondelete='CASCADE'), nullable=False)


class Team(Base):
    __tablename__ = 'teams'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    icon: Mapped[str] = mapped_column(String, nullable=True)

    users: Mapped[List[User]] = relationship()


class UserSession(Base):
    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    session_token: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    ip_address: Mapped[Optional[str]] = mapped_column(String(45))
    user_agent: Mapped[Optional[str]] = mapped_column(Text)

    user: Mapped["User"] = relationship("User", back_populates="user_sessions")


class Story(Base):
    __tablename__ = "stories"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    story_key: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    cover_image: Mapped[Optional[str]] = mapped_column(String(255))
    background_image: Mapped[Optional[str]] = mapped_column(String(255))
    premium: Mapped[bool] = mapped_column(default=False)
    diamonds_cost: Mapped[int] = mapped_column(default=0)
    chapters_count: Mapped[int] = mapped_column(default=0)
    scenes_count: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
    is_published: Mapped[bool] = mapped_column(default=False)
    author_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"))

    author: Mapped[Optional["User"]] = relationship("User", back_populates="authored_stories")
    chapters: Mapped[List["Chapter"]] = relationship("Chapter", back_populates="story", cascade="all, delete-orphan")
    story_characters: Mapped[List["StoryCharacter"]] = relationship("StoryCharacter", back_populates="story", cascade="all, delete-orphan")


class GameSave(Base):
    __tablename__ = "game_saves"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    story_id: Mapped[int] = mapped_column(ForeignKey("stories.id", ondelete="CASCADE"), nullable=False)
    scene_id: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    chapter_id: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    teasing_level: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    friendship_level: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    passion_level: Mapped[int] = mapped_column(Integer, nullable=False, default=0)



class GameStat(Base):
    __tablename__ = "game_stats"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    game_name: Mapped[str] = mapped_column(String(100), nullable=False)
    play_time: Mapped[int] = mapped_column(default=0)
    completed: Mapped[bool] = mapped_column(default=False)
    rating: Mapped[Optional[int]] = mapped_column()
    choices_made: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    user: Mapped["User"] = relationship("User", back_populates="game_stats")


class Achievement(Base):
    __tablename__ = "achievements"
    __table_args__ = (UniqueConstraint("user_id", "achievement_name", name="uq_achievement"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    achievement_name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    unlocked_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    user: Mapped["User"] = relationship("User", back_populates="achievements")


class Chapter(Base):
    __tablename__ = "chapters"
    __table_args__ = (UniqueConstraint("story_id", "chapter_number", name="uq_chapter"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    story_id: Mapped[int] = mapped_column(ForeignKey("stories.id", ondelete="CASCADE"), nullable=False)
    chapter_number: Mapped[int] = mapped_column(nullable=False)
    title: Mapped[Optional[str]] = mapped_column(String(200))
    description: Mapped[Optional[str]] = mapped_column(Text)
    background_image: Mapped[Optional[str]] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    story: Mapped["Story"] = relationship("Story", back_populates="chapters")
    scenes: Mapped[List["Scene"]] = relationship("Scene", back_populates="chapter", cascade="all, delete-orphan")


class Scene(Base):
    __tablename__ = "scenes"
    __table_args__ = (UniqueConstraint("chapter_id", "scene_number", name="uq_scene"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    chapter_id: Mapped[int] = mapped_column(ForeignKey("chapters.id", ondelete="CASCADE"), nullable=False)
    scene_number: Mapped[int] = mapped_column(nullable=False)
    character_name: Mapped[str] = mapped_column(String(100), nullable=False)
    character_image: Mapped[Optional[str]] = mapped_column(String(255))
    dialogue_text: Mapped[str] = mapped_column(Text, nullable=False)
    background_image: Mapped[Optional[str]] = mapped_column(String(255))
    music_track: Mapped[Optional[str]] = mapped_column(String(255))
    effects: Mapped[Optional[str]] = mapped_column(Text)  # JSON
    position_x: Mapped[int] = mapped_column(default=0)
    position_y: Mapped[int] = mapped_column(default=0)
    scale: Mapped[float] = mapped_column(Float, default=1.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    scene_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    chapter: Mapped["Chapter"] = relationship("Chapter", back_populates="scenes")

    choices: Mapped[List["Choice"]] = relationship(
        "Choice",
        back_populates="scene",
        cascade="all, delete-orphan",
        foreign_keys="Choice.scene_id",
    )


class Choice(Base):
    __tablename__ = "choices"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    scene_id: Mapped[int] = mapped_column(ForeignKey("scenes.id", ondelete="CASCADE"), nullable=False)
    choice_number: Mapped[int] = mapped_column(nullable=False)
    choice_text: Mapped[str] = mapped_column(String(255), nullable=False)
    next_scene_id: Mapped[Optional[int]] = mapped_column(ForeignKey("scenes.id"))
    next_chapter_id: Mapped[Optional[int]] = mapped_column(ForeignKey("chapters.id"))
    effect_type: Mapped[Optional[str]] = mapped_column(String(50))
    effect_data: Mapped[Optional[str]] = mapped_column(Text)  # JSON
    premium: Mapped[bool] = mapped_column(default=False)
    diamonds_cost: Mapped[int] = mapped_column(default=0)
    teasing_change: Mapped[int] = mapped_column(default=0)
    friendship_change: Mapped[int] = mapped_column(default=0)
    passion_change: Mapped[int] = mapped_column(default=0)
    unlock_condition: Mapped[Optional[str]] = mapped_column(String(255))
    only_leader: Mapped[bool] = mapped_column(Boolean, default=False)
    is_locked: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    is_legend_choice: Mapped[bool] = mapped_column(Boolean, default=False)
    is_important_choice: Mapped[bool] = mapped_column(Boolean, default=False)
    legend_title: Mapped[str] = mapped_column(String, nullable=True)
    legend_icon: Mapped[str] = mapped_column(String, nullable=True)
    required_teasing_level: Mapped[str] = mapped_column(Integer, default=0)
    required_passion_level: Mapped[str] = mapped_column(Integer, default=0)
    required_friendship_level: Mapped[str] = mapped_column(Integer, default=0)
    unlocked_for_teams: Mapped[str] = mapped_column(String, nullable=False)

    scene: Mapped["Scene"] = relationship(
        "Scene",
        back_populates="choices",
        foreign_keys=[scene_id],
    )

    @staticmethod
    def as_dict(choice) -> dict:
        return {'number': choice.choice_number,
                'text': choice.choice_text,
                'next_scene_id': choice.next_scene_id,
                'next_chapter_id': choice.next_chapter_id,
                'premium': choice.premium,
                'diamonds_cost': choice.diamonds_cost,
                'id': choice.id,
                'only_leader': choice.only_leader,
                'is_important': choice.is_important_choice,
                'teasing_change': choice.teasing_change,
                'friendship_change': choice.friendship_change,
                'passion_change': choice.passion_change,
                'required_teasing_level': choice.required_teasing_level,
                'required_passion_level': choice.required_passion_level,
                'required_friendship_level': choice.required_friendship_level,
                'is_legend_choice': choice.is_legend_choice,
                'legend_title': choice.legend_title,
                'legend_icon': choice.legend_icon
                }


class ChoiceHistory(Base):
    __tablename__ = "choices_history"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    choice_id: Mapped[int] = mapped_column(ForeignKey('choices.id', ondelete='CASCADE'), nullable=False)


class Character(Base):
    __tablename__ = "characters"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    avatar_image: Mapped[Optional[str]] = mapped_column(String(255))
    portrait_image: Mapped[Optional[str]] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    story_characters: Mapped[List["StoryCharacter"]] = relationship(
        "StoryCharacter", back_populates="character", cascade="all, delete-orphan"
    )


class StoryCharacter(Base):
    __tablename__ = "story_characters"
    __table_args__ = (UniqueConstraint("story_id", "character_id", name="uq_story_character"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    story_id: Mapped[int] = mapped_column(ForeignKey("stories.id", ondelete="CASCADE"), nullable=False)
    character_id: Mapped[int] = mapped_column(ForeignKey("characters.id", ondelete="CASCADE"), nullable=False)
    role: Mapped[Optional[str]] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    story: Mapped["Story"] = relationship("Story", back_populates="story_characters")
    character: Mapped["Character"] = relationship("Character", back_populates="story_characters")


class Database:
    def __init__(self, db_url: str):
        self.db_url = db_url
        print(f"Используется база: {self.db_url}")

        self.engine = create_engine(
            self.db_url,
            echo=True,
        )

        self.SessionLocal = sessionmaker(
            bind=self.engine,
            class_=Session,
            expire_on_commit=False
        )

        self.init_database()

    def init_database(self):
        Base.metadata.create_all(self.engine)
        print("✓ Все таблицы созданы")

    def get_connection(self) -> Connection:
        return self.engine.connect()

    @contextmanager
    def get_session(self):
        session = self.SessionLocal()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def get_user_by_id(self, user_id: int) -> Optional[User]:
        with self.get_session() as s:
            return s.get(User, user_id)

    def get_user_by_username(self, username: str) -> Optional[User]:
        with self.get_session() as s:
            return s.scalar(select(User).where(User.username == username))

    def get_user_by_email(self, email: str) -> Optional[User]:
        with self.get_session() as s:
            return s.scalar(select(User).where(User.email == email))

    def create_user(
        self,
        username: str,
        email: str,
        password_hash: str,
        password_salt: str,
        display_name: Optional[str] = None,
        diamonds: int = 0,
        is_leader: bool = False,
    ) -> Optional[int]:
        with self.get_session() as s:
            user = User(
                username=username,
                email=email,
                password_hash=password_hash,
                password_salt=password_salt,
                display_name=display_name or username,
                diamonds=diamonds,
                is_leader=is_leader,
            )
            s.add(user)
            try:
                s.flush()
                return user.id
            except IntegrityError:
                return None

    def update_user(self, user_id: int, **kwargs):
        with Session(self.engine) as s:
            user = self.get_user_by_id(user_id)

            for arg, value in kwargs.items():
                setattr(user, arg, value)

            s.commit()

    def create_session(
        self,
        user_id: int,
        session_token: str,
        expires_at: datetime,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> bool:
        with self.get_session() as s:
            session_obj = UserSession(
                user_id=user_id,
                session_token=session_token,
                expires_at=expires_at,
                ip_address=ip_address,
                user_agent=user_agent,
            )
            s.add(session_obj)
            return True

    def validate_session(self, session_token: str) -> Optional[Dict[str, Any]]:
        with self.get_session() as s:
            now = datetime.now()
            stmt = (
                select(UserSession)
                .options(joinedload(UserSession.user))
                .where(
                    UserSession.session_token == session_token,
                    UserSession.expires_at > now
                )
            )
            session_obj = s.scalar(stmt)
            if not session_obj:
                return None
            user = session_obj.user
            return {
                'session_token': session_obj.session_token,
                'user_id': user.id,
                'username': user.username,
                'email': user.email,
                'display_name': user.display_name,
                'avatar_url': user.avatar_url,
                'diamonds': user.diamonds,
                'theme': user.theme,
                'is_admin': user.is_admin,
                'expires_at': session_obj.expires_at
            }

    def delete_session(self, session_token: str) -> bool:
        with self.get_session() as s:
            stmt = delete(UserSession).where(UserSession.session_token == session_token)
            result = s.execute(stmt)
            return result.rowcount > 0

    def save_game(self, user_id: int, story_id: int, scene_id: int,
                  chapter_id: int, teasing_change: int, passion_change: int,
                  friendship_change: int):
        with Session(self.engine) as s:
            saved_game = s.query(GameSave).filter_by(user_id=user_id, story_id=story_id).first()

            if not saved_game:
                saved_game = GameSave(user_id=user_id, story_id=story_id)

                saved_game.teasing_level += teasing_change
                saved_game.friendship_level += friendship_change
                saved_game.passion_level += passion_change

                s.add(saved_game)
                s.commit()

            saved_game.scene_id = scene_id
            saved_game.chapter_id = chapter_id

            s.commit()

    def load_game(self, user_id: int, story_id: int) -> tuple[int, int]:
        with Session(self.engine) as s:
            saved_game = s.query(GameSave).filter_by(user_id=user_id, story_id=story_id).first()

            if not saved_game:
                saved_game = GameSave(user_id=user_id,
                                      story_id=story_id)

                first_chapter_in_story = s.query(Chapter).filter_by(story_id=story_id
                                                                    ).order_by(Chapter.id).first()

                saved_game.chapter_id = first_chapter_in_story.id
                saved_game.scene_id = s.query(Scene).filter_by(chapter_id=first_chapter_in_story.id
                                                               ).order_by(Scene.id).first().id

                s.add(saved_game)
                s.commit()

            return saved_game.chapter_id, saved_game.scene_id

    def load_game_raw(self, user_id: int, story_id: int) -> GameSave:
        with Session(self.engine) as s:
            saved_game = s.query(GameSave).filter_by(user_id=user_id, story_id=story_id).first()

            if not saved_game:
                saved_game = GameSave(user_id=user_id,
                                      story_id=story_id)

                first_chapter_in_story = s.query(Chapter).filter_by(story_id=story_id).first()

                saved_game.chapter_id = first_chapter_in_story.id
                saved_game.scene_id = s.query(Scene).filter_by(chapter_id=first_chapter_in_story.id).first().id

                s.add(saved_game)
                s.commit()

            return saved_game


    def get_user_stats(self, user_id: int) -> dict:
        with self.get_session() as s:
            stmt = (
                select(
                    func.sum(GameStat.play_time).label("total_play_time"),
                    func.count(GameStat.id).label("games_played"),
                    func.sum(GameStat.choices_made).label("total_choices"),
                    func.avg(GameStat.rating).label("avg_rating"),
                    func.count(GameStat.completed).filter(GameStat.completed == True).label("completed_games")
                )
                .select_from(GameStat)
                .where(GameStat.user_id == user_id)
            )

            result = s.execute(stmt).one()

            total_minutes = (result.total_play_time or 0) // 60

            return {
                "total_play_time_minutes": total_minutes,
                "games_played": result.games_played or 0,
                "completed_games": result.completed_games or 0,
                "total_choices": result.total_choices or 0,
                "average_rating": round(float(result.avg_rating), 1) if result.avg_rating else None,
            }

    def get_user_achievements(self, user_id: int) -> list[dict]:
        with self.get_session() as s:
            stmt = (
                select(
                    Achievement.achievement_name,
                    Achievement.description,
                    Achievement.unlocked_at
                )
                .where(Achievement.user_id == user_id)
                .order_by(Achievement.unlocked_at.desc())
            )

            results = s.execute(stmt).all()

            return [
                {
                    "name": row.achievement_name,
                    "description": row.description or "Без описания",
                    "unlocked_at": row.unlocked_at.isoformat() if row.unlocked_at else None,
                    # Можно добавить иконку/цвет/редкость позже
                    # "icon": f"/static/achievements/{row.achievement_name.lower()}.png",
                }
                for row in results
            ]

    def generate_diamond_code(self, amount: int, value: int) -> DiamondCode:
        with Session(self.engine) as s:
            diamond_code = DiamondCode(amount=amount,
                                           value=value)

            s.add(diamond_code)
            s.commit()

            return diamond_code


if __name__ == "__main__":
    db = Database()
    print("База данных инициализирована")