"""Tests for commands/handlers.py."""

from __future__ import annotations

from io import StringIO
from unittest.mock import MagicMock

import pytest

from anythink.app.chat import ChatState
from anythink.app.context import AppContext
from anythink.commands.handlers import register_commands
from anythink.commands.registry import CommandRegistry
from anythink.config.manager import Paths
from anythink.config.personas import Persona, PersonaManager
from anythink.providers.base import ChatMessage, TokenUsage


@pytest.fixture()
def registry() -> CommandRegistry:
    r = CommandRegistry()
    register_commands(r)
    return r


@pytest.fixture()
def ctx(xdg_dirs: Paths) -> AppContext:
    return AppContext.create(paths=xdg_dirs, console_file=StringIO())


@pytest.fixture()
def state(ctx: AppContext) -> ChatState:
    provider = MagicMock()
    provider.name = "mock"
    return ChatState(provider=provider, model_id="llama3", context_window=8192)


class TestRegisterCommands:
    def test_all_builtin_commands_registered(self, registry: CommandRegistry) -> None:
        expected = {"help", "clear", "history", "tokens", "model", "persona", "exit", "quit", "search"}
        assert expected.issubset(set(registry.names()))


class TestHelpCommand:
    async def test_help_lists_commands(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch("/help", ctx, state)
        assert result.message is not None
        assert "help" in result.message
        assert "exit" in result.message

    async def test_help_not_error(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch("/help", ctx, state)
        assert result.error is False


class TestClearCommand:
    async def test_clear_removes_user_and_assistant_messages(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        state.history = [
            ChatMessage(role="user", content="hello"),
            ChatMessage(role="assistant", content="hi"),
        ]
        result = await registry.dispatch("/clear", ctx, state)
        assert state.history == []
        assert "cleared" in (result.message or "").lower()

    async def test_clear_preserves_system_messages(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        state.history = [
            ChatMessage(role="system", content="You are a pirate."),
            ChatMessage(role="user", content="hello"),
        ]
        await registry.dispatch("/clear", ctx, state)
        assert len(state.history) == 1
        assert state.history[0].role == "system"

    async def test_clear_resets_token_count(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        state.total_tokens_used = 5000
        await registry.dispatch("/clear", ctx, state)
        assert state.total_tokens_used == 0


class TestHistoryCommand:
    async def test_history_empty(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch("/history", ctx, state)
        assert "No messages" in (result.message or "")

    async def test_history_shows_messages(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        state.history = [
            ChatMessage(role="user", content="What is 2+2?"),
            ChatMessage(role="assistant", content="4"),
        ]
        result = await registry.dispatch("/history", ctx, state)
        assert "[user]" in (result.message or "")
        assert "What is 2+2?" in (result.message or "")

    async def test_history_truncates_long_content(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        state.history = [ChatMessage(role="user", content="x" * 200)]
        result = await registry.dispatch("/history", ctx, state)
        assert "…" in (result.message or "")

    async def test_history_shows_limit_note_over_10(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        state.history = [
            ChatMessage(role="user", content=f"msg {i}") for i in range(15)
        ]
        result = await registry.dispatch("/history", ctx, state)
        assert "showing last 10" in (result.message or "")

    async def test_history_multimodal_shows_label(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        from anythink.providers.base import TextPart
        state.history = [ChatMessage(role="user", content=[TextPart("hi")])]
        result = await registry.dispatch("/history", ctx, state)
        assert "[multimodal" in (result.message or "")


class TestTokensCommand:
    async def test_tokens_shows_counts(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        state.total_tokens_used = 1234
        result = await registry.dispatch("/tokens", ctx, state)
        assert "1,234" in (result.message or "")
        assert "8,192" in (result.message or "")

    async def test_tokens_shows_percentage(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        state.total_tokens_used = 4096
        result = await registry.dispatch("/tokens", ctx, state)
        assert "50.0%" in (result.message or "")

    async def test_tokens_zero_context_no_crash(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        state.context_window = 0
        state.total_tokens_used = 0
        result = await registry.dispatch("/tokens", ctx, state)
        assert result.message is not None


class TestModelCommand:
    async def test_model_shows_provider_and_model(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch("/model", ctx, state)
        assert "mock" in (result.message or "")
        assert "llama3" in (result.message or "")


class TestPersonaCommand:
    async def test_persona_no_args_returns_error(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch("/persona", ctx, state)
        assert result.error is True
        assert "Usage" in (result.message or "")

    async def test_persona_clear_removes_system_messages(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        state.history = [
            ChatMessage(role="system", content="You are a pirate."),
            ChatMessage(role="user", content="hi"),
        ]
        result = await registry.dispatch("/persona clear", ctx, state)
        assert all(m.role != "system" for m in state.history)
        assert "cleared" in (result.message or "").lower()

    async def test_persona_set_unknown_returns_error(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch("/persona nonexistent", ctx, state)
        assert result.error is True
        assert "not found" in (result.message or "")

    async def test_persona_set_known_prepends_system_message(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        ctx.persona_manager.add(Persona(name="pirate", system_prompt="Speak like a pirate."))
        result = await registry.dispatch("/persona pirate", ctx, state)
        assert result.error is False
        assert state.history[0].role == "system"
        assert "pirate" in state.history[0].content  # type: ignore[operator]

    async def test_persona_replaces_existing_system_message(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        ctx.persona_manager.add(Persona(name="chef", system_prompt="You are a chef."))
        ctx.persona_manager.add(Persona(name="pirate", system_prompt="Speak pirate."))
        state.history = [ChatMessage(role="system", content="old persona")]
        await registry.dispatch("/persona pirate", ctx, state)
        system_msgs = [m for m in state.history if m.role == "system"]
        assert len(system_msgs) == 1
        assert "pirate" in system_msgs[0].content.lower()  # type: ignore[operator]


class TestSessionCommand:
    async def test_session_no_args_returns_error(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch("/session", ctx, state)
        assert result.error is True
        assert "Usage" in (result.message or "")

    async def test_session_unknown_sub_returns_error(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch("/session bloop", ctx, state)
        assert result.error is True

    async def test_session_list_empty(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch("/session list", ctx, state)
        assert "No saved sessions" in (result.message or "")

    async def test_session_save_no_name(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        state.history = [ChatMessage(role="user", content="hi")]
        result = await registry.dispatch("/session save", ctx, state)
        assert result.error is False
        assert len(ctx.session_manager.list_sessions()) == 1

    async def test_session_save_with_name(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        state.history = [ChatMessage(role="user", content="hi")]
        await registry.dispatch("/session save my-chat", ctx, state)
        sessions = ctx.session_manager.list_sessions()
        assert sessions[0].name == "my-chat"

    async def test_session_list_shows_saved_sessions(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        state.history = [ChatMessage(role="user", content="hi")]
        await registry.dispatch("/session save chat1", ctx, state)
        result = await registry.dispatch("/session list", ctx, state)
        assert "chat1" in (result.message or "")

    async def test_session_load_unknown_returns_error(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch("/session load nobody", ctx, state)
        assert result.error is True

    async def test_session_load_no_arg_returns_error(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch("/session load", ctx, state)
        assert result.error is True

    async def test_session_load_restores_history(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        state.history = [ChatMessage(role="user", content="loaded msg")]
        await registry.dispatch("/session save myload", ctx, state)
        state.history = []
        result = await registry.dispatch("/session load myload", ctx, state)
        assert result.error is False
        assert len(state.history) == 1
        assert state.history[0].content == "loaded msg"

    async def test_session_delete_unknown_returns_error(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch("/session delete nobody", ctx, state)
        assert result.error is True

    async def test_session_delete_no_arg_returns_error(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch("/session delete", ctx, state)
        assert result.error is True

    async def test_session_delete_removes_session(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        state.history = [ChatMessage(role="user", content="bye")]
        await registry.dispatch("/session save todele", ctx, state)
        await registry.dispatch("/session delete todele", ctx, state)
        assert ctx.session_manager.list_sessions() == []

    async def test_session_rename_no_args_returns_error(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch("/session rename", ctx, state)
        assert result.error is True

    async def test_session_rename_one_arg_returns_error(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch("/session rename oldname", ctx, state)
        assert result.error is True

    async def test_session_rename_unknown_returns_error(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch("/session rename nobody newname", ctx, state)
        assert result.error is True

    async def test_session_rename_updates_name(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        state.history = [ChatMessage(role="user", content="hello")]
        await registry.dispatch("/session save oldname", ctx, state)
        await registry.dispatch("/session rename oldname newname", ctx, state)
        sessions = ctx.session_manager.list_sessions()
        assert sessions[0].name == "newname"


class TestFileCommand:
    async def test_file_no_arg_returns_error(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch("/file", ctx, state)
        assert result.error is True
        assert "Usage" in (result.message or "")

    async def test_file_attaches_text_file(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState, tmp_path: pytest.TempPathFactory
    ) -> None:
        from pathlib import Path
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w", encoding="utf-8") as fh:
            fh.write("print('hello')")
            fpath = fh.name
        result = await registry.dispatch(f"/file {fpath}", ctx, state)
        assert result.error is False
        assert len(state.pending_attachments) == 1
        from anythink.files.reader import TextAttachment
        assert isinstance(state.pending_attachments[0], TextAttachment)

    async def test_file_nonexistent_returns_error(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch("/file /tmp/does_not_exist_anythink.py", ctx, state)
        assert result.error is True
        assert "not found" in (result.message or "").lower()

    async def test_file_image_extension_returns_error(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as fh:
            fh.write(b"\x89PNG")
            fpath = fh.name
        result = await registry.dispatch(f"/file {fpath}", ctx, state)
        assert result.error is True
        assert "/image" in (result.message or "")


class TestImageCommand:
    async def test_image_no_arg_returns_error(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch("/image", ctx, state)
        assert result.error is True
        assert "Usage" in (result.message or "")

    async def test_image_attaches_image_file(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as fh:
            fh.write(b"\x89PNG\r\n\x1a\n")
            fpath = fh.name
        result = await registry.dispatch(f"/image {fpath}", ctx, state)
        assert result.error is False
        assert len(state.pending_attachments) == 1
        from anythink.files.reader import ImageAttachment
        assert isinstance(state.pending_attachments[0], ImageAttachment)

    async def test_image_nonexistent_returns_error(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch("/image /tmp/no_such_image_anythink.png", ctx, state)
        assert result.error is True
        assert "not found" in (result.message or "").lower()

    async def test_image_unsupported_ext_returns_error(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".bmp", delete=False) as fh:
            fh.write(b"BM")
            fpath = fh.name
        result = await registry.dispatch(f"/image {fpath}", ctx, state)
        assert result.error is True
        assert "Unsupported" in (result.message or "")


class TestFilesCommand:
    async def test_files_empty_when_no_attachments(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch("/files", ctx, state)
        assert result.error is False
        assert "No pending" in (result.message or "")

    async def test_files_shows_text_attachment(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        from pathlib import Path
        from anythink.files.reader import TextAttachment
        state.pending_attachments.append(
            TextAttachment(path=Path("/tmp/script.py"), filename="script.py",
                           content="print()", size_bytes=7)
        )
        result = await registry.dispatch("/files", ctx, state)
        assert "script.py" in (result.message or "")

    async def test_files_shows_image_attachment(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        from pathlib import Path
        from anythink.files.reader import ImageAttachment
        from anythink.providers.base import ImagePart
        state.pending_attachments.append(
            ImageAttachment(path=Path("/tmp/img.png"), filename="img.png",
                            image_part=ImagePart(b"\x89PNG", "image/png"), size_bytes=4)
        )
        result = await registry.dispatch("/files", ctx, state)
        assert "img.png" in (result.message or "")
        assert "image/png" in (result.message or "")

    async def test_files_shows_count_of_multiple(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        from pathlib import Path
        from anythink.files.reader import TextAttachment
        state.pending_attachments.extend([
            TextAttachment(path=Path("/a.py"), filename="a.py", content="", size_bytes=0),
            TextAttachment(path=Path("/b.txt"), filename="b.txt", content="", size_bytes=0),
        ])
        result = await registry.dispatch("/files", ctx, state)
        assert "a.py" in (result.message or "")
        assert "b.txt" in (result.message or "")


class TestSearchCommand:
    def _mock_ctx_with_backend(
        self,
        ctx: AppContext,
        results: list | None = None,
        *,
        raises: bool = False,
        available: bool = True,
    ) -> AppContext:
        from unittest.mock import AsyncMock, MagicMock

        from anythink.exceptions import SearchError
        from anythink.search.registry import SearchRegistry

        mock_backend = MagicMock()
        mock_backend.name = "mock"
        mock_backend.is_available = MagicMock(return_value=available)

        if raises:
            mock_backend.search = AsyncMock(
                side_effect=SearchError("boom", user_message="search failed")
            )
        else:
            mock_backend.search = AsyncMock(return_value=results or [])

        r = SearchRegistry()
        r.register(mock_backend)
        ctx.search_registry = r
        return ctx

    async def test_on_enables_search(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        assert state.search_enabled is False
        result = await registry.dispatch("/search on", ctx, state)
        assert state.search_enabled is True
        assert result.error is False
        assert "enabled" in (result.message or "").lower()

    async def test_off_disables_search(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        state.search_enabled = True
        result = await registry.dispatch("/search off", ctx, state)
        assert state.search_enabled is False
        assert result.error is False
        assert "disabled" in (result.message or "").lower()

    async def test_no_args_returns_usage_error(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch("/search", ctx, state)
        assert result.error is True
        assert "Usage" in (result.message or "")

    async def test_query_shows_results(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        from anythink.search.base import SearchResult

        results = [SearchResult(title="Python.org", url="https://python.org", snippet="Language")]
        self._mock_ctx_with_backend(ctx, results=results)

        result = await registry.dispatch("/search python", ctx, state)

        assert result.error is False
        assert "Python.org" in (result.message or "")
        assert "https://python.org" in (result.message or "")

    async def test_query_shows_no_results_message(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        self._mock_ctx_with_backend(ctx, results=[])
        result = await registry.dispatch("/search obscure thing", ctx, state)
        assert result.error is False
        assert "No results" in (result.message or "")

    async def test_no_backend_returns_error(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        from anythink.search.registry import SearchRegistry

        ctx.search_registry = SearchRegistry()  # empty
        result = await registry.dispatch("/search python", ctx, state)
        assert result.error is True
        assert "No search backend" in (result.message or "")

    async def test_search_error_returns_error(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        self._mock_ctx_with_backend(ctx, raises=True)
        result = await registry.dispatch("/search python", ctx, state)
        assert result.error is True
        assert "search failed" in (result.message or "").lower()


class TestExitCommand:
    async def test_exit_sets_should_exit(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch("/exit", ctx, state)
        assert result.should_exit is True

    async def test_quit_sets_should_exit(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch("/quit", ctx, state)
        assert result.should_exit is True

    async def test_exit_has_goodbye_message(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch("/exit", ctx, state)
        assert result.message is not None
