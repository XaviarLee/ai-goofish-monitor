import asyncio
import re
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Optional, Pattern, Union

from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from src.utils import log_time, random_sleep

NEXT_PAGE_SELECTOR = (
    "button[class*='search-pagination-arrow-container']"
    ":has([class*='search-pagination-arrow-right'])"
    ":not([disabled])"
)
# 精确匹配 PC 搜索接口，允许版本号变化，并排除 search.shade 等联想接口。
SEARCH_RESULTS_API_PATTERN = re.compile(
    r"/h5/mtop\.taobao\.idlemtopsearch\.pc\.search/\d+\.\d+/"
)
SEARCH_RESULTS_API_FRAGMENT = "/h5/mtop.taobao.idlemtopsearch.pc.search/"
PAGE_REQUEST_TIMEOUT_MS = 20_000
PAGE_CLICK_TIMEOUT_MS = 10_000
PAGE_RETRY_DELAY_SECONDS = 5
PAGE_RETRY_COUNT = 2
PAGE_CLICK_SLEEP_MIN_SECONDS = 2
PAGE_CLICK_SLEEP_MAX_SECONDS = 5


@dataclass(frozen=True)
class PageAdvanceResult:
    advanced: bool
    response: Optional[Any] = None
    stop_reason: Optional[str] = None


def is_search_results_response(
    response: Any,
    api_url_fragment: Union[str, Pattern[str]] = SEARCH_RESULTS_API_PATTERN,
) -> bool:
    response_url = getattr(response, "url", "") or ""
    if isinstance(api_url_fragment, re.Pattern):
        if not api_url_fragment.search(response_url):
            return False
    elif api_url_fragment not in response_url:
        return False

    request = getattr(response, "request", None)
    request_method = str(getattr(request, "method", "") or "").upper()
    # 预检请求不是搜索结果；真实搜索接口以 POST 为主，也兼容 GET。
    return request_method != "OPTIONS"


async def advance_search_page(
    *,
    page: Any,
    page_num: int,
    logger: Callable[[str], None] = log_time,
    wait_after_click: Callable[[float, float], Awaitable[None]] = random_sleep,
    retry_sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    max_retries: int = PAGE_RETRY_COUNT,
) -> PageAdvanceResult:
    next_button = page.locator(NEXT_PAGE_SELECTOR).first
    if not await next_button.count():
        logger("已到达最后一页，未找到可用的'下一页'按钮，停止翻页。")
        return PageAdvanceResult(advanced=False, stop_reason="no_next_button")

    for retry_index in range(max_retries):
        try:
            await next_button.scroll_into_view_if_needed()
            async with page.expect_response(
                is_search_results_response,
                timeout=PAGE_REQUEST_TIMEOUT_MS,
            ) as response_info:
                try:
                    await next_button.click(timeout=PAGE_CLICK_TIMEOUT_MS)
                except PlaywrightTimeoutError:
                    logger(f"第 {page_num} 页下一页按钮点击超时，停止翻页。")
                    return PageAdvanceResult(
                        advanced=False,
                        stop_reason="click_timeout",
                    )
            await wait_after_click(
                PAGE_CLICK_SLEEP_MIN_SECONDS,
                PAGE_CLICK_SLEEP_MAX_SECONDS,
            )
            return PageAdvanceResult(
                advanced=True,
                response=await response_info.value,
            )
        except PlaywrightTimeoutError:
            if retry_index < max_retries - 1:
                logger(
                    f"等待第 {page_num} 页搜索响应超时，"
                    f"{PAGE_RETRY_DELAY_SECONDS}秒后重试..."
                )
                await retry_sleep(PAGE_RETRY_DELAY_SECONDS)
                continue

            logger(f"等待第 {page_num} 页搜索响应超时 {max_retries} 次，停止翻页。")
            return PageAdvanceResult(advanced=False, stop_reason="response_timeout")

    return PageAdvanceResult(advanced=False, stop_reason="unknown")
