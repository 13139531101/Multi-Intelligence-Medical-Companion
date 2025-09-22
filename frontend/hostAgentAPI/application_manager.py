from abc import ABC, abstractmethod
from A2AServer.common.A2Atypes import Message, Task, AgentCard
from ServiceTypes import Conversation, Event

class ApplicationManager(ABC):

  @abstractmethod
  def create_conversation(self) -> Conversation:
    pass

  @abstractmethod
  def sanitize_message(self, message: Message) -> Message:
    pass

  @abstractmethod
  async def process_message(self, message: Message):
    pass

  @abstractmethod
  def register_agent(self, url: str):
    pass

  @abstractmethod
  def get_pending_messages(self) -> list[str]:
    pass

  @property
  @abstractmethod
  def conversations(self) -> list[Conversation]:
    pass

  @property
  @abstractmethod
  def tasks(self) -> list[Task]:
    pass

  @property
  @abstractmethod
  def agents(self) -> list[AgentCard]:
    pass

  @property
  @abstractmethod
  def events(self) -> list[Event]:
    pass

