"""Claude Code Headless CLI 래퍼."""

import asyncio
import json

import structlog

logger = structlog.get_logger(__name__)


class ClaudeRunner:
    """Claude Code CLI를 비동기로 실행하는 래퍼 클래스."""

    def __init__(self, claude_path: str = "/usr/bin/claude", timeout: int = 120) -> None:
        self.claude_path = claude_path
        self.timeout = timeout

    async def run(
        self,
        prompt: str,
        output_format: str = "json",
        max_turns: int = 3,
        max_retries: int = 3,
    ) -> dict | str:
        """Claude CLI를 실행하고 결과를 반환한다 (지수 백오프 재시도 포함).

        Args:
            prompt: Claude에 전달할 프롬프트
            output_format: 출력 포맷 (json 또는 text)
            max_turns: 최대 턴 수
            max_retries: 최대 재시도 횟수

        Returns:
            output_format이 json이면 dict, 아니면 str

        Raises:
            TimeoutError: 모든 재시도 후에도 타임아웃 초과 시
            RuntimeError: 모든 재시도 후에도 프로세스 실행 실패 시
        """
        last_error: TimeoutError | RuntimeError | None = None
        for attempt in range(max_retries):
            try:
                return await self._execute(prompt, output_format, max_turns)
            except (TimeoutError, RuntimeError) as e:
                last_error = e
                if attempt < max_retries - 1:
                    delay = min(2 ** attempt * 5, 30)  # 5s, 10s, 20s (max 30s)
                    logger.warning(
                        "claude_retry",
                        attempt=attempt + 1,
                        max_retries=max_retries,
                        delay=delay,
                        error=str(e),
                    )
                    await asyncio.sleep(delay)
        raise last_error  # type: ignore[misc]

    async def _execute(
        self,
        prompt: str,
        output_format: str,
        max_turns: int,
    ) -> dict | str:
        """Claude CLI 단일 실행."""
        args = [
            self.claude_path,
            "-p",
            prompt,
            "--output-format",
            output_format,
            "--max-turns",
            str(max_turns),
        ]

        logger.info("claude_cli_start", output_format=output_format, max_turns=max_turns)

        process = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=self.timeout,
            )
        except TimeoutError:
            process.kill()
            await process.wait()
            logger.error("claude_cli_timeout", timeout=self.timeout)
            raise TimeoutError(
                f"Claude CLI가 {self.timeout}초 내에 응답하지 않았습니다"
            ) from None

        if process.returncode != 0:
            stderr_text = stderr.decode().strip()
            logger.error(
                "claude_cli_failed",
                returncode=process.returncode,
                stderr=stderr_text,
            )
            raise RuntimeError(
                f"Claude CLI 실행 실패 (code={process.returncode}): {stderr_text}"
            )

        raw_output = stdout.decode().strip()
        logger.info("claude_cli_success", output_length=len(raw_output))

        if output_format == "json":
            try:
                return json.loads(raw_output)
            except json.JSONDecodeError as e:
                logger.warning("claude_cli_json_parse_failed", error=str(e))
                raise RuntimeError(
                    f"Claude CLI JSON 파싱 실패: {e}"
                ) from e

        return raw_output

    async def health_check(self) -> bool:
        """Claude CLI 정상 동작 여부를 확인한다."""
        try:
            process = await asyncio.create_subprocess_exec(
                self.claude_path,
                "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(
                process.communicate(),
                timeout=10,
            )
            version = stdout.decode().strip()
            logger.info("claude_cli_health_ok", version=version)
            return process.returncode == 0
        except (TimeoutError, FileNotFoundError, OSError) as e:
            logger.error("claude_cli_health_failed", error=str(e))
            return False
