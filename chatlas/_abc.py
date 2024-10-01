import asyncio
from abc import ABC, abstractmethod
from typing import Any, AsyncGenerator, Generic, Optional, TypeVar

from ._utils import ToolFunction

MessageType = TypeVar("MessageType")


class BaseChat(ABC, Generic[MessageType]):
    @abstractmethod
    async def response_generator(
        self,
        user_input: str,
        *,
        stream: bool = True,
    ) -> AsyncGenerator[str, None]:
        """
        Generate a response from user input.

        Parameters
        ----------
        user_input
            The user input to generate a response from.
        stream
            Whether to stream the response (i.e., have the response appear in chunks).

        Yields
        ------
        str
            The response content.
        """
        ...

    @abstractmethod
    def messages(self) -> list[MessageType]:
        """
        Get messages from the chat conversation.

        Returns
        -------
        list[MessageType]
            The messages from the chat conversation.
        """
        ...

    def console(self):
        """
        Enter a chat console to interact with the LLM.
        """

        print("\nEntering chat console. Press Ctrl+C to quit.\n")

        # Create event loop once
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        while True:
            user_input = input("?> ")
            if user_input.strip().lower() in ("exit", "exit()"):
                break
            print("")
            self._chat(user_input, loop=loop)
            print("")

    def app(self, *, launch_browser: bool = True, port: int = 0):
        """
        Enter a chat browser to interact with the LLM.
        """

        try:
            from shiny import App, run_app, ui
        except ImportError:
            raise ImportError(
                "The `shiny` package is required for the `browser` method. "
                "Install it with `pip install shiny`."
            )

        app_ui = ui.page_fillable(
            ui.chat_ui("chat"),
            fillable_mobile=True,
        )

        def server(input):
            chat = ui.Chat("chat", messages=self.messages())

            @chat.on_user_submit
            async def _():
                user_input = chat.user_input()
                response = self.response_generator(user_input)  # type: ignore
                await chat.append_message_stream(response)

        run_app(App(app_ui, server), launch_browser=launch_browser)

    def chat(
        self,
        user_input: str,
        *,
        stream: bool = True,
    ):
        """
        Chat with the LLM.

        Parameters
        ----------
        user_input
            The user input to chat with.
        stream
            Whether to stream the response (i.e., have the response appear in chunks).

        Returns
        -------
        None
        """
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return self._chat(user_input, stream=stream, loop=loop)

    def _chat(
        self,
        user_input: str,
        *,
        stream: bool = True,
        loop: asyncio.AbstractEventLoop,
    ):
        from rich.console import Console
        from rich.live import Live
        from rich.markdown import Markdown

        response = self.response_generator(user_input, stream=stream)

        async def _send_response_to_console():
            console = Console()
            content = ""

            with Live(console=console, refresh_per_second=10) as live:
                async for part in response:
                    content += part
                    live.update(Markdown(content))
                    await asyncio.sleep(0.001)

        return loop.run_until_complete(_send_response_to_console())


class BaseChatWithTools(BaseChat[MessageType]):
    @abstractmethod
    def register_tool(
        self,
        func: ToolFunction,
        *,
        schema: Optional[Any] = None,
        name: Optional[str] = None,
        description: Optional[str] = None,
        parameter_descriptions: Optional[dict[str, str]] = None,
    ) -> None: ...


# def _get_token_count(
#     self,
#     content: str,
# ) -> int:
#     if self._tokenizer is None:
#         self._tokenizer = get_default_tokenizer()
#
#     if self._tokenizer is None:
#         raise ValueError(
#             "A tokenizer is required to impose `token_limits` on messages. "
#             "To get a generic default tokenizer, install the `tokenizers` "
#             "package (`pip install tokenizers`). "
#             "To get a more precise token count, provide a specific tokenizer "
#             "to the `Chat` constructor."
#         )
#
#     encoded = self._tokenizer.encode(content)
#     if isinstance(encoded, TokenizersEncoding):
#         return len(encoded.ids)
#     else:
#         return len(encoded)


# def _trim_messages(
#         self,
#         messages: tuple[TransformedMessage, ...],
#         token_limits: tuple[int, int],
#     ) -> tuple[TransformedMessage, ...]:

#         n_total, n_reserve = token_limits
#         if n_total <= n_reserve:
#             raise ValueError(
#                 f"Invalid token limits: {token_limits}. The 1st value must be greater "
#                 "than the 2nd value."
#             )

#         # Since don't trim system messages, 1st obtain their total token count
#         # (so we can determine how many non-system messages can fit)
#         n_system_tokens: int = 0
#         n_system_messages: int = 0
#         n_other_messages: int = 0
#         token_counts: list[int] = []
#         for m in messages:
#             content = (
#                 m.content_server if isinstance(m, TransformedMessage) else m.content
#             )
#             count = self._get_token_count(content)
#             token_counts.append(count)
#             if m.role == "system":
#                 n_system_tokens += count
#                 n_system_messages += 1
#             else:
#                 n_other_messages += 1

#         remaining_non_system_tokens = n_total - n_reserve - n_system_tokens

#         if remaining_non_system_tokens <= 0:
#             raise ValueError(
#                 f"System messages exceed `.messages(token_limits={token_limits})`. "
#                 "Consider increasing the 1st value of `token_limit` or setting it to "
#                 "`token_limit=None` to disable token limits."
#             )

#         # Now, iterate through the messages in reverse order and appending
#         # until we run out of tokens
#         messages2: list[TransformedMessage] = []
#         n_other_messages2: int = 0
#         token_counts.reverse()
#         for i, m in enumerate(reversed(messages)):
#             if m.role == "system":
#                 messages2.append(m)
#                 continue
#             remaining_non_system_tokens -= token_counts[i]
#             if remaining_non_system_tokens >= 0:
#                 messages2.append(m)
#                 n_other_messages2 += 1

#         messages2.reverse()

#         if len(messages2) == n_system_messages and n_other_messages2 > 0:
#             raise ValueError(
#                 f"Only system messages fit within `.messages(token_limits={token_limits})`. "
#                 "Consider increasing the 1st value of `token_limit` or setting it to "
#                 "`token_limit=None` to disable token limits."
#             )

#         return tuple(messages2)

#   def _trim_anthropic_messages(
#       self,
#       messages: tuple[TransformedMessage, ...],
#   ) -> tuple[TransformedMessage, ...]:

#       if any(m.role == "system" for m in messages):
#           raise ValueError(
#               "Anthropic requires a system prompt to be specified in it's `.create()` method "
#               "(not in the chat messages with `role: system`)."
#           )
#       for i, m in enumerate(messages):
#           if m.role == "user":
#               return messages[i:]

#       return ()
