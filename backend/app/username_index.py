from typing import Set

class UsernameIndex:
    """
    Authoritative in-process read index.
    Loaded once at startup.
    Mutated only after successful DB writes.
    """
    __slots__ = ("_usernames",)

    def __init__(self):
        self._usernames: Set[str] = set()

    def load(self, usernames: list[str]) -> None:
        self._usernames = set(usernames)

    def exists(self, username: str) -> bool:
        return username in self._usernames  # O(1) C-level hash lookup

    def add(self, username: str) -> None:
        self._usernames.add(username)

    def remove(self, username: str) -> None:
        self._usernames.discard(username)

username_index = UsernameIndex()
