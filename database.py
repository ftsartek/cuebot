from os.path import exists
from sqlalchemy import create_engine, Column, Integer, Float, String, DateTime, Boolean, Interval, ForeignKey
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from datetime import timedelta
import config

Base = declarative_base()
engine = create_engine("sqlite:///records.db", echo=False, future=True)
Session = sessionmaker(bind=engine)
session = Session()
cfg = config.Config.get_instance()


class Member(Base):
    __tablename__ = "member"

    id = Column(Integer, primary_key=True)
    ref = Column(String(50), nullable=False)
    superuser = Column(Boolean, nullable=False, default=False)
    current_queue = relationship("Queue", back_populates='member', uselist=False, lazy=True)
    related = relationship("Related", back_populates='member', uselist=False, lazy=True)


class Queue(Base):
    __tablename__ = "queue"

    id = Column(Integer, primary_key=True, autoincrement=True)
    join_time = Column(DateTime, nullable=False)
    timeout_start = Column(DateTime, nullable=True)
    server_id = Column(Integer, ForeignKey('server.id'), nullable=False)
    member_id = Column(Integer, ForeignKey('member.id'), nullable=False, unique=True)
    server = relationship("Server", back_populates='server_queue', uselist=False, lazy=True)
    member = relationship("Member", back_populates='current_queue', uselist=False, lazy=True)


class Server(Base):
    __tablename__ = "server"

    id = Column(Integer, primary_key=True)
    voice_channel = Column(Integer, nullable=False, default=-1)
    text_channel = Column(Integer, nullable=False, default=-1)
    bot_channel = Column(Integer, nullable=False, default=-1)
    admin_channel = Column(Integer, nullable=False, default=-1)
    timeout_wait = Column(Integer, nullable=False, default=330)
    timeout_duration = Column(Integer, nullable=False, default=300)
    leaderboard_url = Column(String(100), nullable=False, default="https://warthunder.com/en/community/clansleaderboard/")
    squadron_url = Column(String(100), nullable=False, default="https://warthunder.com/en/community/claninfo/Immortal%20Legion")
    related = relationship("Related", back_populates='server', uselist=True, lazy=True)
    server_queue = relationship("Queue", back_populates='server', uselist=True, lazy=True)


class Related(Base):
    __tablename__ = "related"

    id = Column(Integer, primary_key=True, autoincrement=True)
    nick = Column(String(50), nullable=False)
    queue_time = Column(Interval, nullable=False, default=timedelta(seconds=0))
    queue_count = Column(Integer, nullable=False, default=0)
    admin = Column(Boolean, nullable=False, default=False)
    server_id = Column(Integer, ForeignKey('server.id'), nullable=False)
    member_id = Column(Integer, ForeignKey('member.id'), nullable=False)
    server = relationship("Server", back_populates='related', uselist=False, lazy=True)
    member = relationship("Member", back_populates='related', uselist=False, lazy=True)


class Leaderboard(Base):
    __tablename__ = "leaderboard"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, nullable=False)
    points = Column(Integer, nullable=False)
    placing = Column(Integer, nullable=False)
    playtime = Column(Float, nullable=False)


class PlayerScores(Base):
    __tablename__ = "playerscores"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, nullable=False)
    player = Column(String(50), nullable=False)
    points = Column(Integer, nullable=False)


if not exists("temp.db") and cfg.get_superuser_id is not None and cfg.get_superuser_ref is not None:
    Base.metadata.create_all(engine)
    superuser = Member(id=cfg.get_superuser_id, ref=cfg.get_superuser_ref, superuser=True)
    session.add(superuser)
    session.commit()
