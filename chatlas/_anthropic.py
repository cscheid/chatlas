import json
from typing import TYPE_CHECKING, AsyncGenerator, Iterable, Optional, cast

from . import _utils
from ._abc import BaseChatWithTools
from ._anthropic_types import CreateCompletion
from ._utils import ToolFunction

if TYPE_CHECKING:
    from anthropic import AsyncAnthropic
    from anthropic.types import (
        ContentBlock,
        MessageParam,
        Model,
        TextBlock,
        ToolParam,
        ToolResultBlockParam,
        ToolUseBlock,
    )


class AnthropicChat(BaseChatWithTools["CreateCompletion"]):
    _messages: list["MessageParam"] = []
    _tool_schemas: list["ToolParam"] = []
    _tool_functions: dict[str, _utils.ToolFunctionAsync] = {}

    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        model: "Model" = "claude-3-5-sonnet-20240620",
        system_prompt: Optional[str] = None,
        max_tokens: int = 1024,
        tools: Iterable[ToolFunction] = (),
        client: "AsyncAnthropic | None" = None,
    ):
        """
        Start a chat powered by Anthropic

        Parameters
        ----------
        api_key
            Your Anthropic API key.
        model
            The model to use for the chat.
        system_prompt
            A system prompt to use for the chat.
        max_tokens
            The maximum number of tokens to generate for each response.
        tools
            A list of tools (i.e., function calls) to use for the chat.
        client
            An `anthropic.AsyncAnthropic` client instance to use for the chat.
            Use this to customize stuff like `base_url`, `timeout`, etc.

        Raises
        ------
        ImportError
            If the `anthropic` package is not installed.
        """
        self._model = model
        self._system_prompt = system_prompt
        self._max_tokens = max_tokens
        for tool in tools:
            self.register_tool(tool)
        if client is None:
            client = self._get_client()
        if api_key is not None:
            client.api_key = api_key
        self.client = client

    def _get_client(self) -> "AsyncAnthropic":
        try:
            from anthropic import AsyncAnthropic

            return AsyncAnthropic()
        except ImportError:
            raise ImportError(
                f"The {self.__class__.__name__} class requires the `anthropic` package. "
                "Please install it with `pip install anthropic`."
            )

    async def response_generator(
        self,
        user_input: str,
        *,
        stream: bool = True,
        kwargs: Optional[CreateCompletion] = None,
    ) -> AsyncGenerator[str, None]:
        """
        Generate response(s) given a user input.

        Parameters
        ----------
        user_input
            The user input to generate responses for.
        stream
            Whether to stream the responses.
        kwargs
            Additional arguments to pass to the Anthropic's `messages.create()`
            method.
        """
        self._add_message({"role": "user", "content": user_input})
        while True:
            async for chunk in self._submit_messages(stream, kwargs):
                yield chunk
            if not await self._invoke_tools():
                break

    async def _submit_messages(
        self,
        stream: bool = True,
        kwargs: Optional[CreateCompletion] = None,
    ) -> AsyncGenerator[str, None]:
        if kwargs is None:
            kwargs = {}

        model = kwargs.pop("model", self._model)
        max_tokens = kwargs.pop("max_tokens", self._max_tokens)
        tools = kwargs.pop("tools", [])
        tools = list(tools or [])
        tools.extend(self._tool_schemas)

        if self._system_prompt is not None:
            kwargs["system"] = kwargs.get("system", self._system_prompt)

        if stream:
            response = await self.client.messages.create(
                model=model,
                messages=self.messages(),
                max_tokens=max_tokens,
                tools=tools,
                stream=True,
                **kwargs,  # type: ignore
            )

            # Accumulate content blocks until the end of the stream
            # (and yield the text content)
            # TODO: handle stop_reasons (i.e., type = "message_delta" events)
            contents: list["ContentBlock"] = []
            current_content: Optional["ContentBlock"] = None
            async for chunk in response:
                if chunk.type == "content_block_start":
                    current_content = chunk.content_block
                elif chunk.type == "content_block_delta":
                    if chunk.delta.type == "text_delta":
                        current_content = cast("TextBlock", current_content)
                        current_content.text += chunk.delta.text
                        yield chunk.delta.text
                    elif chunk.delta.type == "input_json_delta":
                        current_content = cast("ToolUseBlock", current_content)
                        if not isinstance(current_content.input, str):
                            current_content.input = ""
                        current_content.input += chunk.delta.partial_json
                    else:
                        raise ValueError(f"Unknown delta type: {chunk.delta.type}")
                elif chunk.type == "content_block_stop":
                    if current_content is None:
                        continue
                    if current_content.type == "tool_use" and isinstance(
                        current_content.input, str
                    ):
                        try:
                            current_content.input = json.loads(current_content.input)
                        except json.JSONDecodeError as e:
                            raise ValueError(f"Invalid JSON input: {e}")
                    contents.append(current_content)

            msg: "MessageParam" = {"content": contents, "role": "assistant"}
            self._add_message(msg)

        else:
            response = await self.client.messages.create(
                model=model,
                messages=self.messages(),
                max_tokens=max_tokens,
                tools=tools,
                stream=False,
                **kwargs,  # type: ignore
            )

            for x in response.content:
                if x.type == "text":
                    yield x.text

            # TODO: handle stop_reasons?
            msg: "MessageParam" = {
                "content": response.content,
                "role": "assistant",
            }
            self._add_message(msg)

    def messages(self) -> list["MessageParam"]:
        """
        Get the messages in the chat.

        Returns
        -------
        list[MessageParam]
            The messages in the chat.
        """
        return self._messages

    def _add_message(self, message: "MessageParam"):
        self._messages.append(message)

    def register_tool(
        self,
        func: ToolFunction,
        *,
        schema: Optional["ToolParam"] = None,
        name: Optional[str] = None,
        description: Optional[str] = None,
        parameter_descriptions: Optional[dict[str, str]] = None,
    ) -> None:
        """
        Register a tool to use in the chat.

        Parameters
        ----------
        func
            The tool function (i.e., a Python function).
        schema
            The schema for the tool. If not provided, it will be auto-generated from
            the function.
        name
            The name of the tool. If not provided, it will be taken from the function.
        description
            The description of the tool. If not provided, it will be taken from the
            function's docstring.
        parameter_descriptions
            The descriptions of the parameters of the tool.
        """
        if schema is None:
            final_schema = self._transform_tool_schema(
                _utils.func_to_schema(func, name, description, parameter_descriptions)
            )
        else:
            final_schema = schema

        name = final_schema["name"]

        self._tool_schemas = [x for x in self._tool_schemas if x["name"] != name]
        self._tool_schemas.append(final_schema)
        self._tool_functions[name] = _utils.wrap_async(func)

    @staticmethod
    def _transform_tool_schema(
        tool: _utils.ToolSchema,
    ) -> "ToolParam":
        fn = tool["function"]
        name = fn["name"]
        return {
            "name": name,
            "description": fn["description"],
            "input_schema": {
                "type": "object",
                "properties": fn["parameters"]["properties"],
            },
        }

    async def _invoke_tools(self) -> bool:
        if self._tool_functions:
            last = self.messages()[-1]
            assert last["role"] == "assistant"
            tool_messages = await self._call_tools(last)
            if tool_messages:
                self._add_message(tool_messages)
                return True
        return False

    async def _call_tools(self, last_message: "MessageParam") -> "MessageParam | None":
        from anthropic.types import ToolUseBlock

        contents = last_message["content"]
        if isinstance(contents, str):
            return None
        tool_calls = [x for x in contents if isinstance(x, ToolUseBlock)]
        results: list["ToolResultBlockParam"] = []
        for x in tool_calls:
            msg = await self._call_tool(x)
            results.append(msg)
        if len(results) == 0:
            return None
        res: "MessageParam" = {"content": results, "role": "user"}
        return res

    async def _call_tool(
        self,
        tool_call: "ToolUseBlock",
    ) -> "ToolResultBlockParam":
        name = tool_call.name
        tool_fun = self._tool_functions.get(name, None)
        if tool_fun is None:
            raise ValueError(f"Tool {name} not found.")

        args = tool_call.input

        if isinstance(args, str):
            try:
                args = json.loads(args)
            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid JSON arguments for tool {name}: {e}")

        if not isinstance(args, dict):
            raise ValueError(
                f"Expected a dictionary of arguments, got {type(args).__name__}."
            )

        try:
            result = await tool_fun(**args)
        except Exception as e:
            raise ValueError(f"Error calling tool {name}: {e}")

        res: "ToolResultBlockParam" = {
            "type": "tool_result",
            "tool_use_id": tool_call.id,
            "content": str(result),
        }

        return res
